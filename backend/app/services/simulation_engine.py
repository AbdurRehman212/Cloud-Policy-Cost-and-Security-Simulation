"""
simulation_engine.py — CloudSim-style Simulation Engine
=======================================================

Architecture (strict ownership):
  SimulationEngine is the ONLY owner of:
    - time progression (internal tick counter per context)
    - VM state (via SimulationContext.vm_state)
    - autoscaling logic
    - queue / latency metrics
    - all system state mutations

  SimulationContext is the per-org state capsule.
"""

from __future__ import annotations

import logging
import random
import string
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from queue import PriorityQueue
from threading import Event, Lock, Thread
from typing import Dict, List, Optional, Any

from app.services.simulation_core import (
    MAX_VMS,
    BASE_LATENCY_MS,
    Autoscaler,
    AutoscalerConfig,
    DataCenter,
    Host,
    MetricsEngine,
    ScalingDecision,
    SimVM,
    TickMetrics,
    VMRegistry,
    VMState,
    orm_vm_to_simvm,
    vm_registry,
    metrics_engine,
)

logger = logging.getLogger(__name__)

class EventType(Enum):
    REQUEST_ARRIVAL = auto()
    VM_ADD          = auto()
    VM_REMOVE       = auto()
    SCALE_UP        = auto()
    SCALE_DOWN      = auto()
    TICK            = auto()
    PROCESS_START   = auto()
    PROCESS_END     = auto()
    VM_PROVISIONED  = auto()

@dataclass(order=True)
class SimulationEvent:
    timestamp: float
    seq: int = field(default=0)
    type: EventType = field(compare=False, default=EventType.TICK)
    payload: Dict[str, Any] = field(default_factory=dict, compare=False)

_CAPACITY_TABLE: Dict[str, int] = {
    "t2.micro": 50, "t2.small": 100, "t2.medium": 200, "t2.large": 400,
    "t3.micro": 60, "t3.small": 120, "t3.medium": 250,
    "m5.large": 300, "m5.xlarge": 600, "c5.large": 400, "c5.xlarge": 800,
}

@dataclass
class SimulationContext:
    org_id: int
    current_tick: int = 0
    workload_sequence: List[int] = field(default_factory=list)
    vm_state: List[SimVM] = field(default_factory=list)
    queue_state: float = 0.0
    metrics: Optional[TickMetrics] = None
    is_running: bool = False
    scenario_id: Optional[int] = None
    total_ticks: int = 0
    autoscaler: Optional[Autoscaler] = None
    
    current_time: float = 0.0
    event_counter: int = 0
    event_queue: PriorityQueue = field(default_factory=PriorityQueue)
    vm_queues: Dict[str, List[float]] = field(default_factory=dict) # vm_id -> [arrival_times]
    vm_busy: Dict[str, bool] = field(default_factory=dict)
    tick_latencies: List[float] = field(default_factory=list)
    max_queue_size: int = 500
    dropped_requests: int = 0
    
    # Scheduler state per context for multi-tenant isolation
    scheduler_idx: int = 0
    
    _stop_event: Event = field(default_factory=Event, repr=False)
    _thread: Optional[Thread] = field(default=None, repr=False)

    def enqueue_event(self, timestamp: float, event_type: EventType, payload: Dict[str, Any] = None) -> None:
        self.event_counter += 1
        self.event_queue.put(SimulationEvent(
            timestamp=timestamp,
            seq=self.event_counter,
            type=event_type,
            payload=payload or {}
        ))

    def stop(self) -> None:
        self.is_running = False
        self._stop_event.set()

    def to_dict(self) -> dict:
        m = self.metrics
        return {
            "org_id": self.org_id, "scenario_id": self.scenario_id,
            "current_tick": self.current_tick, "total_ticks": self.total_ticks,
            "is_running": self.is_running, "vm_count": len(self.vm_state),
            "queue_depth": self.queue_state,
            "dropped_requests": self.dropped_requests,
            "metrics": {
                "incoming_rps": m.incoming_rps if m else 0,
                "total_capacity_rps": m.total_capacity_rps if m else 0,
                "queue_depth": m.queue_depth if m else 0.0,
                "latency_ms": m.latency_ms if m else BASE_LATENCY_MS,
                "cpu_avg": m.cpu_avg if m else 0.0,
                "memory_avg": m.memory_avg if m else 0.0,
                "overloaded": m.overloaded if m else False,
                "vm_count": m.vm_count if m else 0,
            } if m else {},
        }

class RequestScheduler:
    def __init__(self, strategy: str = "round-robin"):
        self.strategy = strategy

    def schedule(self, ctx: SimulationContext, rps: int, timestamp: float) -> None:
        active_vms = [v for v in ctx.vm_state if v.state in {VMState.RUNNING, VMState.OVERLOADED, VMState.SCALING}]
        if not active_vms:
            ctx.dropped_requests += rps
            return

        if self.strategy == "round-robin":
            for _ in range(rps):
                vm = active_vms[ctx.scheduler_idx % len(active_vms)]
                if vm.vm_id not in ctx.vm_queues:
                    ctx.vm_queues[vm.vm_id] = []
                
                if len(ctx.vm_queues[vm.vm_id]) < ctx.max_queue_size:
                    ctx.vm_queues[vm.vm_id].append(timestamp)
                    # Event Chaining: If VM is idle, schedule PROCESS_START
                    if not ctx.vm_busy.get(vm.vm_id, False):
                        ctx.vm_busy[vm.vm_id] = True
                        ctx.enqueue_event(ctx.current_time, EventType.PROCESS_START, {"vm_id": vm.vm_id})
                else:
                    ctx.dropped_requests += 1
                ctx.scheduler_idx += 1

class SimulationEngine:
    TICK_INTERVAL: float = 1.0

    def __init__(self) -> None:
        self.registry: VMRegistry = vm_registry
        self._metrics_engine: MetricsEngine = metrics_engine
        self.scheduler = RequestScheduler()
        self.contexts: Dict[int, SimulationContext] = {}
        self._ctx_lock: Lock = Lock()
        self.datacenter = DataCenter(name="sim-dc", region="us-east-1")
        self._default_host = Host(host_id="host-0", vcpu_total=512, ram_gb_total=2048.0)
        self.datacenter.register_host(self._default_host)
        self._app = None
        self._idle_running: bool = False
        self._idle_stop: Event = Event()
        self._instance_id: str = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    def start(self, app) -> None:
        self._app = app
        if self._idle_running: return
        self._idle_running = True
        self._idle_thread = Thread(target=self._idle_loop, name="SimEngine-idle", daemon=True)
        self._idle_thread.start()

    def stop(self) -> None:
        self._idle_running = False
        self._idle_stop.set()
        with self._ctx_lock:
            for ctx in list(self.contexts.values()): ctx.stop()

    def start_scenario(self, org_id: int, workload_pattern: List[int], scenario_id: Optional[int] = None) -> bool:
        with self._ctx_lock:
            existing = self.contexts.get(org_id)
            if existing and existing.is_running: return False
            ctx = SimulationContext(
                org_id=org_id, workload_sequence=list(workload_pattern),
                total_ticks=len(workload_pattern), is_running=True,
                scenario_id=scenario_id,
                autoscaler=Autoscaler(self.datacenter, AutoscalerConfig(cooldown_ticks=4))
            )
            self.contexts[org_id] = ctx
        
        self._seed_context_vms(ctx)
        
        # Enqueue initial workload events
        for i, rps in enumerate(workload_pattern):
            ctx.enqueue_event(float(i), EventType.REQUEST_ARRIVAL, {"rps": rps})
        
        # Enqueue first tick
        ctx.enqueue_event(0.0, EventType.TICK)
        
        ctx._thread = Thread(target=self._context_loop, args=(ctx,), name=f"SimEngine-org{org_id}", daemon=True)
        ctx._thread.start()
        return True

    def stop_scenario(self, org_id: int) -> None:
        with self._ctx_lock:
            ctx = self.contexts.get(org_id)
        if ctx: ctx.stop()

    def get_state(self, org_id: int) -> dict:
        with self._ctx_lock:
            ctx = self.contexts.get(org_id)
        return ctx.to_dict() if ctx else {"org_id": org_id, "is_running": False}

    def is_scenario_running(self, org_id: int) -> bool:
        with self._ctx_lock:
            ctx = self.contexts.get(org_id)
        return bool(ctx and ctx.is_running)

    def add_vm(self, org_id: int, vm_id: str) -> None:
        """Add a VM to the active context immediately via event."""
        logger.info(f"[ENGINE_ACTION] VM ADDED: vm_id={vm_id} org={org_id} (Engine: {self._instance_id})")
        with self._ctx_lock:
            ctx = self.contexts.get(org_id)
        if ctx:
            ctx.enqueue_event(ctx.current_time, EventType.VM_ADD, {"vm_id": vm_id})
        logger.info(f"[ENGINE_STATE] Current VM count in registry: {self.registry.count}")

    def remove_vm(self, org_id: int, vm_id: str) -> None:
        """Remove a VM from the active context immediately via event."""
        logger.info(f"[ENGINE_ACTION] VM REMOVED: vm_id={vm_id} org={org_id} (Engine: {self._instance_id})")
        with self._ctx_lock:
            ctx = self.contexts.get(org_id)
        if ctx:
            ctx.enqueue_event(ctx.current_time, EventType.VM_REMOVE, {"vm_id": vm_id})
        logger.info(f"[ENGINE_STATE] Current VM count in registry: {self.registry.count}")

    def _context_loop(self, ctx: SimulationContext) -> None:
        if not self._app: return
        with self._app.app_context():
            from app import socketio
            sim_start_time = time.monotonic()
            
            while ctx.is_running and not ctx._stop_event.is_set():
                try:
                    # Use a short timeout to check stop_event frequently
                    event = ctx.event_queue.get(timeout=0.1)
                except:
                    if ctx.event_queue.empty() and ctx.current_tick >= ctx.total_ticks:
                        ctx.is_running = False
                        self._emit_complete(socketio, ctx)
                        break
                    continue

                # Real-time synchronization (optional, but keeps UI updates smooth)
                wait_time = event.timestamp - (time.monotonic() - sim_start_time)
                if wait_time > 0:
                    if ctx._stop_event.wait(wait_time):
                        break

                # Update simulation clock strictly from event timestamp
                ctx.current_time = max(ctx.current_time, event.timestamp)
                self._process_event(ctx, event, socketio)

    def _process_event(self, ctx: SimulationContext, event: SimulationEvent, socketio) -> None:
        if event.type == EventType.REQUEST_ARRIVAL:
            rps = event.payload.get("rps", 0)
            self.scheduler.schedule(ctx, rps, event.timestamp)
        
        elif event.type == EventType.TICK:
            self._handle_tick(ctx, socketio)
            
        elif event.type == EventType.VM_ADD:
            self._handle_vm_add(ctx, event.payload.get("vm_id"))
            
        elif event.type == EventType.VM_REMOVE:
            self._handle_vm_remove(ctx, event.payload.get("vm_id"))
            
        elif event.type == EventType.SCALE_UP:
            self._handle_scale_out(ctx)
            
        elif event.type == EventType.SCALE_DOWN:
            self._handle_scale_in(ctx)
            
        elif event.type == EventType.PROCESS_START:
            self._handle_process_start(ctx, event.payload.get("vm_id"))
            
        elif event.type == EventType.PROCESS_END:
            self._handle_process_end(ctx, event.payload)
            
        elif event.type == EventType.VM_PROVISIONED:
            self._handle_vm_provisioned(ctx, event.payload.get("vm_id"))

    def _handle_tick(self, ctx: SimulationContext, socketio) -> None:
        rps = ctx.workload_sequence[ctx.current_tick] if ctx.current_tick < len(ctx.workload_sequence) else 0
        
        # Autoscaling evaluation
        self._evaluate_autoscaling(ctx)
        
        # Standard tick logic
        self._update_metrics(ctx, rps)
        self._persist(ctx)
        self._emit_tick(socketio, ctx, rps)
        
        # Reset tick accumulators
        ctx.tick_latencies = []
        
        ctx.current_tick += 1
        if ctx.current_tick < ctx.total_ticks:
            ctx.enqueue_event(float(ctx.current_tick), EventType.TICK)

    def _handle_process_start(self, ctx: SimulationContext, vm_id: str) -> None:
        vm = next((v for v in ctx.vm_state if v.vm_id == vm_id), None)
        if not vm or vm.state not in {VMState.RUNNING, VMState.OVERLOADED, VMState.SCALING}:
            ctx.vm_busy[vm_id] = False
            return
            
        queue = ctx.vm_queues.get(vm_id, [])
        if not queue:
            ctx.vm_busy[vm_id] = False
            return
            
        # Pop the first request
        arrival_time = queue.pop(0)
        ctx.vm_busy[vm_id] = True
        
        # Calculate processing duration (seconds)
        processing_duration = 1.0 / vm.capacity_rps if vm.capacity_rps > 0 else 0.01
        
        # Schedule PROCESS_END
        ctx.enqueue_event(
            ctx.current_time + processing_duration, 
            EventType.PROCESS_END, 
            {"vm_id": vm_id, "arrival_time": arrival_time}
        )

    def _handle_process_end(self, ctx: SimulationContext, payload: Dict[str, Any]) -> None:
        vm_id = payload.get("vm_id")
        arrival_time = payload.get("arrival_time", ctx.current_time)
        
        # Accumulate latency (ms)
        latency_ms = (ctx.current_time - arrival_time) * 1000.0
        ctx.tick_latencies.append(latency_ms)
        
        ctx.vm_busy[vm_id] = False
        
        # Event Chaining: If queue has more requests, start next one
        if ctx.vm_queues.get(vm_id):
            self._handle_process_start(ctx, vm_id)

    def _handle_vm_provisioned(self, ctx: SimulationContext, vm_id: str) -> None:
        vm = next((v for v in ctx.vm_state if v.vm_id == vm_id), None)
        if vm and vm.state == VMState.PROVISIONING:
            vm.transition(VMState.RUNNING)
            # If requests were already queued, trigger processing
            if ctx.vm_queues.get(vm_id) and not ctx.vm_busy.get(vm_id):
                self._handle_process_start(ctx, vm_id)

    def _evaluate_autoscaling(self, ctx: SimulationContext) -> None:
        if not ctx.autoscaler or not ctx.metrics: return
        
        # Improved Autoscaler: Prevent oscillation during provisioning
        provisioning = [v for v in ctx.vm_state if v.state == VMState.PROVISIONING]
        if provisioning:
            logger.debug("[Autoscaler] Skipping evaluation: %d VMs are provisioning", len(provisioning))
            return
            
        decision = ctx.autoscaler.evaluate(ctx.metrics)
        if decision == ScalingDecision.SCALE_OUT:
            ctx.enqueue_event(ctx.current_time, EventType.SCALE_UP)
        elif decision == ScalingDecision.SCALE_IN:
            ctx.enqueue_event(ctx.current_time, EventType.SCALE_DOWN)

    def _handle_vm_add(self, ctx: SimulationContext, vm_id: str) -> None:
        from app.models.resources import VirtualMachine
        with self._app.app_context():
            vm = VirtualMachine.query.filter_by(instance_id=vm_id).first()
            if vm:
                svm = self.registry.get(vm_id) or orm_vm_to_simvm(vm)
                if not self.registry.get(vm_id): self.registry.register(svm)
                if svm not in self._default_host.vms: self._default_host.vms.append(svm)
                if svm not in ctx.vm_state: ctx.vm_state.append(svm)

    def _handle_vm_remove(self, ctx: SimulationContext, vm_id: str) -> None:
        self.registry.remove(vm_id, reason="user-delete")
        ctx.vm_state = [v for v in ctx.vm_state if v.vm_id != vm_id]
        self._default_host.remove_vm(vm_id)
        if vm_id in ctx.vm_queues:
            del ctx.vm_queues[vm_id]
        if vm_id in ctx.vm_busy:
            del ctx.vm_busy[vm_id]

    def _handle_scale_out(self, ctx: SimulationContext) -> None:
        if len([v for v in ctx.vm_state if v.state != VMState.TERMINATED]) < MAX_VMS:
            new_vm = self._provision_vm(ctx)
            if new_vm:
                # Add in PROVISIONING state
                new_vm.state = VMState.PROVISIONING
                ctx.vm_state.append(new_vm)
                self.registry.register(new_vm)
                self._default_host.vms.append(new_vm)
                
                # Schedule VM_PROVISIONED with 7.5s delay
                ctx.enqueue_event(ctx.current_time + 7.5, EventType.VM_PROVISIONED, {"vm_id": new_vm.vm_id})

    def _handle_scale_in(self, ctx: SimulationContext) -> None:
        candidates = [v for v in ctx.vm_state if v.state != VMState.TERMINATED and v.name.startswith("autoscale-")]
        if candidates:
            target = sorted(candidates, key=lambda v: (v.cpu_utilization, v.vm_id))[0]
            self._terminate_vm(ctx, target.vm_id)

    def _update_metrics(self, ctx: SimulationContext, rps: int) -> None:
        active = [v for v in ctx.vm_state if v.state in {VMState.RUNNING, VMState.OVERLOADED, VMState.SCALING}]
        ctx.metrics = self._metrics_engine.compute(rps, active)
        
        # Override latency with our precise event-driven calculation
        if ctx.tick_latencies:
            avg_latency = sum(ctx.tick_latencies) / len(ctx.tick_latencies)
            ctx.metrics.latency_ms = round(avg_latency, 2)
        else:
            # If no requests processed, use base latency or keep metrics engine's estimate
            # But strictly, if idle, it should be base.
            if rps == 0 and sum(len(q) for q in ctx.vm_queues.values()) == 0:
                ctx.metrics.latency_ms = BASE_LATENCY_MS
            
        # Update queue depth to be sum of all VM queues
        total_queue = sum(len(q) for q in ctx.vm_queues.values())
        ctx.metrics.queue_depth = float(total_queue)
        ctx.queue_state = float(total_queue)
        
        self._metrics_engine.apply_to_vms(active, ctx.metrics)

    def _persist(self, ctx: SimulationContext) -> None:
        from app import db
        from app.models.resources import VirtualMachine, ResourceStatus
        _map = {VMState.RUNNING: ResourceStatus.RUNNING, VMState.OVERLOADED: ResourceStatus.OVERLOADED,
                VMState.SCALING: ResourceStatus.SCALING, VMState.TERMINATED: ResourceStatus.TERMINATED}
        for svm in ctx.vm_state:
            vm = VirtualMachine.query.filter_by(instance_id=svm.vm_id).first()
            if vm:
                if _map.get(svm.state): vm.status = _map[svm.state]
                vm.cpu_utilization, vm.memory_utilization = round(svm.cpu_utilization, 2), round(svm.memory_utilization, 2)
                vm.total_runtime_hours = (vm.total_runtime_hours or 0.0) + self.TICK_INTERVAL / 3600.0
        try: db.session.commit()
        except: db.session.rollback()

    def _emit_tick(self, socketio, ctx: SimulationContext, rps: int) -> None:
        payload = {"tick": ctx.current_tick + 1, "total_ticks": ctx.total_ticks, "scenario_id": ctx.scenario_id,
                   "org_id": ctx.org_id, "rps": rps, "metrics": ctx.to_dict()["metrics"]}
        socketio.emit("scenario_tick", payload, room=f"org_{ctx.org_id}", namespace="/metrics")

    def _emit_complete(self, socketio, ctx: SimulationContext) -> None:
        self._update_metrics(ctx, 0)
        payload = {"scenario_id": ctx.scenario_id, "org_id": ctx.org_id, "total_ticks": ctx.total_ticks, "final_metrics": ctx.to_dict()["metrics"]}
        socketio.emit("scenario_complete", payload, room=f"org_{ctx.org_id}", namespace="/metrics")

    def _provision_vm(self, ctx: SimulationContext) -> Optional[SimVM]:
        from app import db
        from app.models.resources import VirtualMachine, ResourceStatus
        spec = {"vcpu": 2, "memory_gb": 4, "hourly_rate": 0.0464}
        
        # Deterministic ID and IP for strict DES validation
        # Uses org_id and event_counter to ensure uniqueness and reproducibility
        iid = f"i-auto-{ctx.org_id}-{ctx.event_counter:04d}"
        ip = f"10.{ctx.org_id % 256}.{(ctx.event_counter // 256) % 256}.{ctx.event_counter % 256 + 1}"
        
        vm = VirtualMachine(organization_id=ctx.org_id, name=f"autoscale-{iid[7:]}", instance_id=iid,
                            instance_type="t2.medium", status=ResourceStatus.RUNNING, vcpu=spec["vcpu"],
                            memory_gb=spec["memory_gb"], storage_gb=8, private_ip=ip,
                            hourly_rate=spec["hourly_rate"], launched_at=datetime.now(timezone.utc))
        try:
            db.session.add(vm)
            db.session.flush()
            return SimVM(vm_id=iid, name=vm.name, vcpu=spec["vcpu"], memory_gb=spec["memory_gb"], capacity_rps=200, state=VMState.RUNNING)
        except:
            db.session.rollback()
            return None

    def _terminate_vm(self, ctx: SimulationContext, vm_id: str) -> None:
        from app import db
        from app.models.resources import VirtualMachine, ResourceStatus
        ctx.vm_state = [v for v in ctx.vm_state if v.vm_id != vm_id]
        self.registry.remove(vm_id, reason="scale-in")
        self._default_host.remove_vm(vm_id)
        vm = VirtualMachine.query.filter_by(instance_id=vm_id).first()
        if vm:
            vm.status = ResourceStatus.TERMINATED
            vm.terminated_at = datetime.now(timezone.utc)
            try: db.session.commit()
            except: db.session.rollback()

    def _seed_context_vms(self, ctx: SimulationContext) -> None:
        from app.models.resources import VirtualMachine, ResourceStatus
        vms = VirtualMachine.query.filter_by(organization_id=ctx.org_id, status=ResourceStatus.RUNNING).all() if self._app else []
        ctx.vm_state = []
        for v in vms:
            svm = self.registry.get(v.instance_id) or orm_vm_to_simvm(v)
            if not self.registry.get(v.instance_id): self.registry.register(svm)
            if svm not in self._default_host.vms: self._default_host.vms.append(svm)
            ctx.vm_state.append(svm)

    def _idle_loop(self) -> None:
        if not self._app: return
        with self._app.app_context():
            while self._idle_running and not self._idle_stop.is_set():
                try:
                    from app.models.resources import VirtualMachine, ResourceStatus
                    for v in VirtualMachine.query.filter_by(status=ResourceStatus.RUNNING).all():
                        if not self.registry.get(v.instance_id):
                            svm = orm_vm_to_simvm(v)
                            self.registry.register(svm)
                            if svm not in self._default_host.vms: self._default_host.vms.append(svm)
                except: pass
                self._idle_stop.wait(5.0)

# Removed local instantiation: simulation_engine is now a singleton in app/__init__.py

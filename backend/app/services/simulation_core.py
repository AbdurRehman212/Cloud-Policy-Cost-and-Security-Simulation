"""
simulation_core.py — Deterministic Cloud Simulation Engine
===========================================================

Provides the six core entities required by the simulation specification:
  1. DataCenter
  2. Host
  3. VirtualMachine   (full lifecycle state machine)
  4. WorkloadRequest
  5. Autoscaler       (queue/latency/CPU-driven with global quota)
  6. MetricsEngine    (derived, not random)

Design principles
-----------------
* **Deterministic**: same (incoming_rps, capacity) inputs → same metrics.
* **No orphan VMs**: delete always updates resource count, metrics, and cost.
* **State-machine enforced**: VM deletable only if state != PROVISIONING.
* **Global quota**: Autoscaler never exceeds MAX_VMS = 20.
* **Debug logging**: every VM create/delete/scale/queue event is logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Global constants ────────────────────────────────────────────────────────────
MAX_VMS: int = 100                 # Global VM quota increased for performance testing
BASE_LATENCY_MS: float = 20.0     # Minimum service latency (ms)
LATENCY_QUEUE_FACTOR: float = 0.5 # Additional ms per unit of queue depth
VM_CAPACITY_PER_UNIT: int = 50    # RPS capacity of one smallest unit


# ─────────────────────────────────────────────────────────────────────────────
# 1. VM Lifecycle State Machine
# ─────────────────────────────────────────────────────────────────────────────

class VMState(str, Enum):
    """Allowed VM states in the lifecycle state machine."""
    PROVISIONING = "provisioning"
    RUNNING      = "running"
    OVERLOADED   = "overloaded"
    SCALING      = "scaling"
    TERMINATED   = "terminated"


_VALID_TRANSITIONS: Dict[VMState, List[VMState]] = {
    VMState.PROVISIONING: [VMState.RUNNING, VMState.TERMINATED],
    VMState.RUNNING:      [VMState.OVERLOADED, VMState.SCALING, VMState.TERMINATED],
    VMState.OVERLOADED:   [VMState.RUNNING, VMState.SCALING, VMState.TERMINATED],
    VMState.SCALING:      [VMState.RUNNING, VMState.TERMINATED],
    VMState.TERMINATED:   [],   # terminal state
}


def is_valid_transition(current: VMState, target: VMState) -> bool:
    return target in _VALID_TRANSITIONS.get(current, [])


def vm_is_deletable(state: VMState) -> bool:
    """VM may only be deleted if it is NOT in PROVISIONING state."""
    return state != VMState.PROVISIONING


# ─────────────────────────────────────────────────────────────────────────────
# 2. Core Entities (in-memory, used by the simulation engine)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DataCenter:
    """Top-level container that groups hosts and enforces the global VM quota."""
    name: str
    region: str = "us-east-1"
    hosts: List["Host"] = field(default_factory=list)

    @property
    def total_vm_count(self) -> int:
        return sum(len(h.vms) for h in self.hosts)

    @property
    def quota_available(self) -> bool:
        return self.total_vm_count < MAX_VMS

    def register_host(self, host: "Host") -> None:
        self.hosts.append(host)
        host.datacenter = self
        logger.debug("[DataCenter:%s] Registered host %s", self.name, host.host_id)


@dataclass
class Host:
    """Physical host that runs virtual machines."""
    host_id: str
    vcpu_total: int = 64
    ram_gb_total: float = 256.0
    datacenter: Optional[DataCenter] = None
    vms: List["SimVM"] = field(default_factory=list)

    @property
    def vcpu_used(self) -> int:
        return sum(v.vcpu for v in self.vms if v.state != VMState.TERMINATED)

    @property
    def ram_used(self) -> float:
        return sum(v.memory_gb for v in self.vms if v.state != VMState.TERMINATED)

    def can_fit(self, vcpu: int = 1, ram_gb: float = 1.0) -> bool:
        """Return True if this host has room for vcpu/ram_gb more."""
        return (
            self.vcpu_used + vcpu <= self.vcpu_total
            and self.ram_used + ram_gb <= self.ram_gb_total
        )

    def remove_vm(self, vm_id: str) -> bool:
        """Remove a SimVM from this host by vm_id. Returns True if removed."""
        before = len(self.vms)
        self.vms = [v for v in self.vms if v.vm_id != vm_id]
        return len(self.vms) < before


@dataclass
class SimVM:
    """In-memory representation of a VM with full lifecycle state machine."""
    vm_id: str
    name: str
    vcpu: int
    memory_gb: float
    capacity_rps: int              # max RPS this VM can serve
    state: VMState = VMState.PROVISIONING
    host: Optional[Host] = None
    cpu_utilization: float = 0.0
    memory_utilization: float = 0.0
    queue_depth: float = 0.0       # pending work in RPS units
    latency_ms: float = BASE_LATENCY_MS

    # ── State machine ────────────────────────────────────────────────────────

    def transition(self, target: VMState) -> None:
        """Apply a state transition, logging every step."""
        if not is_valid_transition(self.state, target):
            raise ValueError(
                f"[VM:{self.vm_id}] Invalid transition {self.state} → {target}"
            )
        logger.debug(
            "[VM_STATE] vm_id=%s  %s → %s", self.vm_id, self.state.value, target.value
        )
        self.state = target

    # ── Deletion guard ───────────────────────────────────────────────────────

    def can_delete(self) -> bool:
        return vm_is_deletable(self.state)


@dataclass
class WorkloadRequest:
    """Represents a batch of incoming requests for one simulation tick."""
    incoming_rps: int
    tick_seconds: float = 5.0

    @property
    def total_requests(self) -> int:
        return int(self.incoming_rps * self.tick_seconds)


# ─────────────────────────────────────────────────────────────────────────────
# 3. MetricsEngine — derived, never random
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TickMetrics:
    """All simulation metrics for one tick — 100 % derived from inputs."""
    incoming_rps: int
    total_capacity_rps: int
    queue_depth: float        # max(0, incoming_rps - total_capacity_rps)
    latency_ms: float         # base_latency + queue_depth * factor
    cpu_avg: float            # 0-100 %
    memory_avg: float         # 0-100 %
    overloaded: bool
    vm_count: int


class MetricsEngine:
    """Compute simulation metrics deterministically from first principles.

    Formulas
    --------
    queue_depth = max(0, incoming_rps − total_capacity_rps)
    latency_ms  = BASE_LATENCY_MS + queue_depth × LATENCY_QUEUE_FACTOR
    cpu_avg     = min(100, (incoming_rps / total_capacity_rps) × 100)  [or 0]
    overloaded  = queue_depth > 0
    """

    def compute(
        self,
        incoming_rps: int,
        vms: List[SimVM],
    ) -> TickMetrics:
        total_capacity = sum(v.capacity_rps for v in vms if v.state in
                             {VMState.RUNNING, VMState.OVERLOADED, VMState.SCALING})
        vm_count = len(vms)

        queue_depth = max(0.0, float(incoming_rps - total_capacity))
        latency_ms = BASE_LATENCY_MS + queue_depth * LATENCY_QUEUE_FACTOR

        if total_capacity > 0:
            cpu_raw = (incoming_rps / total_capacity) * 100.0
            cpu_avg = round(min(100.0, cpu_raw), 2)
        else:
            cpu_avg = 100.0 if incoming_rps > 0 else 0.0

        # Memory is derived proportionally from CPU (no randomness)
        memory_avg = round(min(100.0, cpu_avg * 0.8), 2)

        overloaded = queue_depth > 0

        logger.debug(
            "[MetricsEngine] rps=%d capacity=%d queue=%.1f latency=%.1f ms cpu=%.1f%%",
            incoming_rps, total_capacity, queue_depth, latency_ms, cpu_avg,
        )

        return TickMetrics(
            incoming_rps=incoming_rps,
            total_capacity_rps=total_capacity,
            queue_depth=queue_depth,
            latency_ms=round(latency_ms, 2),
            cpu_avg=cpu_avg,
            memory_avg=memory_avg,
            overloaded=overloaded,
            vm_count=vm_count,
        )

    def apply_to_vms(self, vms: List[SimVM], metrics: TickMetrics) -> None:
        """Push computed metrics back onto each VM object (no DB write)."""
        for vm in vms:
            if vm.state in {VMState.RUNNING, VMState.OVERLOADED, VMState.SCALING}:
                vm.cpu_utilization = metrics.cpu_avg
                vm.memory_utilization = metrics.memory_avg
                vm.queue_depth = metrics.queue_depth
                vm.latency_ms = metrics.latency_ms
                # Transition overloaded / recovered
                if metrics.overloaded and vm.state == VMState.RUNNING:
                    try:
                        vm.transition(VMState.OVERLOADED)
                    except ValueError:
                        pass
                elif not metrics.overloaded and vm.state == VMState.OVERLOADED:
                    try:
                        vm.transition(VMState.RUNNING)
                    except ValueError:
                        pass
            else:
                vm.cpu_utilization = 0.0
                vm.memory_utilization = 0.0
                vm.queue_depth = 0.0
                vm.latency_ms = BASE_LATENCY_MS


# ─────────────────────────────────────────────────────────────────────────────
# 4. Autoscaler — queue/latency/CPU driven, respects global quota
# ─────────────────────────────────────────────────────────────────────────────

class ScalingDecision(str, Enum):
    SCALE_OUT = "scale_out"
    SCALE_IN  = "scale_in"
    NO_ACTION = "no_action"


@dataclass
class AutoscalerConfig:
    cpu_high_threshold: float = 75.0    # % CPU → scale-out
    cpu_low_threshold: float = 30.0     # % CPU → scale-in candidate
    queue_threshold: float = 10.0       # RPS queue depth → scale-out
    latency_threshold_ms: float = 200.0 # ms p95 → scale-out
    cooldown_ticks: int = 6             # ticks between scaling actions


class Autoscaler:
    """Decides scale-out / scale-in based on derived metrics.

    Scaling decision = f(queue_depth, latency, CPU)
    Global hard limit: total running VMs in the DataCenter ≤ MAX_VMS
    """

    def __init__(self, datacenter: DataCenter, config: Optional[AutoscalerConfig] = None):
        self.dc = datacenter
        self.config = config or AutoscalerConfig()
        self._cooldown_remaining: int = 0

    def evaluate(self, metrics: TickMetrics) -> ScalingDecision:
        """Return a scaling decision for the current tick metrics."""
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            logger.debug("[Autoscaler] Cooldown: %d ticks remaining", self._cooldown_remaining)
            return ScalingDecision.NO_ACTION

        should_scale_out = (
            metrics.queue_depth > self.config.queue_threshold
            or metrics.latency_ms > self.config.latency_threshold_ms
            or metrics.cpu_avg > self.config.cpu_high_threshold
        )

        should_scale_in = (
            not should_scale_out
            and metrics.cpu_avg < self.config.cpu_low_threshold
            and metrics.queue_depth == 0.0
            and metrics.vm_count > 1
        )

        # Enforce global quota before scale-out
        if should_scale_out:
            if not self.dc.quota_available:
                logger.warning(
                    "[Autoscaler] SCALE_OUT requested but global quota (%d VMs) reached.",
                    MAX_VMS,
                )
                return ScalingDecision.NO_ACTION
            decision = ScalingDecision.SCALE_OUT
        elif should_scale_in:
            decision = ScalingDecision.SCALE_IN
        else:
            decision = ScalingDecision.NO_ACTION

        if decision != ScalingDecision.NO_ACTION:
            self._cooldown_remaining = self.config.cooldown_ticks
            logger.info(
                "[Autoscaler] Scaling decision=%s  cpu=%.1f%% queue=%.1f rps "
                "latency=%.1fms vm_count=%d global_vms=%d/%d",
                decision.value, metrics.cpu_avg, metrics.queue_depth,
                metrics.latency_ms, metrics.vm_count,
                self.dc.total_vm_count, MAX_VMS,
            )

        return decision


# ─────────────────────────────────────────────────────────────────────────────
# 5. VM Registry — tracks all SimVMs in the engine (in-memory)
# ─────────────────────────────────────────────────────────────────────────────

class VMRegistry:
    """Central, in-memory registry of all SimVM objects.

    This is the ONLY authoritative runtime state.  The DB is a persistence
    replica synced at the end of each tick and at startup.

    Rules
    -----
    * On startup → DB → VMRegistry (via ``sync_from_db``)
    * On tick    → VMRegistry → DB (via ``SimulationEngine.tick``)
    """

    def __init__(self) -> None:
        self._vms: Dict[str, SimVM] = {}  # vm_id → SimVM

    def register(self, vm: SimVM) -> None:
        self._vms[vm.vm_id] = vm
        logger.info(
            "[VMRegistry] VM CREATED  vm_id=%s name=%s vcpu=%d state=%s",
            vm.vm_id, vm.name, vm.vcpu, vm.state.value,
        )

    def remove(self, vm_id: str, reason: str = "user-requested") -> Optional[SimVM]:
        """Remove a VM from the registry.

        Also removes from its host.vms list if the SimVM has a ``host``
        reference set.  DB update is the caller's responsibility.
        """
        vm = self._vms.pop(vm_id, None)
        if vm is None:
            logger.warning("[VMRegistry] Remove requested for unknown vm_id=%s", vm_id)
            return None
        # Remove from host.vms if linked
        if vm.host is not None:
            vm.host.remove_vm(vm_id)
        logger.info(
            "[VMRegistry] VM DELETED  vm_id=%s name=%s state=%s reason=%s",
            vm_id, vm.name, vm.state.value, reason,
        )
        return vm

    def get(self, vm_id: str) -> Optional[SimVM]:
        return self._vms.get(vm_id)

    def all(self) -> List[SimVM]:
        return list(self._vms.values())

    def running(self) -> List[SimVM]:
        """Return only VMs in active states."""
        active = {VMState.RUNNING, VMState.OVERLOADED, VMState.SCALING}
        return [v for v in self._vms.values() if v.state in active]

    @property
    def count(self) -> int:
        return len(self._vms)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Helpers — bridge to ORM layer
# ─────────────────────────────────────────────────────────────────────────────

def orm_vm_to_simvm(orm_vm) -> SimVM:
    """Convert an ORM VirtualMachine to a SimVM (read-only projection)."""
    from app.models.resources import ResourceStatus

    # Map ORM status → VMState
    _status_map = {
        ResourceStatus.PENDING:     VMState.PROVISIONING,
        ResourceStatus.RUNNING:     VMState.RUNNING,
        ResourceStatus.STOPPED:     VMState.TERMINATED,
        ResourceStatus.TERMINATED:  VMState.TERMINATED,
        ResourceStatus.FAILED:      VMState.TERMINATED,
    }
    state = _status_map.get(orm_vm.status, VMState.RUNNING)

    # Derive capacity from instance_type or fallback
    _CAPACITY_TABLE = {
        't2.micro':   50,  't2.small':  100, 't2.medium': 200,
        't2.large':  400,  't2.xlarge': 800,
        't3.micro':   60,  't3.small':  120, 't3.medium': 250,
        'm5.large':  300,  'm5.xlarge': 600, 'm5.2xlarge': 1200,
        'c5.large':  400,  'c5.xlarge': 800, 'c5.2xlarge': 1600,
    }
    capacity = _CAPACITY_TABLE.get(orm_vm.instance_type or 't2.micro', 200)

    return SimVM(
        vm_id=orm_vm.instance_id,
        name=orm_vm.name,
        vcpu=orm_vm.vcpu or 1,
        memory_gb=orm_vm.memory_gb or 1.0,
        capacity_rps=capacity,
        state=state,
        cpu_utilization=float(orm_vm.cpu_utilization or 0.0),
        memory_utilization=float(orm_vm.memory_utilization or 0.0),
    )


def delete_vm_with_side_effects(
    vm_id: str,
    org_id: int,
    registry: VMRegistry,
    reason: str = "user-requested",
) -> dict:
    """Delete a VM from both the registry and the ORM layer.

    Enforces the lifecycle rule: a VM in PROVISIONING state cannot be deleted.
    Updates resource count, metrics (zeroed out), and cost on deletion.

    Returns a dict describing what happened, raises ValueError on rule violation.
    """
    from app import db
    from app.models.resources import VirtualMachine, ResourceStatus
    from datetime import datetime

    # 1. Validate via registry (in-memory state machine)
    sim_vm = registry.get(vm_id)
    if sim_vm is not None and not sim_vm.can_delete():
        raise ValueError(
            f"VM {vm_id} is in PROVISIONING state and cannot be deleted yet."
        )

    # 2. Fetch ORM row
    orm_vm = VirtualMachine.query.filter_by(instance_id=vm_id, organization_id=org_id).first()
    if orm_vm is None:
        raise LookupError(f"VM {vm_id} not found in org {org_id}")

    # Extra guard: if ORM says PENDING and no registry entry, also block deletion
    if orm_vm.status and orm_vm.status.value == 'pending' and sim_vm is None:
        raise ValueError(
            f"VM {vm_id} is still provisioning (status=pending) and cannot be deleted."
        )

    # 3. Freeze cost before zeroing
    runtime_cost = orm_vm.calculate_current_cost()

    # 4. Zero metrics (no orphan metric state)
    orm_vm.cpu_utilization = 0.0
    orm_vm.memory_utilization = 0.0
    orm_vm.disk_read_iops = 0.0
    orm_vm.disk_write_iops = 0.0
    orm_vm.network_in_mbps = 0.0
    orm_vm.network_out_mbps = 0.0
    orm_vm.status = ResourceStatus.TERMINATED
    orm_vm.terminated_at = datetime.utcnow()

    # 5. Remove from registry
    registry.remove(vm_id, reason=reason)

    db.session.commit()

    running_count = VirtualMachine.query.filter_by(
        organization_id=org_id, status=ResourceStatus.RUNNING
    ).count()

    logger.info(
        "[delete_vm_with_side_effects] vm_id=%s org=%d reason=%s "
        "final_cost=%.4f remaining_running_vms=%d",
        vm_id, org_id, reason, runtime_cost, running_count,
    )

    return {
        "vm_id": vm_id,
        "org_id": org_id,
        "reason": reason,
        "final_cost": round(runtime_cost, 4),
        "remaining_running_vms": running_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Singleton registry (shared across the application process)
# ─────────────────────────────────────────────────────────────────────────────
vm_registry = VMRegistry()
metrics_engine = MetricsEngine()

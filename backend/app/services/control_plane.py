"""Module 3 — MAPE control plane for organization resource snapshots.

Monitor → Analyze → Plan → Execute loop over the in-memory simulation state
exposed by `resource_simulator`. Extends (never removes) existing response
keys so the frontend continues to work unchanged.
"""

import math
import random
import string
import threading
import time
from datetime import datetime

from app import db
from app.models.resources import VirtualMachine, Database, ResourceStatus

# ── Snapshot cache — updated by background thread, read by API ───────────────
_snapshot_cache: dict[int, dict] = {}
_cache_lock = threading.Lock()
_cache_ttl = 2.0  # seconds between recomputes

# In-memory storage for CPU history per organization (max 5 entries)
cpu_history: dict[int, list] = {}

# EMA smoothing parameters
alpha = 0.3
ema_cpu: dict[int, float] = {}
ema_memory: dict[int, float] = {}

# Alert state storage (CloudWatch-style state transitions)
alert_states = {}  # org_id -> { alert_type: state }

# Scaling state storage for cooldown and capacity control
scaling_state = {}  # org_id -> { last_action_time, capacity }

# ── MAPE thresholds ─────────────────────────────────────────────────────────
_QUEUE_ALARM_MS = 1000.0        # 1s of backlog → queue ALARM
_LATENCY_P95_ALARM_MS = 500.0   # p95 SLO (ms) — also used for target BPI
_LATENCY_P95_CRITICAL_MS = 1500.0
_TARGET_UTIL_PCT = 60
_SCALE_COOLDOWN_S = 10
_CAPACITY_MIN = 1
_CAPACITY_MAX = 10
# Scale-in hysteresis: only scale in when BPI < target × (1 − SCALE_IN_TOLERANCE)
_SCALE_IN_BPI_RATIO = 0.7       # AWS recommended: 70% of target triggers scale-in
# Hard step cap: never add/remove more than this many instances per evaluation.
_MAX_STEP = 3

# ── VM provisioning helpers for autoscaling execution ──────────────────────────

_INSTANCE_SPECS = {
    "t2.micro":  {"vcpu": 1, "memory_gb": 1,  "baseline_cpu": 0.20, "baseline_memory": 0.30, "hourly_rate": 0.0116},
    "t2.small":  {"vcpu": 1, "memory_gb": 2,  "baseline_cpu": 0.40, "baseline_memory": 0.50, "hourly_rate": 0.0230},
    "t2.medium": {"vcpu": 2, "memory_gb": 4,  "baseline_cpu": 0.60, "baseline_memory": 0.70, "hourly_rate": 0.0464},
    "t2.large":  {"vcpu": 2, "memory_gb": 8,  "baseline_cpu": 0.75, "baseline_memory": 0.80, "hourly_rate": 0.0928},
}


def _generate_instance_id(prefix: str = "i") -> str:
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=17))
    return f"{prefix}-{suffix}"


def _create_autoscale_vm(org_id: int, instance_type: str, base_rps: int, pattern: str) -> VirtualMachine:
    """Create and commit a RUNNING VM for autoscaling execution."""
    current_count = VirtualMachine.query.filter_by(organization_id=org_id, status=ResourceStatus.RUNNING).count()
    if current_count >= 20:
        raise Exception("Organization has reached the maximum allowed limit of 20 VMs.")
    spec = _INSTANCE_SPECS.get(instance_type, _INSTANCE_SPECS["t2.medium"])
    vm = VirtualMachine(
        organization_id=org_id,
        name=f"autoscale-{_generate_instance_id('i')[:8]}",
        instance_id=_generate_instance_id('i'),
        instance_type=instance_type,
        status=ResourceStatus.RUNNING,
        vcpu=spec["vcpu"],
        memory_gb=spec["memory_gb"],
        storage_gb=8,
        private_ip=f"10.0.{random.randint(0,255)}.{random.randint(1,254)}",
        cpu_utilization=round(spec["baseline_cpu"] * 100, 2),
        memory_utilization=round(spec["baseline_memory"] * 100, 2),
        hourly_rate=spec["hourly_rate"],
        total_runtime_hours=0.0,
        requests_per_second=base_rps,
        workload_pattern=pattern,
        launched_at=datetime.utcnow(),
    )
    db.session.add(vm)
    db.session.commit()
    return vm


def _terminate_autoscale_vm(org_id: int) -> bool:
    """Terminate one autoscale-created VM (lowest utilisation first). Returns True if a VM was terminated."""
    candidates = (
        VirtualMachine.query
        .filter(VirtualMachine.organization_id == org_id)
        .filter(VirtualMachine.status == ResourceStatus.RUNNING)
        .filter(VirtualMachine.name.like("autoscale-%"))
        .order_by(VirtualMachine.cpu_utilization.asc())
        .all()
    )
    if not candidates:
        return False
    vm = candidates[0]
    vm.status = ResourceStatus.TERMINATED
    vm.terminated_at = datetime.utcnow()
    db.session.commit()
    # Remove from simulator in-memory state so it stops contributing to queue/latency.
    try:
        from flask import current_app
        sim = getattr(current_app, 'simulator', None)
        if sim and hasattr(sim, '_vm_des'):
            sim._vm_des.pop(vm.instance_id, None)
            sim._vm_queue.pop(vm.instance_id, None)
            sim._vm_dropped.pop(vm.instance_id, None)
            sim.vm_latency_samples.pop(vm.instance_id, None)
            sim.vm_rps_history.pop(vm.instance_id, None)
            sim.vm_metric_history.pop(vm.instance_id, None)
    except Exception:
        pass
    return True


def _workload_snapshot_for(org_id: int) -> dict:
    """Pull the simulator's per-org queue/latency aggregate. Safe on no-sim."""
    try:
        from flask import current_app
        sim = getattr(current_app, 'simulator', None)
        if sim is None or not hasattr(sim, 'get_org_workload_snapshot'):
            return {}
        return sim.get_org_workload_snapshot(org_id) or {}
    except Exception:
        # Never let monitoring errors propagate into the request path.
        return {}


def _topology_for(org_id: int) -> dict:
    """Build the VM→Host→Datacenter view for Module 1 §5."""
    try:
        from app.services.infrastructure import aggregate_via_topology
        return aggregate_via_topology(org_id)
    except Exception:
        return {}


def get_org_snapshot(org_id: int, use_cache: bool = True) -> dict:
    """Return the latest computed snapshot for an org.

    By default reads from the in-memory cache (updated every ~2 s by the
    background control-plane loop). Set use_cache=False to force a fresh
    computation (used by the cache-refresh path itself).
    """
    if use_cache:
        with _cache_lock:
            cached = _snapshot_cache.get(org_id)
            if cached is not None:
                return cached
    return _compute_org_snapshot(org_id)


def _compute_org_snapshot(org_id: int) -> dict:
    """Get current organization resource snapshot.
    
    Queries the database once for a consistent snapshot and computes metrics.
    
    Args:
        org_id: Organization ID
        
    Returns:
        Dict with keys:
            - total_vms: Total non-terminated VMs
            - running_vms: Total running VMs
            - cpu_avg: Weighted average CPU utilization of running VMs (0-100)
            - memory_avg: Average memory utilization of running VMs (0-100)
    """
    # Single DB query for all VMs in organization
    vms = VirtualMachine.query.filter_by(
        organization_id=org_id,
    ).filter(VirtualMachine.status != ResourceStatus.TERMINATED).all()
    
    # Compute total_vms from queried list
    total_vms = len(vms)
    
    # Filter running VMs in memory (separate from valid_vms for accurate counting)
    running_vms = [vm for vm in vms if vm.status == ResourceStatus.RUNNING]
    running_vms_count = len(running_vms)
    
    # Filter VMs with valid metrics for aggregation (subset of running_vms)
    valid_vms = [
        vm for vm in running_vms
        if vm.cpu_utilization is not None and vm.memory_utilization is not None
    ]
    
    # BPI defaults — overwritten in the valid_vms branch if simulation is active.
    bpi: float = 0.0
    target_bpi: float = 0.0
    avg_service_time_ms: float = 5.0

    # Compute metrics only from valid VMs
    if valid_vms:
        # Weight CPU by vcpu for realistic cross-instance-type averaging
        total_vcpu = sum(float(vm.vcpu or 1) for vm in valid_vms)
        if total_vcpu > 0:
            weighted_cpu_sum = sum(
                float(vm.cpu_utilization or 0) * float(vm.vcpu or 1)
                for vm in valid_vms
            )
            cpu_avg = weighted_cpu_sum / total_vcpu
        else:
            cpu_avg = 0.0
        
        # Memory computed normally (unweighted)
        memory_avg = sum(float(vm.memory_utilization or 0) for vm in valid_vms) / len(valid_vms)
        
        # Clamp values to 0-100 range
        cpu_avg = max(0.0, min(100.0, cpu_avg))
        memory_avg = max(0.0, min(100.0, memory_avg))
        
        # EMA smoothing for CPU
        if org_id not in ema_cpu:
            ema_cpu[org_id] = cpu_avg
        else:
            ema_cpu[org_id] = (alpha * cpu_avg) + ((1 - alpha) * ema_cpu[org_id])
        smoothed_cpu = ema_cpu[org_id]
        
        # Replace cpu_avg with smoothed for all downstream usage
        cpu_avg = smoothed_cpu
        
        # EMA smoothing for memory
        if org_id not in ema_memory:
            ema_memory[org_id] = memory_avg
        else:
            ema_memory[org_id] = (alpha * memory_avg) + ((1 - alpha) * ema_memory[org_id])
        smoothed_memory = ema_memory[org_id]
        
        # Replace memory_avg with smoothed for all downstream usage
        memory_avg = smoothed_memory
        
        # Initialize bottleneck variables
        raw_max_cpu = 0
        raw_max_memory = 0
        smoothed_max_cpu = 0
        smoothed_max_memory = 0
        
        # Bottleneck detection (hybrid: raw max + smoothed average)
        raw_max_cpu = max(float(vm.cpu_utilization or 0) for vm in valid_vms)
        raw_max_memory = max(float(vm.memory_utilization or 0) for vm in valid_vms)
        
        smoothed_max_cpu = (0.7 * raw_max_cpu) + (0.3 * smoothed_cpu)
        smoothed_max_memory = (0.7 * raw_max_memory) + (0.3 * smoothed_memory)
        
        cpu_bottleneck = smoothed_max_cpu > 85
        memory_bottleneck = smoothed_max_memory > 90
        
        max_cpu = raw_max_cpu
        max_memory = raw_max_memory
        
        # System pressure assessment
        if cpu_bottleneck or memory_bottleneck:
            system_pressure = "high"
        elif smoothed_cpu > 70:
            system_pressure = "moderate"
        else:
            system_pressure = "normal"
        
        # Trend detection
        history = cpu_history.get(org_id, [])

        if len(history) < 4:
            cpu_trend = "stable"
        else:
            recent = history[-3:]
            previous = history[-4:-1]

            recent_avg = sum(recent) / len(recent)
            previous_avg = sum(previous) / len(previous)

            if recent_avg > previous_avg + 3:
                cpu_trend = "increasing"
            elif recent_avg < previous_avg - 3:
                cpu_trend = "decreasing"
            else:
                cpu_trend = "stable"
        
        # Update CPU history (keep max 5 entries) - use smoothed value
        history.append(smoothed_cpu)
        if len(history) > 5:
            history.pop(0)
        cpu_history[org_id] = history
        
        # System risk assessment
        if cpu_trend == "increasing" and smoothed_cpu > 60:
            system_risk = "rising"
        else:
            system_risk = "normal"
        
        # Alert engine with CloudWatch-style state transitions
        prev_states = alert_states.get(org_id, {}).copy()
        org_alerts = {}
        
        # Define insufficient data conditions
        cpu_insufficient = (
            total_vms == 0
            or len(cpu_history.get(org_id, [])) < 3
        )
        memory_insufficient = (
            total_vms == 0
            or len(cpu_history.get(org_id, [])) < 3
        )
        
        # CPU alert state
        if cpu_insufficient:
            cpu_state = "INSUFFICIENT_DATA"
        elif cpu_bottleneck:
            cpu_state = "ALARM"
        else:
            cpu_state = "OK"
        org_alerts["cpu"] = cpu_state
        
        # Memory alert state
        if memory_insufficient:
            memory_state = "INSUFFICIENT_DATA"
        elif memory_bottleneck:
            memory_state = "ALARM"
        else:
            memory_state = "OK"
        org_alerts["memory"] = memory_state
        
        # Trend alert state
        if cpu_trend == "stable" and len(cpu_history.get(org_id, [])) < 3:
            trend_state = "INSUFFICIENT_DATA"
        elif system_risk == "rising":
            trend_state = "ALARM"
        else:
            trend_state = "OK"
        org_alerts["trend"] = trend_state
        
        # Track state transitions
        transitions = []
        for key, new_state in org_alerts.items():
            old_state = prev_states.get(key)
            if old_state and old_state != new_state:
                transitions.append({
                    "type": key,
                    "from": old_state,
                    "to": new_state
                })
        
        # Save state
        alert_states[org_id] = org_alerts
        
        # ── Module 3: MAPE — MONITOR (pull sim workload snapshot) ──────────────
        workload = _workload_snapshot_for(org_id)
        queue_total_ms = float(workload.get('queue_total_ms', 0.0) or 0.0)
        latency_avg_ms = float(workload.get('latency_avg_ms', 0.0) or 0.0)
        p95_latency_ms = float(workload.get('p95_latency_ms', 0.0) or 0.0)
        # Bug #4 fix: ALARM logic uses RECENT drops (per evaluation cycle), not
        # cumulative — otherwise drops_state stays ALARM forever and scale-in
        # is permanently blocked. Cumulative remains for accounting only.
        dropped_recent = int(workload.get('dropped_recent_total', 0) or 0)
        dropped_total = int(workload.get('dropped_requests_total', 0) or 0)
        overloaded_vms = int(workload.get('overloaded_vms', 0) or 0)
        # Bug #2 fix: BPI must use the actual instance count (vm_count), not
        # the autoscaler's abstract capacity scalar — those diverge because the
        # simulator does not actually launch new VMs when capacity bumps.
        vm_count = int(workload.get('vm_count', 0) or 0)

        # ── Module 3: MAPE — ANALYZE (queue/latency/drops alerts) ───────────
        # Queue alert: ALARM when backlog > 1s of work; INSUFFICIENT on cold sim.
        if workload.get('vm_count', 0) == 0:
            queue_state = "INSUFFICIENT_DATA"
        elif queue_total_ms > _QUEUE_ALARM_MS:
            queue_state = "ALARM"
        else:
            queue_state = "OK"
        org_alerts["queue"] = queue_state

        # Latency alert: ALARM when p95 breaches SLO.
        if workload.get('vm_count', 0) == 0:
            latency_state = "INSUFFICIENT_DATA"
        elif p95_latency_ms > _LATENCY_P95_ALARM_MS:
            latency_state = "ALARM"
        else:
            latency_state = "OK"
        org_alerts["latency"] = latency_state

        # Drops alert: rate-style — any drops in the most recent tick.
        # Bug #4 fix: was previously cumulative, which never recovered.
        drops_state = "ALARM" if dropped_recent > 0 else "OK"
        org_alerts["drops"] = drops_state

        # Re-track transitions so the newly-added alert keys are included.
        transitions = []
        for key, new_state in org_alerts.items():
            old_state = prev_states.get(key)
            if old_state and old_state != new_state:
                transitions.append({"type": key, "from": old_state, "to": new_state})
        alert_states[org_id] = org_alerts

        # ── MAPE — PLAN + EXECUTE (Task 1: AWS BPI target-tracking) ──────────
        # Import DES helpers lazily to avoid module-load cycle.
        from app.services.des_engine import (
            compute_backlog_per_instance,
            compute_target_bpi,
            compute_desired_capacity,
        )

        state = scaling_state.get(org_id, {"last_action_time": 0, "capacity": 1})
        current_time = time.time()

        # Retrieve org-level avg service time from the workload snapshot so
        # target BPI uses the actual measured distribution, not a hard-coded
        # constant. Falls back to 5 ms if the simulator hasn't reported yet.
        avg_service_time_ms = float(workload.get("avg_service_time_ms", 5.0) or 5.0)

        # PRIMARY SIGNAL: backlog-per-instance (AWS Target Tracking).
        # Bug #2 fix: denominator is vm_count (instances actually doing work),
        # not state["capacity"] (autoscaler's desired-count scalar). They
        # diverge in this simulation because scale_up bumps the scalar but
        # does not spawn real VMs — using the scalar would make BPI 'recover'
        # without any real capacity change, defeating the AWS principle:
        # "scaling metric MUST be proportional to capacity actually present".
        # Fall back to capacity scalar only when no VMs are running.
        instances_for_bpi = vm_count if vm_count > 0 else state["capacity"]
        bpi = compute_backlog_per_instance(
            queue_total_ms, avg_service_time_ms, instances_for_bpi
        )

        # TARGET: how many requests of backlog can each instance hold and still
        # drain within the latency SLO?
        # target_bpi = SLO_ms / avg_service_time_ms
        target_bpi = compute_target_bpi(_LATENCY_P95_ALARM_MS, avg_service_time_ms)

        if current_time - state["last_action_time"] < _SCALE_COOLDOWN_S:
            # Cooldown gate: Execute phase allows only one action per cooldown.
            actions = []
        else:
            actions = []
            action_taken = False

            if bpi > target_bpi and state["capacity"] < _CAPACITY_MAX:
                # SCALE OUT — proportional to overload.
                # desired = ceil(backlog_requests / target_bpi)
                # step = desired - current_capacity, clamped to [1, MAX_STEP].
                desired = compute_desired_capacity(
                    queue_total_ms, avg_service_time_ms, target_bpi
                )
                step = max(1, min(_MAX_STEP, desired - state["capacity"]))
                new_capacity = min(_CAPACITY_MAX, state["capacity"] + step)
                actual_step = new_capacity - state["capacity"]

                # Execute: create actual VMs in the database.
                created = 0
                instance_type = running_vms[0].instance_type if running_vms else "t2.medium"
                base_rps = int(running_vms[0].requests_per_second or 50) if running_vms else 50
                pattern = (running_vms[0].workload_pattern or "steady") if running_vms else "steady"
                for _ in range(actual_step):
                    try:
                        _create_autoscale_vm(org_id, instance_type, base_rps, pattern)
                        created += 1
                    except Exception:
                        db.session.rollback()
                        break

                state["capacity"] = state["capacity"] + created
                reason = (
                    f"BPI={bpi:.1f} > target={target_bpi:.1f} — "
                    f"queue={queue_total_ms:.0f}ms, p95={p95_latency_ms:.0f}ms, "
                    f"drops={dropped_total}, +{created} instance(s) created"
                )
                actions.append({
                    "type": "scale_up",
                    "capacity": state["capacity"],
                    "bpi": round(bpi, 2),
                    "target_bpi": round(target_bpi, 2),
                    "created": created,
                    "reason": reason,
                })
                state["last_action_time"] = current_time
                action_taken = True

            elif (
                bpi < target_bpi * _SCALE_IN_BPI_RATIO
                and latency_state == "OK"
                and drops_state == "OK"
                and system_risk != "rising"
                and state["capacity"] > _CAPACITY_MIN
            ):
                # SCALE IN — only when BPI is well below target AND no SLO breach.
                # Execute: terminate one autoscale-created VM.
                terminated = _terminate_autoscale_vm(org_id)
                if terminated:
                    state["capacity"] -= 1
                reason = (
                    f"BPI={bpi:.1f} < target×0.7={target_bpi * _SCALE_IN_BPI_RATIO:.1f} — "
                    f"queue stable, latency/drops OK"
                    + (" — 1 instance terminated" if terminated else " — no autoscale VM to terminate")
                )
                actions.append({
                    "type": "scale_down",
                    "capacity": state["capacity"],
                    "bpi": round(bpi, 2),
                    "target_bpi": round(target_bpi, 2),
                    "terminated": terminated,
                    "reason": reason,
                })
                state["last_action_time"] = current_time
                action_taken = True

            # Publish scaling_decision event for observability.
            if action_taken:
                try:
                    from app.services.event_bus import event_bus, EVENT_SCALING_DECISION
                    event_bus.publish(
                        EVENT_SCALING_DECISION,
                        org_id=org_id,
                        payload={"action": actions[0], "alerts": org_alerts},
                    )
                except Exception:
                    pass
        
        scaling_state[org_id] = state
        capacity = state["capacity"]
        
        # Build learning explanation based on actions
        if actions:
            action_type = actions[0].get("type")
            _bpi_val = actions[0].get("bpi", 0)
            _tgt_val = actions[0].get("target_bpi", 0)
            if action_type == "scale_up":
                learning_insight = {
                    "title": "Scale-out triggered (BPI target tracking)",
                    "what_happened": (
                        f"Backlog per instance ({_bpi_val:.1f} req/inst) exceeded "
                        f"target ({_tgt_val:.1f} req/inst derived from {_LATENCY_P95_ALARM_MS:.0f}ms SLO)."
                    ),
                    "why_it_happened": (
                        "Arrival rate exceeded drain capacity. Queue grew, pushing "
                        "waiting time above the latency SLO per instance."
                    ),
                    "system_thinking": (
                        "AWS target-tracking: desired = ceil(backlog / target_bpi). "
                        "Adding instances reduces BPI proportionally until SLO is met."
                    ),
                }
            elif action_type == "scale_down":
                learning_insight = {
                    "title": "Scale-in triggered (BPI below threshold)",
                    "what_happened": (
                        f"BPI ({_bpi_val:.1f}) fell below 70% of target "
                        f"({_tgt_val * _SCALE_IN_BPI_RATIO:.1f}). Latency and drops OK."
                    ),
                    "why_it_happened": "Demand decreased; current capacity is over-provisioned.",
                    "system_thinking": (
                        "Hysteresis band (70% of target) prevents oscillation. "
                        "Removing 1 instance conservatively."
                    ),
                }
            else:
                learning_insight = {
                    "title": "System stable",
                    "what_happened": "BPI within target band",
                    "why_it_happened": "Throughput matches demand",
                    "system_thinking": "No scaling action required",
                }
        else:
            learning_insight = {
                "title": "System stable",
                "what_happened": f"BPI={bpi:.1f}, target={target_bpi:.1f} — within band or in cooldown",
                "why_it_happened": "No SLO breach detected",
                "system_thinking": "Thermostat steady — no scaling required",
            }
        
        # Build alerts with state
        alerts = []
        
        if cpu_bottleneck:
            alerts.append({
                "type": "cpu",
                "state": cpu_state,
                "level": "critical" if cpu_state == "ALARM" else "normal",
                "message": "High CPU usage detected"
            })
        
        if memory_bottleneck:
            alerts.append({
                "type": "memory",
                "state": memory_state,
                "level": "critical" if memory_state == "ALARM" else "normal",
                "message": "High memory usage detected"
            })
        
        if system_risk == "rising":
            alerts.append({
                "type": "trend",
                "state": trend_state,
                "level": "warning" if trend_state == "ALARM" else "normal",
                "message": "CPU trend increasing"
            })
        
        alert_count = len(alerts)
    elif running_vms:
        # Running VMs exist but none have valid metrics
        cpu_avg = 0.0
        memory_avg = 0.0
        max_cpu = 0.0
        max_memory = 0.0
        smoothed_max_cpu = 0.0
        smoothed_max_memory = 0.0
        cpu_bottleneck = False
        memory_bottleneck = False
        system_pressure = "normal"
        cpu_trend = "stable"
        system_risk = "normal"
        alerts = []
        alert_count = 0
        transitions = []
        actions = []
        capacity = 1
        learning_insight = {
            "title": "System stable",
            "what_happened": "No valid metrics available",
            "why_it_happened": "Running VMs lack CPU/memory data",
            "system_thinking": "Waiting for metric collection"
        }
    else:
        cpu_avg = 0.0
        memory_avg = 0.0
        max_cpu = 0.0
        max_memory = 0.0
        smoothed_max_cpu = 0.0
        smoothed_max_memory = 0.0
        cpu_bottleneck = False
        memory_bottleneck = False
        system_pressure = "normal"
        cpu_trend = "stable"
        system_risk = "normal"
        alerts = []
        alert_count = 0
        transitions = []
        actions = []
        capacity = 1
        learning_insight = {
            "title": "System stable",
            "what_happened": "No resources detected",
            "why_it_happened": "No VMs running",
            "system_thinking": "System idle"
        }
    
    # Module 3/4: attach workload snapshot + topology without removing keys.
    workload_block = _workload_snapshot_for(org_id) if running_vms_count else {}
    topology_block = _topology_for(org_id)

    return {
        'total_vms': total_vms,
        'running_vms': running_vms_count,
        'cpu_avg': round(cpu_avg, 2),
        'memory_avg': round(memory_avg, 2),
        'max_cpu': round(max_cpu, 2),
        'max_memory': round(max_memory, 2),
        'smoothed_max_cpu': round(smoothed_max_cpu, 2),
        'smoothed_max_memory': round(smoothed_max_memory, 2),
        'cpu_bottleneck': cpu_bottleneck,
        'memory_bottleneck': memory_bottleneck,
        'system_pressure': system_pressure,
        'cpu_trend': cpu_trend,
        'system_risk': system_risk,
        'alerts': alerts,
        'alert_count': alert_count,
        'alert_transitions': transitions,
        'alert_states': alert_states.get(org_id, {}),
        'actions': actions,
        'capacity': capacity,
        'learning_insight': learning_insight,
        # BPI observability (Task 1) — let dashboard render the scaling signal
        'bpi': round(bpi, 2),
        'target_bpi': round(target_bpi, 2),
        'avg_service_time_ms': round(avg_service_time_ms, 3),
        # Transparency (Bug #2 follow-up): expose both numbers so the user
        # can see the divergence between desired (autoscaler) and running
        # (simulator). In a real AWS deployment, the ASG reconciler would
        # spawn EC2 instances to close the gap.
        'desired_capacity': capacity,
        'running_capacity': running_vms_count,
        # Module 4 extensions
        'workload': workload_block,
        # Module 1 extension
        'topology': topology_block,
    }


def run_control_plane_loop():
    """Background task: refresh snapshot cache + emit real-time dashboard updates.

    Runs every _cache_ttl seconds (2 s by default).  All API endpoints
    read from _snapshot_cache so they never block on heavy computation.
    """
    from app import socketio
    from app.models.organization import Organization

    while True:
        t0 = time.time()
        try:
            orgs = Organization.query.all()
            for org in orgs:
                snap_t0 = time.time()
                snapshot = _compute_org_snapshot(org.id)
                snapshot['timestamp'] = time.time()
                with _cache_lock:
                    _snapshot_cache[org.id] = snapshot
                socketio.emit(
                    "dashboard_update",
                    snapshot,
                    room=f"org_{org.id}",
                    namespace="/metrics"
                )
                # TASK 6: log per-org snapshot compute time
                elapsed_ms = round((time.time() - snap_t0) * 1000, 1)
                if elapsed_ms > 500:
                    print(f"[CONTROL_PLANE] org={org.id} snapshot took {elapsed_ms} ms — consider reducing VM count")
        except Exception:
            pass
        # TASK 4: sleep between iterations — prevents busy-loop and CPU saturation
        socketio.sleep(_cache_ttl)  # 2 s


def start_control_plane_loop():
    """Launch run_control_plane_loop as a SocketIO background task (idempotent)."""
    from app import socketio
    socketio.start_background_task(run_control_plane_loop)

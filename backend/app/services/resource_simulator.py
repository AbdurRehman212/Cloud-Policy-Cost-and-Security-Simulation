"""Dataset-backed resource simulator for the cloud digital twin."""

from __future__ import annotations

import random
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from threading import Event, Lock, Thread

import numpy as np
from flask import has_app_context, current_app

from app import db
from app.ai_models.data_generator import SyntheticDataGenerator
from app.ai_models.remediation_agent import remediation_agent
from app.ai_models.threat_detector import threat_detector
from app.models.cost import CostRecord
from app.models.governance import AuditLog
from app.models.resources import Database, ResourceStatus, VirtualMachine
from app.models.security import (
    RemediationAction,
    SecurityLog,
    ThreatDetection,
    ThreatSeverity,
    ThreatType,
)


class ResourceSimulator:
    """Simulate cloud resources using real dataset patterns and synthetic telemetry."""

    def __init__(self, tick_interval: int = 5, history_limit: int = 120):
        self.tick_interval = tick_interval
        self.history_limit = history_limit
        self.running = False
        self.thread = None
        self.stop_event = Event()
        self._lock = Lock()
        self._app = None
        self._generator = None
        self._history_by_org = defaultdict(lambda: deque(maxlen=self.history_limit))
        self._activity_by_org = defaultdict(lambda: deque(maxlen=20))

    def _get_generator(self) -> SyntheticDataGenerator:
        if self._generator is None:
            self._generator = SyntheticDataGenerator()
        return self._generator

    def start(self, app=None):
        """Start the simulation loop."""
        with self._lock:
            if self.running:
                return

            if app is None and has_app_context():
                app = current_app._get_current_object()

            self._app = app
            if self._app is None:
                print('Resource simulator not started: Flask app context unavailable')
                return

            self.running = True
            self.stop_event.clear()
            self.thread = Thread(target=self._simulation_loop, daemon=True)
            self.thread.start()
            print('Resource simulator started')

    def stop(self):
        """Stop the simulation loop."""
        with self._lock:
            self.running = False
            self.stop_event.set()
            if self.thread:
                self.thread.join(timeout=5)
            print('Resource simulator stopped')

    def _simulation_loop(self):
        """Main simulation loop."""
        if self._app is None:
            return

        with self._app.app_context():
            while self.running and not self.stop_event.is_set():
                try:
                    self._update_resources()
                except Exception as exc:  # pragma: no cover - defensive runtime logging
                    db.session.rollback()
                    print(f'Simulation error: {exc}')
                finally:
                    self.stop_event.wait(self.tick_interval)

    def _update_resources(self):
        """Update all running resources with dataset-backed telemetry."""
        generator = self._get_generator()
        moment = datetime.utcnow()

        vms = VirtualMachine.query.filter_by(status=ResourceStatus.RUNNING).all()
        dbs = Database.query.filter_by(status=ResourceStatus.RUNNING).all()

        for vm in vms:
            metrics = generator.generate_vm_metrics(vm, moment)
            vm.cpu_utilization = metrics['cpu_utilization']
            vm.memory_utilization = metrics['memory_utilization']
            vm.disk_read_iops = metrics['disk_read_iops']
            vm.disk_write_iops = metrics['disk_write_iops']
            vm.network_in_mbps = metrics['network_in_mbps']
            vm.network_out_mbps = metrics['network_out_mbps']
            vm.total_runtime_hours += self.tick_interval / 3600
            self._upsert_cost_record(vm, 'vm', moment, metrics)
            self._analyze_vm_security(vm, moment)

        for database in dbs:
            metrics = generator.generate_database_metrics(database, moment)
            database.cpu_utilization = metrics['cpu_utilization']
            database.database_connections = metrics['database_connections']
            database.read_iops = metrics['read_iops']
            database.write_iops = metrics['write_iops']
            database.free_storage_space = metrics['free_storage_space']
            database.total_runtime_hours += self.tick_interval / 3600
            self._upsert_cost_record(database, 'database', moment, metrics)

        db.session.commit()

        org_ids = {vm.organization_id for vm in vms} | {database.organization_id for database in dbs}
        for org_id in org_ids:
            self._record_org_snapshot(org_id, moment)
            self._append_activity(
                org_id,
                title='Synthetic telemetry refreshed',
                severity='info',
                details=f'Updated {len(vms)} VM(s) and {len(dbs)} database(s) from the simulator.',
                moment=moment,
            )

    def _usage_factor(self, metrics, kind='vm'):
        cpu = float(metrics.get('cpu_utilization', 0) or 0)
        memory = float(metrics.get('memory_utilization', 0) or 0)
        network_in = float(metrics.get('network_in_mbps', 0) or 0)
        network_out = float(metrics.get('network_out_mbps', 0) or 0)
        base = 0.35 if kind == 'vm' else 0.30
        usage = base + (cpu / 100.0) * 0.55 + (memory / 100.0) * 0.25
        usage += min(0.25, (network_in + network_out) / 2000.0)
        return max(0.25, usage)

    def _upsert_cost_record(self, resource, resource_type, moment, metrics):
        hourly_increment = resource.hourly_rate * self._usage_factor(metrics, resource_type) * (
            self.tick_interval / 3600
        )
        record = CostRecord.query.filter_by(
            organization_id=resource.organization_id,
            resource_id=resource.instance_id,
            resource_type=resource_type,
            date=moment.date(),
            hour=moment.hour,
        ).first()
        if record is None:
            record = CostRecord(
                organization_id=resource.organization_id,
                resource_id=resource.instance_id,
                resource_type=resource_type,
                date=moment.date(),
                hour=moment.hour,
                compute_cost=0.0,
                storage_cost=0.0,
                network_cost=0.0,
                total_cost=0.0,
                cpu_avg=0.0,
                memory_avg=0.0,
            )
            db.session.add(record)

        record.compute_cost = round((record.compute_cost or 0.0) + hourly_increment * 0.72, 6)
        record.storage_cost = round((record.storage_cost or 0.0) + hourly_increment * 0.18, 6)
        record.network_cost = round((record.network_cost or 0.0) + hourly_increment * 0.10, 6)
        record.total_cost = round((record.total_cost or 0.0) + hourly_increment, 6)
        record.cpu_avg = float(metrics.get('cpu_utilization', 0) or 0)
        record.memory_avg = float(metrics.get('memory_utilization', 0) or 0)
        record.timestamp = moment

    def _build_vm_traffic_metrics(self, vm):
        cpu = float(vm.cpu_utilization or 0)
        memory = float(vm.memory_utilization or 0)
        network_in = float(vm.network_in_mbps or 0)
        network_out = float(vm.network_out_mbps or 0)
        requests_per_minute = int(max(120, network_in * 20 + cpu * 35 + random.uniform(0, 160)))
        avg_latency_ms = round(max(15.0, 35 + cpu * 2.4 + network_out * 0.45 + random.uniform(-5, 25)), 2)
        error_rate = round(min(0.42, max(0.002, (cpu / 100.0) * 0.06 + random.uniform(0.0, 0.015))), 4)
        auth_failures = int(max(0, (cpu - 70) / 5 + random.uniform(0, 4))) if cpu > 70 else int(random.uniform(0, 2))

        return {
            'requests_per_minute': requests_per_minute,
            'avg_latency_ms': avg_latency_ms,
            'error_rate': error_rate,
            'bytes_in': int(network_in * 125000),
            'bytes_out': int(network_out * 125000),
            'active_connections': int(max(1, network_in / 2 + cpu * 0.8)),
            'cpu_utilization': cpu,
            'memory_utilization': memory,
            'disk_read_iops': float(vm.disk_read_iops or 0),
            'disk_write_iops': float(vm.disk_write_iops or 0),
            'network_in_mbps': network_in,
            'network_out_mbps': network_out,
            'auth_failures': auth_failures,
        }

    def _map_threat_type(self, label):
        normalized = (label or '').lower()
        return {
            'ddos': ThreatType.DDoS,
            'brute_force': ThreatType.BRUTE_FORCE,
            'port_scan': ThreatType.PORT_SCAN,
            'sql_injection': ThreatType.SQL_INJECTION,
            'xss': ThreatType.XSS,
            'malware': ThreatType.MALWARE,
            'unauthorized_access': ThreatType.UNAUTHORIZED_ACCESS,
            'privilege_escalation': ThreatType.PRIVILEGE_ESCALATION,
            'data_exfiltration': ThreatType.DATA_EXFILTRATION,
            'suspicious_behavior': ThreatType.SUSPICIOUS_BEHAVIOR,
        }.get(normalized, ThreatType.SUSPICIOUS_BEHAVIOR)

    def _severity_from_confidence(self, confidence):
        if confidence >= 0.95:
            return ThreatSeverity.CRITICAL
        if confidence >= 0.82:
            return ThreatSeverity.HIGH
        if confidence >= 0.7:
            return ThreatSeverity.MEDIUM
        return ThreatSeverity.LOW

    def _threat_recent(self, vm, threat_type, moment):
        recent_cutoff = moment - timedelta(minutes=30)
        recent = ThreatDetection.query.filter(
            ThreatDetection.organization_id == vm.organization_id,
            ThreatDetection.detected_at >= recent_cutoff,
        ).order_by(ThreatDetection.detected_at.desc()).limit(10).all()
        for threat in recent:
            affected = threat.affected_resources or []
            if threat.threat_type == threat_type and vm.instance_id in affected and threat.status == 'active':
                return True
        return False

    def _analyze_vm_security(self, vm, moment):
        if threat_detector is None:
            return

        metrics = self._build_vm_traffic_metrics(vm)
        result = threat_detector.real_time_monitor(metrics)
        if not result.get('is_threat'):
            return

        threat_type = self._map_threat_type(result.get('threat_type'))
        if self._threat_recent(vm, threat_type, moment):
            return

        severity = self._severity_from_confidence(result.get('confidence', 0.0))
        threat = ThreatDetection(
            organization_id=vm.organization_id,
            threat_type=threat_type,
            severity=severity,
            confidence_score=float(result.get('confidence', 0.0)),
            affected_resources=[vm.instance_id],
            attack_vectors={
                'metrics': metrics,
                'source': result.get('source'),
                'signals': result.get('signals'),
            },
            network_traffic_snapshot=metrics,
            model_version=result.get('source', 'heuristic'),
            detection_pattern=f'Synthetic {result.get("threat_type")} pattern detected',
            status='active',
        )
        db.session.add(threat)
        db.session.flush()

        db.session.add(
            SecurityLog(
                organization_id=vm.organization_id,
                event_type=f'{result.get("threat_type", "suspicious_behavior")}_detected',
                severity=severity,
                source_ip='198.51.100.200',
                destination_ip=vm.private_ip,
                resource_id=vm.instance_id,
                description='Synthetic threat generated by the simulator.',
                raw_data=metrics,
            )
        )

        if remediation_agent is not None:
            remediation_result = remediation_agent.remediate(
                {'type': result.get('threat_type'), 'severity': severity.value, 'confidence': result.get('confidence', 0.0)},
                vm.to_dict(),
            )
            for action in remediation_result.get('results', []):
                db.session.add(
                    RemediationAction(
                        threat_id=threat.id,
                        action_type=action.get('action', 'request_review'),
                        executed_by='system',
                        status=action.get('status', 'success'),
                        details=action.get('details'),
                        result='Applied by dataset-backed simulator',
                        requires_approval=remediation_result.get('requires_approval', False),
                    )
                )

        self._append_activity(
            vm.organization_id,
            title='Security threat detected',
            severity=severity.value,
            details=f'{result.get("threat_type", "suspicious_behavior")} detected on {vm.instance_id}.',
            moment=moment,
        )

    def _record_org_snapshot(self, org_id, moment):
        vms = VirtualMachine.query.filter_by(organization_id=org_id).all()
        dbs = Database.query.filter_by(organization_id=org_id).all()
        running_vms = [vm for vm in vms if vm.status == ResourceStatus.RUNNING]
        running_dbs = [database for database in dbs if database.status == ResourceStatus.RUNNING]

        cpu_values = [vm.cpu_utilization for vm in running_vms] + [database.cpu_utilization for database in running_dbs]
        memory_values = [vm.memory_utilization for vm in running_vms] + [
            min(100.0, max(0.0, database.cpu_utilization * 1.35 + database.database_connections * 0.65))
            for database in running_dbs
        ]
        cost_values = [vm.calculate_current_cost() for vm in running_vms] + [
            database.total_runtime_hours * database.hourly_rate for database in running_dbs
        ]

        snapshot = {
            'timestamp': moment.isoformat(),
            'name': moment.strftime('%H:%M:%S'),
            'cpu': round(float(np.mean(cpu_values)) if cpu_values else 0.0, 2),
            'memory': round(float(np.mean(memory_values)) if memory_values else 0.0, 2),
            'cost': round(float(sum(cost_values)) if cost_values else 0.0, 4),
            'running_vms': len(running_vms),
            'running_dbs': len(running_dbs),
        }
        self._history_by_org[org_id].append(snapshot)

    def _append_activity(self, org_id, title, severity, details, moment=None):
        self._activity_by_org[org_id].appendleft(
            {
                'title': title,
                'severity': severity,
                'details': details,
                'timestamp': (moment or datetime.utcnow()).isoformat(),
            }
        )

    def _build_cost_trend_from_records(self, org_id):
        records = (
            CostRecord.query.filter_by(organization_id=org_id)
            .order_by(CostRecord.date.asc(), CostRecord.hour.asc())
            .all()
        )
        grouped = {}
        for record in records[-48:]:
            label = f'{record.date.isoformat()} {int(record.hour):02d}:00' if record.hour is not None else record.date.isoformat()
            grouped[label] = grouped.get(label, 0.0) + float(record.total_cost or 0.0)
        return [
            {'name': name, 'cost': round(cost, 2)}
            for name, cost in list(grouped.items())[-12:]
        ]

    def _build_utilization_trend_from_resources(self, org_id):
        vms = VirtualMachine.query.filter_by(organization_id=org_id).all()
        dbs = Database.query.filter_by(organization_id=org_id).all()
        cpu_values = [vm.cpu_utilization for vm in vms if vm.status == ResourceStatus.RUNNING] + [
            database.cpu_utilization for database in dbs if database.status == ResourceStatus.RUNNING
        ]
        memory_values = [vm.memory_utilization for vm in vms if vm.status == ResourceStatus.RUNNING] + [
            min(100.0, max(0.0, database.cpu_utilization * 1.35 + database.database_connections * 0.65))
            for database in dbs
            if database.status == ResourceStatus.RUNNING
        ]
        cpu = round(float(np.mean(cpu_values)) if cpu_values else 0.0, 2)
        memory = round(float(np.mean(memory_values)) if memory_values else 0.0, 2)
        series = []
        for offset in range(6):
            jitter = (offset - 2.5) * 1.8
            series.append({
                'name': f'{(datetime.utcnow() - timedelta(hours=5 - offset)).strftime("%H:%M")}',
                'cpu': max(0, round(cpu + jitter, 2)),
                'memory': max(0, round(memory + jitter * 0.8, 2)),
            })
        return series

    def _build_recent_activity_from_db(self, org_id):
        items = []
        audit_logs = AuditLog.query.filter_by(organization_id=org_id).order_by(AuditLog.timestamp.desc()).limit(3).all()
        for log in audit_logs:
            items.append(
                {
                    'title': f'Audit: {log.action}',
                    'severity': 'info',
                    'details': f'{log.resource_type or "resource"} {log.resource_id or ""}'.strip(),
                    'timestamp': log.timestamp.isoformat() if log.timestamp else None,
                }
            )

        threats = ThreatDetection.query.filter_by(organization_id=org_id).order_by(ThreatDetection.detected_at.desc()).limit(3).all()
        for threat in threats:
            items.append(
                {
                    'title': f'Security: {threat.threat_type.value}',
                    'severity': threat.severity.value if threat.severity else 'medium',
                    'details': ', '.join(threat.affected_resources or []),
                    'timestamp': threat.detected_at.isoformat() if threat.detected_at else None,
                }
            )

        items.sort(key=lambda item: item.get('timestamp') or '', reverse=True)
        return items[:5]

    def get_dashboard_snapshot(self, org_id):
        """Return chart and activity series for the dashboard."""
        history = list(self._history_by_org.get(org_id, []))
        if history:
            cost_trend = [{'name': item['name'], 'cost': round(item['cost'], 2)} for item in history[-12:]]
            utilization_trend = [
                {'name': item['name'], 'cpu': round(item['cpu'], 2), 'memory': round(item['memory'], 2)}
                for item in history[-12:]
            ]
        else:
            cost_trend = self._build_cost_trend_from_records(org_id)
            utilization_trend = self._build_utilization_trend_from_resources(org_id)

        recent_activity = list(self._activity_by_org.get(org_id, []))
        if not recent_activity:
            recent_activity = self._build_recent_activity_from_db(org_id)

        return {
            'cost_trend': cost_trend,
            'utilization_trend': utilization_trend,
            'recent_activity': recent_activity,
        }

    def simulate_load_test(self, vm_id, duration_seconds=60, intensity='medium'):
        """Simulate load test on a specific VM."""
        vm = VirtualMachine.query.get(vm_id)
        if not vm or vm.status != ResourceStatus.RUNNING:
            return False

        intensity_factor = {'low': 1.5, 'medium': 3, 'high': 5}.get(intensity, 3)
        original_cpu = vm.cpu_utilization

        def apply_load():
            start_time = time.time()
            while time.time() - start_time < duration_seconds:
                vm.cpu_utilization = min(100, original_cpu * intensity_factor + np.random.normal(0, 10))
                db.session.commit()
                time.sleep(1)
            vm.cpu_utilization = original_cpu
            db.session.commit()

        Thread(target=apply_load, daemon=True).start()
        return True


# Global simulator instance
resource_simulator = ResourceSimulator()

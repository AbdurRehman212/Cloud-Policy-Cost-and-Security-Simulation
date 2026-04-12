"""
Resource Simulator Service
Generates realistic utilization metrics for simulated resources.
P1 Final - M. Abdur Rehman Khan
"""
import random
import numpy as np
from datetime import datetime
from threading import Thread, Event
import time
from app import db
from app.models.resources import VirtualMachine, Database, ResourceStatus
class ResourceSimulator:
    """
    Simulates realistic cloud resource behavior including:
    - CPU/Memory utilization patterns
    - Network I/O
    - Disk operations
    - Cost accumulation
    """
    def __init__(self, tick_interval=5):
        self.tick_interval = tick_interval
        self.running = False
        self.thread = None
        self.stop_event = Event()
    def start(self):
        """Start the simulation loop."""
        if not self.running:
            self.running = True
            self.stop_event.clear()
            self.thread = Thread(target=self._simulation_loop, daemon=True)
            self.thread.start()
            print("Resource simulator started")
    def stop(self):
        """Stop the simulation loop."""
        self.running = False
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        print("Resource simulator stopped")
    def _simulation_loop(self):
        """Main simulation loop."""
        while self.running and not self.stop_event.is_set():
            try:
                self._update_resources()
                time.sleep(self.tick_interval)
            except Exception as e:
                print(f"Simulation error: {e}")
    def _update_resources(self):
        """Update all running resources with new metrics."""
        # Update VMs
        vms = VirtualMachine.query.filter_by(status=ResourceStatus.RUNNING).all()
        for vm in vms:
            # Generate realistic CPU pattern with daily cycle
            hour = datetime.now().hour
            base_cpu = 30 if 9 <= hour <= 17 else 10  # Business hours higher
            cpu_spike = np.random.exponential(10) if random.random() < 0.05 else 0
            vm.cpu_utilization = min(100, base_cpu + np.random.normal(0, 10) + cpu_spike)
            # Memory correlated with CPU but smoother
            vm.memory_utilization = min(100, vm.memory_utilization * 0.7 + vm.cpu_utilization * 0.3 + np.random.normal(0, 5))
            # Network I/O
            vm.network_in_mbps = max(0, np.random.normal(50, 20) + (vm.cpu_utilization / 100) * 100)
            vm.network_out_mbps = max(0, vm.network_in_mbps * np.random.uniform(0.5, 2))
            # Disk I/O
            vm.disk_read_iops = max(0, np.random.normal(100, 50))
            vm.disk_write_iops = max(0, vm.disk_read_iops * np.random.uniform(0.3, 0.8))
            # Update runtime cost
            vm.total_runtime_hours += self.tick_interval / 3600
        # Update Databases
        dbs = Database.query.filter_by(status=ResourceStatus.RUNNING).all()
        for db_instance in dbs:
            # Database patterns: steady with occasional spikes
            db_instance.cpu_utilization = min(100, np.random.normal(25, 15) + np.random.exponential(5))
            db_instance.database_connections = int(np.random.poisson(20))
            db_instance.read_iops = max(0, np.random.normal(500, 200))
            db_instance.write_iops = max(0, np.random.normal(200, 100))
            db_instance.free_storage_space = max(0, (db_instance.free_storage_space or 20) - np.random.uniform(0.05, 0.35))
            db_instance.total_runtime_hours += self.tick_interval / 3600
        db.session.commit()
    def simulate_load_test(self, vm_id, duration_seconds=60, intensity='medium'):
        """
        Simulate load test on specific VM.
        Used for training and demonstrations.
        """
        vm = VirtualMachine.query.get(vm_id)
        if not vm or vm.status != ResourceStatus.RUNNING:
            return False
        intensity_factor = {'low': 1.5, 'medium': 3, 'high': 5}[intensity]
        # Apply temporary load
        original_cpu = vm.cpu_utilization
        def apply_load():
            start_time = time.time()
            while time.time() - start_time < duration_seconds:
                vm.cpu_utilization = min(100, original_cpu * intensity_factor + np.random.normal(0, 10))
                db.session.commit()
                time.sleep(1)
            # Restore normal
            vm.cpu_utilization = original_cpu
            db.session.commit()
        Thread(target=apply_load, daemon=True).start()
        return True
# Global simulator instance
resource_simulator = ResourceSimulator()

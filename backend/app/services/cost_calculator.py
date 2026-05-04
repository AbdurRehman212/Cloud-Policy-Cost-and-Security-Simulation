"""
Cost Calculation Service
Handles real-time cost tracking and billing simulation.
P2 Final - M. Abdur Rehman Khan
"""
from datetime import datetime, timedelta
from app import db
from app.models.cost import CostRecord
from app.models.resources import VirtualMachine, Database, ResourceStatus
class CostCalculator:
    """Calculate and record costs for simulated resources."""
    def __init__(self):
        self.pricing = {
            'vm': {
                't2.micro': 0.0116,
                't2.small': 0.023,
                't2.medium': 0.0464,
                't2.large': 0.0928,
                'm5.large': 0.096,
                'm5.xlarge': 0.192,
            },
            'db': {
                'db.t2.micro': 0.017,
                'db.t2.small': 0.034,
                'db.m5.large': 0.192,
            }
        }
    def record_hourly_costs(self, organization_id):
        """Record costs for current hour."""
        now = datetime.utcnow()
        # Get all running resources
        vms = VirtualMachine.query.filter_by(
            organization_id=organization_id,
            status=ResourceStatus.RUNNING
        ).all()
        dbs = Database.query.filter_by(
            organization_id=organization_id,
            status=ResourceStatus.RUNNING
        ).all()
        total_cost = 0
        # Record VM costs
        for vm in vms:
            hourly_rate = vm.hourly_rate
            compute_cost = hourly_rate * 0.7  # 70% compute
            storage_cost = hourly_rate * 0.2  # 20% storage
            network_cost = hourly_rate * 0.1  # 10% network
            cost_record = CostRecord(
                organization_id=organization_id,
                resource_id=vm.instance_id,
                resource_type='vm',
                date=now.date(),
                hour=now.hour,
                compute_cost=compute_cost,
                storage_cost=storage_cost,
                network_cost=network_cost,
                total_cost=hourly_rate,
                cpu_avg=vm.cpu_utilization,
                memory_avg=vm.memory_utilization
            )
            db.session.add(cost_record)
            total_cost += hourly_rate
        # Record DB costs
        for db_instance in dbs:
            hourly_rate = db_instance.hourly_rate
            cost_record = CostRecord(
                organization_id=organization_id,
                resource_id=db_instance.instance_id,
                resource_type='database',
                date=now.date(),
                hour=now.hour,
                compute_cost=hourly_rate * 0.6,
                storage_cost=hourly_rate * 0.3,
                network_cost=hourly_rate * 0.1,
                total_cost=hourly_rate,
                cpu_avg=db_instance.cpu_utilization
            )
            db.session.add(cost_record)
            total_cost += hourly_rate
        db.session.commit()
        return total_cost
    def get_cost_breakdown(self, organization_id, start_date, end_date):
        """Get detailed cost breakdown for period."""
        records = CostRecord.query.filter(
            CostRecord.organization_id == organization_id,
            CostRecord.date >= start_date,
            CostRecord.date <= end_date
        ).all()
        breakdown = {
            'total': sum(r.total_cost for r in records),
            'by_service': {},
            'by_day': {},
            'compute': sum(r.compute_cost for r in records),
            'storage': sum(r.storage_cost for r in records),
            'network': sum(r.network_cost for r in records)
        }
        for r in records:
            # By service
            service = r.resource_type
            breakdown['by_service'][service] = breakdown['by_service'].get(service, 0) + r.total_cost
            # By day
            day = str(r.date)
            breakdown['by_day'][day] = breakdown['by_day'].get(day, 0) + r.total_cost
        return breakdown
cost_calculator = CostCalculator()

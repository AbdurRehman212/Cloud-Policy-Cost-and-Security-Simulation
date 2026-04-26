from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.organization import OrganizationMember
from app.models.resources import VirtualMachine, Database, ResourceStatus
from app.models.security import ThreatDetection
from app.models.cost import CostRecord, Budget
from app.services.resource_simulator import resource_simulator
from datetime import datetime, timedelta
dashboard_bp = Blueprint('dashboard', __name__)
@dashboard_bp.route('/summary', methods=['GET'])
@jwt_required()
def get_dashboard_summary():
    """Get dashboard summary data."""
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)
    use_resource_metrics = (request.args.get('use_resource_metrics', '') or '').strip().lower() in {'1', 'true', 'yes'}
    member = OrganizationMember.query.filter_by(organization_id=org_id, user_id=user_id).first()
    if not member:
        return jsonify({'error': 'Access denied'}), 403
    # Resource counts
    total_vms = VirtualMachine.query.filter_by(organization_id=org_id).count()
    running_vms = VirtualMachine.query.filter_by(
        organization_id=org_id,
        status=ResourceStatus.RUNNING
    ).count()
    total_dbs = Database.query.filter_by(organization_id=org_id).count()
    running_dbs = Database.query.filter_by(
        organization_id=org_id,
        status=ResourceStatus.RUNNING
    ).count()
    # Security status
    active_threats = ThreatDetection.query.filter_by(
        organization_id=org_id,
        status='active'
    ).count()
    # Cost status
    today = datetime.now()
    month_start = today.replace(day=1)
    month_costs = CostRecord.query.filter(
        CostRecord.organization_id == org_id,
        CostRecord.date >= month_start.date()
    ).all()
    current_spend = sum(c.total_cost for c in month_costs)
    # Budget status
    budgets = Budget.query.filter_by(organization_id=org_id, is_active=True).all()
    budget_status = []
    for b in budgets:
        status = b.to_dict()
        status['alert_level'] = 'normal'
        if status['percentage_used'] > 100:
            status['alert_level'] = 'critical'
        elif status['percentage_used'] > 80:
            status['alert_level'] = 'warning'
        budget_status.append(status)
    # Recent activity (last 24 hours)
    yesterday = today - timedelta(days=1)
    simulator_snapshot = resource_simulator.get_dashboard_snapshot(org_id)

    if use_resource_metrics:
        from app.routes.resources import RESOURCES, _RESOURCE_LOCK

        with _RESOURCE_LOCK:
            scoped_resources = [
                resource for resource in RESOURCES
                if resource.get('org_id') == org_id and resource.get('id')
            ]

        vm_resources = [resource for resource in scoped_resources if resource.get('type') != 'database']
        db_resources = [resource for resource in scoped_resources if resource.get('type') == 'database']
        running_resources = [resource for resource in scoped_resources if resource.get('status') == 'running']
        avg_cpu = (
            sum(float(resource.get('cpu', 0.0)) for resource in running_resources) / len(running_resources)
            if running_resources else 0.0
        )
        avg_memory = (
            sum(float(resource.get('memory', 0.0)) for resource in running_resources) / len(running_resources)
            if running_resources else 0.0
        )

        total_vms = len(vm_resources)
        running_vms = sum(1 for resource in vm_resources if resource.get('status') == 'running')
        total_dbs = len(db_resources)
        running_dbs = sum(1 for resource in db_resources if resource.get('status') == 'running')
        simulator_snapshot = {
            **simulator_snapshot,
            'utilization_trend': [{
                'timestamp': datetime.utcnow().isoformat(),
                'cpu_avg': round(avg_cpu * 100, 2),
                'memory_avg': round(avg_memory * 100, 2),
            }],
        }

    return jsonify({
        'resources': {
            'vms': {'total': total_vms, 'running': running_vms},
            'databases': {'total': total_dbs, 'running': running_dbs}
        },
        'security': {
            'active_threats': active_threats,
            'status': 'critical' if active_threats > 0 else 'healthy'
        },
        'costs': {
            'current_month_spend': round(current_spend, 2),
            'budgets': budget_status
        },
        'cost_trend': simulator_snapshot.get('cost_trend', []),
        'utilization_trend': simulator_snapshot.get('utilization_trend', []),
        'recent_activity': simulator_snapshot.get('recent_activity', []),
        'health_score': calculate_health_score(
            active_threats, running_vms, total_vms, current_spend, budgets
        )
    }), 200
def calculate_health_score(threats, running_vms, total_vms, spend, budgets):
    """Calculate overall infrastructure health score."""
    score = 100
    # Deduct for threats
    score -= threats * 20
    # Deduct for low utilization
    if total_vms > 0:
        utilization_rate = running_vms / total_vms
        if utilization_rate < 0.3:
            score -= 10
    # Deduct for budget overruns
    for b in budgets:
        if b.get_current_spend() > b.amount:
            score -= 15
    return max(0, min(100, score))

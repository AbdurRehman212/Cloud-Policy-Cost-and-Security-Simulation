from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models.organization import Organization, OrganizationMember

membership_bp = Blueprint('membership', __name__)


PLANS = [
    {
        'id': 'starter',
        'name': 'Starter',
        'description': 'Default simulator access for students and single-user demos.',
        'max_resources': 50,
        'features': [
            'Dashboard, resources, security, cost, governance, settings',
            'Basic AI assistant',
            'Local development and demo support',
        ],
    },
    {
        'id': 'pro',
        'name': 'Pro',
        'description': 'Future plan for advanced tools, analytics, and higher quotas.',
        'max_resources': 100,
        'features': [
            'Higher resource limits',
            'Advanced cost optimisation reports',
            'Enhanced security analytics',
        ],
    },
    {
        'id': 'enterprise',
        'name': 'Enterprise',
        'description': 'Future plan for teams, labs, and institution-wide deployments.',
        'max_resources': 250,
        'features': [
            'Multi-team management',
            'Custom policy packs',
            'Deployment and governance support',
        ],
    },
]


def infer_plan(max_resources):
    if max_resources is None:
        return 'starter'
    if max_resources >= 200:
        return 'enterprise'
    if max_resources >= 100:
        return 'pro'
    return 'starter'


@membership_bp.route('/plans', methods=['GET'])
@jwt_required()
def list_plans():
    org_id = request.args.get('organization_id', type=int)
    current_plan = 'starter'
    if org_id:
        org = Organization.query.get(org_id)
        if org:
            current_plan = infer_plan(org.max_resources)
    return jsonify({
        'current_plan': current_plan,
        'plans': PLANS,
    }), 200


@membership_bp.route('/current', methods=['GET'])
@jwt_required()
def current_membership():
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)
    member = OrganizationMember.query.filter_by(organization_id=org_id, user_id=user_id).first()
    if not member:
        return jsonify({'error': 'Access denied'}), 403
    org = Organization.query.get_or_404(org_id)
    plan_id = infer_plan(org.max_resources)
    plan = next((plan for plan in PLANS if plan['id'] == plan_id), PLANS[0])
    return jsonify({
        'organization_id': org_id,
        'plan': plan,
        'resource_limit': org.max_resources,
        'member_role': member.role,
    }), 200

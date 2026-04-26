from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models.user import User
from app.models.organization import Organization, OrganizationMember, ensure_default_organization_membership

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


def _resolve_membership(user_id, requested_org_id=None):
    """Resolve membership with a safe demo fallback."""
    if requested_org_id:
        member = OrganizationMember.query.filter_by(
            organization_id=requested_org_id,
            user_id=user_id,
        ).first()
        if member:
            return member

    member = (
        OrganizationMember.query
        .filter_by(user_id=user_id)
        .order_by(OrganizationMember.joined_at.asc(), OrganizationMember.id.asc())
        .first()
    )
    if member:
        return member

    user = User.query.get(user_id)
    if not user:
        return None

    _, member, created = ensure_default_organization_membership(user)
    if created:
        db.session.commit()
    return member


@membership_bp.route('/plans', methods=['GET'])
@jwt_required()
def list_plans():
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)

    member = _resolve_membership(user_id, org_id)
    if member and member.organization:
        current_plan = infer_plan(member.organization.max_resources)
    else:
        current_plan = 'starter'

    payload = {
        'current_plan': current_plan,
        'plans': PLANS,
    }
    return jsonify({
        'status': 'success',
        'data': payload,
        **payload,
    }), 200


@membership_bp.route('/current', methods=['GET'])
@jwt_required()
def current_membership():
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)
    member = _resolve_membership(user_id, org_id)
    if not member:
        return jsonify({
            'status': 'error',
            'error': {'message': 'Membership not found.'},
        }), 404

    org = member.organization
    if not org:
        return jsonify({
            'status': 'error',
            'error': {'message': 'Organization not found for membership.'},
        }), 404

    plan_id = infer_plan(org.max_resources)
    plan = next((plan for plan in PLANS if plan['id'] == plan_id), PLANS[0])

    payload = {
        'organization_id': org.id,
        'plan': plan,
        'resource_limit': org.max_resources,
        'member_role': member.role,
    }
    return jsonify({
        'status': 'success',
        'data': payload,
        **payload,
    }), 200


@membership_bp.route('/me', methods=['GET'])
@jwt_required()
def membership_me():
    """Return current user membership safely for demo flows."""
    user_id = get_jwt_identity()
    member = _resolve_membership(user_id)

    if not member:
        return jsonify({
            'status': 'error',
            'error': {'message': 'Membership not found.'},
        }), 404

    return jsonify({
        'status': 'success',
        'data': {
            'user_id': member.user_id,
            'organization_id': member.organization_id,
            'role': member.role or 'owner',
        },
    }), 200

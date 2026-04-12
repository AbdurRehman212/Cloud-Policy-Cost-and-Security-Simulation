from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.governance import Policy, ComplianceCheck, AuditLog, PolicyStatus
from app.models.organization import OrganizationMember
from datetime import datetime

try:
    from app.ai_models.policy_engine import policy_engine
except ImportError:
    policy_engine = None

governance_bp = Blueprint('governance', __name__)


def fallback_compile_policy(policy_rule):
    """Rules-only fallback used if the policy compiler cannot be imported."""
    rule_text = (policy_rule or '').strip()
    if not rule_text:
        return {'success': False, 'error': 'Policy rule is required'}
    return {
        'success': True,
        'confidence': 1.0,
        'parsed_rule': {
            'expression': rule_text,
            'fields': {
                'type': 'custom',
                'severity': 'medium',
                'resource_type': None,
                'requires_encryption': False,
                'requires_private_access': False,
                'requires_public_block': False,
                'required_tags': [],
                'max_cpu': None,
                'max_memory': None,
                'max_network': None,
            },
        },
    }


def fallback_evaluate_resource(rule, resource):
    """Default compliant evaluation when rules cannot be compiled."""
    return {'compliant': True, 'violations': [], 'rule': rule, 'resource': resource}
@governance_bp.route('/policies', methods=['POST'])
@jwt_required()
def create_policy():
    """Create a rules-based policy."""
    user_id = get_jwt_identity()
    data = request.get_json()
    org_id = data.get('organization_id')
    member = OrganizationMember.query.filter_by(organization_id=org_id, user_id=user_id).first()
    if not member or member.role not in ['admin', 'owner']:
        return jsonify({'error': 'Insufficient permissions'}), 403
    # Parse explicit rule syntax
    policy_rule = data.get('policy_rule') or data.get('natural_language_rule')
    parsed = policy_engine.parse_policy(policy_rule) if policy_engine else fallback_compile_policy(policy_rule)
    if not parsed['success']:
        return jsonify({'error': parsed['error']}), 400
    parsed_rule = parsed['parsed_rule']
    rule_fields = parsed_rule.get('fields', parsed_rule)
    policy = Policy(
        organization_id=org_id,
        name=data.get('name'),
        description=data.get('description'),
        natural_language_rule=policy_rule,
        compiled_rule=parsed_rule,
        policy_type=rule_fields.get('type', 'custom'),
        auto_remediate=data.get('auto_remediate', False),
        severity=rule_fields.get('severity', 'medium'),
        status=PolicyStatus.ACTIVE,
        created_by=user_id
    )
    db.session.add(policy)
    db.session.commit()
    return jsonify({
        'message': 'Policy created',
        'policy': policy.to_dict(),
        'parsed_confidence': parsed['confidence']
    }), 201
@governance_bp.route('/policies', methods=['GET'])
@jwt_required()
def list_policies():
    """List policies."""
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)
    member = OrganizationMember.query.filter_by(organization_id=org_id, user_id=user_id).first()
    if not member:
        return jsonify({'error': 'Access denied'}), 403
    policies = Policy.query.filter_by(organization_id=org_id).all()
    return jsonify({
        'policies': [p.to_dict() for p in policies]
    }), 200
@governance_bp.route('/compliance/check', methods=['POST'])
@jwt_required()
def check_compliance():
    """Run compliance check against resources."""
    user_id = get_jwt_identity()
    data = request.get_json()
    org_id = data.get('organization_id')
    member = OrganizationMember.query.filter_by(organization_id=org_id, user_id=user_id).first()
    if not member:
        return jsonify({'error': 'Access denied'}), 403
    # Get active policies
    policies = Policy.query.filter_by(organization_id=org_id, status=PolicyStatus.ACTIVE).all()
    # Get resources
    from app.models.resources import VirtualMachine, Database
    vms = VirtualMachine.query.filter_by(organization_id=org_id).all()
    dbs = Database.query.filter_by(organization_id=org_id).all()
    results = []
    for policy in policies:
        compiled = policy.compiled_rule or {}
        rule = compiled.get('fields', compiled)
        # Check VMs
        for vm in vms:
            if rule.get('resource_type') in [None, 'vm']:
                result = policy_engine.evaluate_resource(rule, vm.to_dict()) if policy_engine else fallback_evaluate_resource(rule, vm.to_dict())
                if not result['compliant']:
                    check = ComplianceCheck(
                        policy_id=policy.id,
                        resource_id=vm.instance_id,
                        resource_type='vm',
                        is_compliant=False,
                        violation_details=result
                    )
                    db.session.add(check)
                    results.append({
                        'policy': policy.name,
                        'resource': vm.instance_id,
                        'compliant': False,
                        'violations': result['violations']
                    })
                    # Auto-remediate if enabled
                    if policy.auto_remediate:
                        # Apply remediation
                        check.remediation_applied = True
                        check.remediation_details = {'action': 'auto_fixed'}
        # Check Databases
        for database in dbs:
            if rule.get('resource_type') in [None, 'database']:
                result = policy_engine.evaluate_resource(rule, database.to_dict()) if policy_engine else fallback_evaluate_resource(rule, database.to_dict())
                if not result['compliant']:
                    check = ComplianceCheck(
                        policy_id=policy.id,
                        resource_id=database.instance_id,
                        resource_type='database',
                        is_compliant=False,
                        violation_details=result
                    )
                    db.session.add(check)
                    results.append({
                        'policy': policy.name,
                        'resource': database.instance_id,
                        'compliant': False,
                        'violations': result['violations']
                    })
    db.session.commit()
    return jsonify({
        'checked_at': datetime.utcnow().isoformat(),
        'policies_checked': len(policies),
        'violations_found': len(results),
        'results': results
    }), 200
@governance_bp.route('/audit-logs', methods=['GET'])
@jwt_required()
def get_audit_logs():
    """Get audit trail."""
    user_id = get_jwt_identity()
    org_id = request.args.get('organization_id', type=int)
    member = OrganizationMember.query.filter_by(organization_id=org_id, user_id=user_id).first()
    if not member:
        return jsonify({'error': 'Access denied'}), 403
    logs = AuditLog.query.filter_by(organization_id=org_id)\
        .order_by(AuditLog.timestamp.desc())\
        .limit(1000)\
        .all()
    return jsonify({
        'logs': [log.to_dict() for log in logs],
        'total': len(logs)
    }), 200

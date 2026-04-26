from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.organization import Organization, OrganizationMember, Invitation, ensure_default_organization_membership
from app.models.user import User
from datetime import datetime
org_bp = Blueprint('organization', __name__)


def _success(data, status_code=200):
    return jsonify({'status': 'success', 'data': data}), status_code


def _error(message, status_code=400):
    return jsonify({'status': 'error', 'error': {'message': message}}), status_code
@org_bp.route('/', methods=['POST'])
@jwt_required()
def create_organization():
    """Create new organization."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    if not data.get('name'):
        return _error('Organization name required', status_code=400)
    org = Organization(
        name=data['name'],
        description=data.get('description', ''),
        owner_id=user_id,
        billing_email=data.get('billing_email')
    )
    org.slug = org.generate_slug()
    db.session.add(org)
    db.session.flush()
    # Add creator as owner
    member = OrganizationMember(
        organization_id=org.id,
        user_id=user_id,
        role='owner'
    )
    db.session.add(member)
    db.session.commit()
    return _success({
        'message': 'Organization created',
        'organization': org.to_dict()
    }, status_code=201)
@org_bp.route('/', methods=['GET'])
@jwt_required()
def list_organizations():
    """List user's organizations."""
    user_id = get_jwt_identity()
    memberships = OrganizationMember.query.filter_by(user_id=user_id).all()

    if not memberships:
        user = User.query.get(user_id)
        if user:
            ensure_default_organization_membership(user)
            db.session.commit()
            memberships = OrganizationMember.query.filter_by(user_id=user_id).all()

    orgs = []
    for membership in memberships:
        org = membership.organization
        org_data = org.to_dict()
        org_data['organization_id'] = org.id
        org_data['role'] = membership.role
        org_data['my_role'] = membership.role
        orgs.append(org_data)
        
    return _success({
        'organizations': orgs,
        'organization_id': orgs[0]['organization_id'] if orgs else 1,
        'role': orgs[0]['role'] if orgs else 'system'
    })
@org_bp.route('/<int:org_id>', methods=['GET'])
@jwt_required()
def get_organization(org_id):
    """Get organization details."""
    user_id = get_jwt_identity()
    org = Organization.query.get(org_id)
    if not org:
        return _error('Organization not found', status_code=404)
    # Check membership
    member = OrganizationMember.query.filter_by(
        organization_id=org_id,
        user_id=user_id
    ).first()
    if not member:
        return _error('Access denied', status_code=403)
    data = org.to_dict()
    data['organization_id'] = org.id
    data['role'] = member.role
    data['my_role'] = member.role
    # Get members
    members = []
    for m in org.members:
        members.append({
            'id': m.user.id,
            'email': m.user.email,
            'name': f"{m.user.first_name} {m.user.last_name}",
            'role': m.role,
            'joined_at': m.joined_at.isoformat() if m.joined_at else None
        })
    data['members'] = members
    return _success(data)
@org_bp.route('/<int:org_id>/invite', methods=['POST'])
@jwt_required()
def invite_member(org_id):
    """Invite member to organization."""
    user_id = get_jwt_identity()
    # Check permissions
    member = OrganizationMember.query.filter_by(
        organization_id=org_id,
        user_id=user_id
    ).first()
    if not member or member.role not in ['owner', 'admin']:
        return _error('Insufficient permissions', status_code=403)
    data = request.get_json() or {}
    email = data.get('email', '').lower().strip()
    role = data.get('role', 'member')
    if role not in ['admin', 'member', 'viewer']:
        return _error('Invalid role', status_code=400)
    # Check if already member
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        existing_member = OrganizationMember.query.filter_by(
            organization_id=org_id,
            user_id=existing_user.id
        ).first()
        if existing_member:
            return _error('User already member', status_code=409)
    # Create invitation
    invitation = Invitation.create_invitation(org_id, email, role, user_id)
    db.session.add(invitation)
    db.session.commit()
    # Send invitation email
    from flask_mail import Message
    from app import mail
    try:
        org = Organization.query.get(org_id)
        msg = Message(
            f'Invitation to join {org.name}',
            recipients=[email]
        )
        invite_url = f"http://localhost:3000/accept-invite?token={invitation.token}"
        inviter = User.query.get(user_id)
        msg.body = f"""
        You've been invited to join {org.name} on Cloud Policy, Cost & Security Simulator.
        Invited by: {inviter.first_name} {inviter.last_name}
        Role: {role}
        Accept invitation: {invite_url}
        This link expires in 7 days.
        """
        mail.send(msg)
    except Exception as e:
        print(f"Failed to send invite: {e}")
    return _success({
        'message': 'Invitation sent',
        'invitation': {
            'email': email,
            'role': role,
            'expires_at': invitation.expires_at.isoformat()
        }
    }, status_code=201)
@org_bp.route('/accept-invite', methods=['POST'])
@jwt_required()
def accept_invitation():
    """Accept invitation."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    token = data.get('token')
    invitation = Invitation.query.filter_by(token=token, accepted=False).first()
    if not invitation:
        return _error('Invalid invitation', status_code=400)
    if invitation.expires_at < datetime.utcnow():
        return _error('Invitation expired', status_code=400)
    user = User.query.get(user_id)
    if user.email.lower() != invitation.email.lower():
        return _error('Invitation email mismatch', status_code=403)
    # Add to organization
    member = OrganizationMember(
        organization_id=invitation.organization_id,
        user_id=user_id,
        role=invitation.role
    )
    invitation.accepted = True
    db.session.add(member)
    db.session.commit()
    return _success({
        'message': 'Joined organization successfully',
        'organization_id': invitation.organization_id
    })
@org_bp.route('/<int:org_id>/members/<int:member_id>', methods=['DELETE'])
@jwt_required()
def remove_member(org_id, member_id):
    """Remove member from organization."""
    user_id = get_jwt_identity()
    # Check permissions
    current_member = OrganizationMember.query.filter_by(
        organization_id=org_id,
        user_id=user_id
    ).first()
    if not current_member or current_member.role not in ['owner', 'admin']:
        return _error('Insufficient permissions', status_code=403)
    target_member = OrganizationMember.query.get(member_id)
    if not target_member:
        return _error('Member not found', status_code=404)
    if target_member.organization_id != org_id:
        return _error('Member not in organization', status_code=400)
    # Cannot remove owner
    if target_member.role == 'owner':
        return _error('Cannot remove owner', status_code=403)
    db.session.delete(target_member)
    db.session.commit()
    return _success({'message': 'Member removed'})

@org_bp.route('/invite_demo', methods=['POST'])
@jwt_required()
def simple_invite():
    """Demo-safe invite that creates users and assigns roles without email."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    email = data.get('email', '').lower().strip()
    role = data.get('role', 'member')

    if not email:
        return _error('Email required', status_code=400)
    if role not in ['admin', 'member', 'viewer', 'owner']:
        return _error('Invalid role', status_code=400)

    memberships = OrganizationMember.query.filter_by(user_id=user_id).all()
    if not memberships:
        return _error('You must belong to an organization', status_code=400)
    
    org_id = data.get('organization_id') or memberships[0].organization_id

    current_member = OrganizationMember.query.filter_by(organization_id=org_id, user_id=user_id).first()
    if not current_member or current_member.role not in ['owner', 'admin']:
        return _error('Permission denied', status_code=403)

    target_user = User.query.filter_by(email=email).first()
    if not target_user:
        target_user = User(
            email=email,
            first_name=email.split('@')[0],
            last_name='User',
            is_active=True,
            email_verified=True
        )
        target_user.set_password('Demo1234')
        db.session.add(target_user)
        db.session.flush()

    existing_member = OrganizationMember.query.filter_by(organization_id=org_id, user_id=target_user.id).first()
    if existing_member:
        existing_member.role = role
    else:
        new_member = OrganizationMember(
            organization_id=org_id,
            user_id=target_user.id,
            role=role
        )
        db.session.add(new_member)

    db.session.commit()
    return _success({'message': f'User {email} added as {role}'}, status_code=200)

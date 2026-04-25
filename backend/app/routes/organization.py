from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.organization import Organization, OrganizationMember, Invitation
from app.models.user import User
from datetime import datetime
org_bp = Blueprint('organization', __name__)
@org_bp.route('/', methods=['POST'])
@jwt_required()
def create_organization():
    """Create new organization."""
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data.get('name'):
        return jsonify({'error': 'Organization name required'}), 400
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
    return jsonify({
        'message': 'Organization created',
        'organization': org.to_dict()
    }), 201
@org_bp.route('/', methods=['GET'])
@jwt_required()
def list_organizations():
    """List user's organizations."""
    user_id = get_jwt_identity()
    memberships = OrganizationMember.query.filter_by(user_id=user_id).all()
    orgs = []
    for membership in memberships:
        org = membership.organization
        org_data = org.to_dict()
        org_data['my_role'] = membership.role
        orgs.append(org_data)
    return jsonify({'organizations': orgs}), 200
@org_bp.route('/<int:org_id>', methods=['GET'])
@jwt_required()
def get_organization(org_id):
    """Get organization details."""
    user_id = get_jwt_identity()
    org = Organization.query.get_or_404(org_id)
    # Check membership
    member = OrganizationMember.query.filter_by(
        organization_id=org_id,
        user_id=user_id
    ).first()
    if not member:
        return jsonify({'error': 'Access denied'}), 403
    data = org.to_dict()
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
    return jsonify(data), 200
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
        return jsonify({'error': 'Insufficient permissions'}), 403
    data = request.get_json()
    email = data.get('email', '').lower().strip()
    role = data.get('role', 'member')
    if role not in ['admin', 'member', 'viewer']:
        return jsonify({'error': 'Invalid role'}), 400
    # Check if already member
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        existing_member = OrganizationMember.query.filter_by(
            organization_id=org_id,
            user_id=existing_user.id
        ).first()
        if existing_member:
            return jsonify({'error': 'User already member'}), 409
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
    return jsonify({
        'message': 'Invitation sent',
        'invitation': {
            'email': email,
            'role': role,
            'expires_at': invitation.expires_at.isoformat()
        }
    }), 201
@org_bp.route('/accept-invite', methods=['POST'])
@jwt_required()
def accept_invitation():
    """Accept invitation."""
    user_id = get_jwt_identity()
    token = request.json.get('token')
    invitation = Invitation.query.filter_by(token=token, accepted=False).first()
    if not invitation:
        return jsonify({'error': 'Invalid invitation'}), 400
    if invitation.expires_at < datetime.utcnow():
        return jsonify({'error': 'Invitation expired'}), 400
    user = User.query.get(user_id)
    if user.email.lower() != invitation.email.lower():
        return jsonify({'error': 'Invitation email mismatch'}), 403
    # Add to organization
    member = OrganizationMember(
        organization_id=invitation.organization_id,
        user_id=user_id,
        role=invitation.role
    )
    invitation.accepted = True
    db.session.add(member)
    db.session.commit()
    return jsonify({
        'message': 'Joined organization successfully',
        'organization_id': invitation.organization_id
    }), 200
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
        return jsonify({'error': 'Insufficient permissions'}), 403
    target_member = OrganizationMember.query.get_or_404(member_id)
    if target_member.organization_id != org_id:
        return jsonify({'error': 'Member not in organization'}), 400
    # Cannot remove owner
    if target_member.role == 'owner':
        return jsonify({'error': 'Cannot remove owner'}), 403
    db.session.delete(target_member)
    db.session.commit()
    return jsonify({'message': 'Member removed'}), 200

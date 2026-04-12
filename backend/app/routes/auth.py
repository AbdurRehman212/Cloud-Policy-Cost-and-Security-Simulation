from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from app import db, mail
from app.models.user import User, UserProfile, EmailVerification
from flask_mail import Message
import re
from datetime import datetime
auth_bp = Blueprint('auth', __name__)
def is_valid_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None
def is_valid_password(password):
    """Validate password strength."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain digit"
    return True, "Valid"
@auth_bp.route('/register', methods=['POST'])
def register():
    """Register new user."""
    data = request.get_json()
    # Validation
    required = ['email', 'password', 'first_name', 'last_name']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    email = data['email'].lower().strip()
    if not is_valid_email(email):
        return jsonify({'error': 'Invalid email format'}), 400
    valid_pwd, msg = is_valid_password(data['password'])
    if not valid_pwd:
        return jsonify({'error': msg}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409
    try:
        # Create user
        user = User(
            email=email,
            first_name=data['first_name'],
            last_name=data['last_name']
        )
        user.set_password(data['password'])
        db.session.add(user)
        db.session.flush()  # Get user.id without committing
        # Create profile
        profile = UserProfile(user_id=user.id)
        db.session.add(profile)
        # Create settings
        from app.models.settings import UserSettings
        settings = UserSettings(user_id=user.id)
        db.session.add(settings)
        # Create verification token
        verification = EmailVerification.create_token(user.id)
        db.session.add(verification)
        db.session.commit()
        # Send verification email
        send_verification_email(user.email, verification.token)
        return jsonify({
            'message': 'Registration successful. Please check your email to verify your account.',
            'user': user.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Registration failed', 'details': str(e)}), 500
def send_verification_email(email, token):
    """Send email verification."""
    try:
        msg = Message(
            'Verify Your Cloud Simulator Account',
            recipients=[email]
        )
        verify_url = f"http://localhost:3000/verify-email?token={token}"
        msg.body = f"""
        Welcome to Cloud Policy, Cost and Security Simulator!
        Please verify your email by clicking: {verify_url}
        This link expires in 24 hours.
        """
        mail.send(msg)
    except Exception as e:
        print(f"Failed to send email: {e}")
@auth_bp.route('/verify-email', methods=['GET'])
def verify_email():
    """Verify email with token."""
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'Token required'}), 400
    verification = EmailVerification.query.filter_by(token=token, used=False).first()
    if not verification:
        return jsonify({'error': 'Invalid or used token'}), 400
    if verification.is_expired():
        return jsonify({'error': 'Token expired'}), 400
    user = User.query.get(verification.user_id)
    user.email_verified = True
    user.is_active = True
    verification.used = True
    db.session.commit()
    return jsonify({'message': 'Email verified successfully. You can now log in.'}), 200
@auth_bp.route('/login', methods=['POST'])
def login():
    """User login."""
    data = request.get_json()
    email = data.get('email', '').lower().strip()
    password = data.get('password')
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401
    if not user.is_active:
        return jsonify({'error': 'Account not activated. Please verify your email.'}), 403
    # Update last login
    user.last_login = datetime.utcnow()
    db.session.commit()
    # Create tokens
    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)
    return jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user.to_dict()
    }), 200
@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token."""
    user_id = get_jwt_identity()
    access_token = create_access_token(identity=user_id)
    return jsonify({'access_token': access_token}), 200
@auth_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """Get user profile."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    return jsonify({
        'user': user.to_dict(),
        'profile': {
            'phone': user.profile.phone if user.profile else None,
            'department': user.profile.department if user.profile else None,
            'job_title': user.profile.job_title if user.profile else None
        }
    }), 200
@auth_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """Update user profile."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    if 'first_name' in data:
        user.first_name = data['first_name']
    if 'last_name' in data:
        user.last_name = data['last_name']
    if user.profile:
        if 'phone' in data:
            user.profile.phone = data['phone']
        if 'department' in data:
            user.profile.department = data['department']
        if 'job_title' in data:
            user.profile.job_title = data['job_title']
    db.session.commit()
    return jsonify({'message': 'Profile updated', 'user': user.to_dict()}), 200
@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """Request password reset."""
    email = request.json.get('email')
    user = User.query.filter_by(email=email).first()
    if user:
        # Generate reset token
        from app.models.user import EmailVerification
        reset = EmailVerification.create_token(user.id)
        db.session.add(reset)
        db.session.commit()
        # Send email
        try:
            msg = Message('Password Reset Request', recipients=[email])
            reset_url = f"http://localhost:3000/reset-password?token={reset.token}"
            msg.body = f"Reset your password: {reset_url}"
            mail.send(msg)
        except:
            pass
    # Always return success to prevent email enumeration
    return jsonify({'message': 'If email exists, reset instructions sent'}), 200
@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """Change password."""
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    if not user.check_password(data.get('current_password')):
        return jsonify({'error': 'Current password incorrect'}), 400
    valid, msg = is_valid_password(data.get('new_password'))
    if not valid:
        return jsonify({'error': msg}), 400
    user.set_password(data['new_password'])
    db.session.commit()
    return jsonify({'message': 'Password changed successfully'}), 200

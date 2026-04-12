from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.settings import UserSettings, NotificationPreference
settings_bp = Blueprint('settings', __name__)
@settings_bp.route('/', methods=['GET'])
@jwt_required()
def get_settings():
    """Get user settings."""
    user_id = get_jwt_identity()
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.session.add(settings)
        db.session.commit()
    notifications = NotificationPreference.query.filter_by(user_id=user_id).first()
    if not notifications:
        notifications = NotificationPreference(user_id=user_id)
        db.session.add(notifications)
        db.session.commit()
    return jsonify({
        'dashboard': {
            'default_organization_id': settings.default_organization_id,
            'dashboard_layout': settings.dashboard_layout,
            'default_view': settings.default_view
        },
        'appearance': {
            'theme': settings.theme,
            'language': settings.language,
            'timezone': settings.timezone,
            'date_format': settings.date_format
        },
        'notifications': {
            'email': settings.email_notifications,
            'push': settings.push_notifications,
            'sms': settings.sms_notifications,
            'preferences': {
                'cost_alerts': notifications.cost_alert_enabled if notifications else True,
                'security_alerts': notifications.security_alert_enabled if notifications else True,
                'cost_threshold': notifications.cost_alert_threshold if notifications else 80
            }
        },
        'security': {
            'login_notifications': settings.login_notifications,
            'suspicious_activity_alerts': settings.suspicious_activity_alerts,
            'session_timeout': settings.session_timeout
        }
    }), 200
@settings_bp.route('/', methods=['PUT'])
@jwt_required()
def update_settings():
    """Update user settings."""
    user_id = get_jwt_identity()
    data = request.get_json()
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.session.add(settings)
    # Update dashboard settings
    if 'dashboard' in data:
        d = data['dashboard']
        if 'default_organization_id' in d:
            settings.default_organization_id = d['default_organization_id']
        if 'default_view' in d:
            settings.default_view = d['default_view']
    # Update appearance
    if 'appearance' in data:
        a = data['appearance']
        if 'theme' in a:
            settings.theme = a['theme']
        if 'timezone' in a:
            settings.timezone = a['timezone']
    # Update notifications
    if 'notifications' in data:
        n = data['notifications']
        if 'email' in n:
            settings.email_notifications = n['email']
        if 'push' in n:
            settings.push_notifications = n['push']
    db.session.commit()
    return jsonify({'message': 'Settings updated'}), 200

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.settings import UserSettings, NotificationPreference
settings_bp = Blueprint('settings', __name__)


def _success(data, status_code=200):
    return jsonify({'status': 'success', 'data': data}), status_code


def _default_settings_payload():
    return {
        'theme': 'light',
        'notifications_enabled': True,
        'dashboard': {
            'default_organization_id': None,
            'dashboard_layout': 'default',
            'default_view': 'overview',
        },
        'appearance': {
            'theme': 'light',
            'language': 'en',
            'timezone': 'Asia/Karachi',
            'date_format': 'YYYY-MM-DD',
        },
        'notifications': {
            'email': True,
            'push': True,
            'sms': False,
            'preferences': {
                'cost_alerts': True,
                'security_alerts': True,
                'cost_threshold': 80,
            },
        },
        'security': {
            'login_notifications': True,
            'suspicious_activity_alerts': True,
            'session_timeout': 60,
        },
    }


@settings_bp.route('', methods=['GET'])
def get_demo_settings():
    """Return demo-safe settings when no authenticated profile is required."""
    return _success(_default_settings_payload())


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
    return _success({
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
    })
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
    return _success({'message': 'Settings updated'})

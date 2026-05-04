from datetime import datetime
from app import db
class UserSettings(db.Model):
    """User preferences and settings."""
    __tablename__ = 'user_settings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Dashboard
    default_organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    dashboard_layout = db.Column(db.JSON, default=dict)  # Widget positions
    default_view = db.Column(db.String(20), default='grid')  # grid, list, map
    # Appearance
    theme = db.Column(db.String(20), default='light')  # light, dark, auto
    language = db.Column(db.String(10), default='en')
    timezone = db.Column(db.String(50), default='UTC')
    date_format = db.Column(db.String(20), default='YYYY-MM-DD')
    # Notifications
    email_notifications = db.Column(db.Boolean, default=True)
    push_notifications = db.Column(db.Boolean, default=True)
    sms_notifications = db.Column(db.Boolean, default=False)
    # Security
    login_notifications = db.Column(db.Boolean, default=True)
    suspicious_activity_alerts = db.Column(db.Boolean, default=True)
    session_timeout = db.Column(db.Integer, default=30)  # minutes
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
class NotificationPreference(db.Model):
    """Detailed notification preferences."""
    __tablename__ = 'notification_preferences'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Cost alerts
    cost_alert_enabled = db.Column(db.Boolean, default=True)
    cost_alert_threshold = db.Column(db.Float, default=80.0)
    # Security alerts
    security_alert_enabled = db.Column(db.Boolean, default=True)
    security_alert_severity = db.Column(db.String(20), default='medium')  # low, medium, high
    # Compliance alerts
    compliance_alert_enabled = db.Column(db.Boolean, default=True)
    # System notifications
    maintenance_notifications = db.Column(db.Boolean, default=True)
    feature_announcements = db.Column(db.Boolean, default=True)
    # Channels
    email_cost_alerts = db.Column(db.Boolean, default=True)
    email_security_alerts = db.Column(db.Boolean, default=True)
    in_app_cost_alerts = db.Column(db.Boolean, default=True)
    in_app_security_alerts = db.Column(db.Boolean, default=True)

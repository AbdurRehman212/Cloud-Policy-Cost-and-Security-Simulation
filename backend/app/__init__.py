from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_mail import Mail
from flask_socketio import SocketIO
from app.config import config
# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
mail = Mail()
socketio = SocketIO(cors_allowed_origins="*")
def create_app(config_name='default'):
    """Application factory pattern."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    mail.init_app(app)
    socketio.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.organization import org_bp
    from app.routes.resources import resource_bp
    from app.routes.governance import governance_bp
    from app.routes.security import security_bp
    from app.routes.cost import cost_bp
    from app.routes.reports import reports_bp
    from app.routes.settings import settings_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.assistant import assistant_bp
    from app.routes.membership import membership_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(org_bp, url_prefix='/api/org')
    app.register_blueprint(resource_bp, url_prefix='/api/resources')
    app.register_blueprint(governance_bp, url_prefix='/api/governance')
    app.register_blueprint(security_bp, url_prefix='/api/security')
    app.register_blueprint(cost_bp, url_prefix='/api/cost')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(settings_bp, url_prefix='/api/settings')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(assistant_bp, url_prefix='/api/assistant')
    app.register_blueprint(membership_bp, url_prefix='/api/membership')
    # Create database tables
    with app.app_context():
        db.create_all()
    return app

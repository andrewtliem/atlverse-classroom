import os
import logging
from dotenv import load_dotenv
from flask_migrate import Migrate

# Load environment variables from .env file
load_dotenv()

from flask import Flask
from flask_login import LoginManager, current_user
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import date

from extensions import db, Base # Import db and Base from new extensions.py

from ai_service import AIService
# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Initialize extensions
# db = SQLAlchemy(model_class=Base) # Removed - now in extensions.py
login_manager = LoginManager()
csrf = CSRFProtect()

# Create the Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET", "dev-secret-key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Add chr function to Jinja2 globals
app.jinja_env.globals['chr'] = chr

# Configure the database
database_url = os.getenv("DATABASE_URL")

# Added safeguard: If the env var contains '=', take the part after it.
# This handles cases where load_dotenv might not parse correctly.
if database_url and '=' in database_url:
    database_url = database_url.split('=', 1)[1]

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///classroom.db"
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

# Initialize Flask extensions
db.init_app(app)
migrate = Migrate(app, db)
login_manager.init_app(app)
csrf.init_app(app)
login_manager.login_view = 'auth_login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@app.context_processor
def inject_unread_notifications_count():
    if current_user.is_authenticated:
        from models import Notification
        count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    else:
        count = 0
    return {'unread_notifications_count': count}


@app.context_processor
def inject_daily_quote():
    from models import DailyQuoteCache
    today = date.today()
    cached = DailyQuoteCache.query.filter_by(date=today).first()
    if cached:
        quote = cached.quote
    else:
        try:
            quote = AIService().get_daily_quote()
        except Exception as e:
            logging.error(f"Daily quote retrieval failed: {e}")
            quote = "Keep learning!"
        db.session.add(DailyQuoteCache(date=today, quote=quote))
        db.session.commit()
    return {'daily_quote': quote}

# User loader
@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Create upload folder if it doesn't exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Application context: import models & routes, optionally create tables
with app.app_context():
    import models  # ensure models are loaded
    import routes  # ensure routes are registered

    # Optionally create tables (not needed if using flask-migrate)
    # db.create_all()

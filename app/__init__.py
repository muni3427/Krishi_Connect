from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from dotenv import load_dotenv
import os

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///agriconnect.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["DATA_GOV_API_KEY"] = os.environ.get("DATA_GOV_API_KEY", "")
    app.config["SARVAM_API_KEY"] = os.environ.get("SARVAM_API_KEY", "")
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    from app.blueprints.auth import auth_bp
    from app.blueprints.farmer import farmer_bp
    from app.blueprints.dealer import dealer_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.api import api_bp
    from app.blueprints.auth import root_bp
    from app.services.market_prices import fetch_and_store_prices
    app.register_blueprint(root_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(farmer_bp)
    app.register_blueprint(dealer_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    with app.app_context():
            from app import models
            db.create_all()

    # APScheduler — auto-fetch mandi prices at 9AM daily
    from apscheduler.schedulers.background import BackgroundScheduler
    import atexit

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: fetch_and_store_prices(app),  # passes app so it can build its own context
        trigger='cron',
        hour=9,
        minute=0,
        id='daily_price_fetch',
        replace_existing=True
    )
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))

    return app
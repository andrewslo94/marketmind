"""
app/__init__.py — the application factory.

create_app() builds and configures the Flask app. Using a factory function
(instead of a global `app = Flask(...)`) makes it easy to create separate
apps for testing and to plug in blueprints, the database, and login later.
"""
import os

from flask import Flask

from app.extensions import csrf, db, login_manager
from config import Config


def create_app(config_class=Config):
    # instance_relative_config=True tells Flask the instance/ folder lives at
    # the project root — that's where the SQLite database goes.
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # Fail fast with a clear message if the secret key is missing.
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is missing. Make sure the .env file exists in the "
            "project root and contains a SECRET_KEY=... line."
        )

    # Create the instance/ folder if it doesn't exist yet (SQLite DB lives here).
    os.makedirs(app.instance_path, exist_ok=True)

    # Attach the extensions (created in app/extensions.py) to this app.
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Import the models so SQLAlchemy knows which tables exist, then create
    # any tables that are missing. Existing tables and data are left alone.
    from app import models  # noqa: F401  (imported for its side effect)

    with app.app_context():
        db.create_all()

    # Register blueprints (groups of routes). Imported here, inside the
    # function, so each blueprint is loaded when the app is built.
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.market import market_bp
    from app.routes.news import news_bp
    from app.routes.portfolio import portfolio_bp
    from app.routes.stocks import stocks_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(portfolio_bp)
    app.register_blueprint(stocks_bp)
    app.register_blueprint(news_bp)
    app.register_blueprint(market_bp)

    # Terminal commands, e.g. `flask --app run refresh-fundamentals` (app/cli.py).
    from app.cli import register_cli

    register_cli(app)

    return app

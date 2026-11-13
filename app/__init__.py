"""
app/__init__.py — the application factory.

create_app() builds and configures the Flask app. Using a factory function
(instead of a global `app = Flask(...)`) makes it easy to create separate
apps for testing and to plug in blueprints, the database, and login later.
"""
import os

from flask import Flask, render_template

from config import Config


def create_app(config_class=Config):
    # instance_relative_config=True tells Flask the instance/ folder lives at
    # the project root — that's where the SQLite database will go in Phase 2.
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # Fail fast with a clear message if the secret key is missing.
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is missing. Make sure the .env file exists in the "
            "project root and contains a SECRET_KEY=... line."
        )

    # Create the instance/ folder if it doesn't exist yet.
    os.makedirs(app.instance_path, exist_ok=True)

    # Temporary home route. In Phase 1B this moves into a "main" blueprint.
    @app.route("/")
    def home():
        return render_template("home.html")

    return app

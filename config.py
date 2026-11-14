"""
config.py — central settings for MarketMind.

Reads secrets from the .env file (via python-dotenv) so that nothing
sensitive is ever hardcoded in the source code.
"""
import os

from dotenv import load_dotenv

# Absolute path of the folder this file lives in (the project root).
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Load key=value pairs from .env into environment variables.
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    """Default settings. Later phases add API-key settings here."""

    # Used by Flask to sign session cookies (logins). Must stay secret.
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # --- Database ---
    # SQLAlchemy connects using a "database URL". For SQLite that is just a
    # file path. Default: instance/marketmind.db inside the project.
    # Switching to PostgreSQL later is a one-line change in .env, e.g.
    #   DATABASE_URL=postgresql://user:password@host/dbname
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "marketmind.db"),
    )

    # Turns off a legacy change-tracking feature that uses extra memory.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

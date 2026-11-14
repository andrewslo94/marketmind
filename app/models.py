"""
app/models.py — database tables, written as Python classes.

Each class that extends db.Model becomes one table. Each db.Column becomes
one column. SQLAlchemy (an ORM, Object-Relational Mapper) translates between
Python objects and SQL rows, so we never write raw SQL by hand.
"""
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager


def utcnow():
    """Current time in UTC. Stored in the DB so timestamps are unambiguous."""
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    """
    A registered MarketMind user.

    UserMixin (from Flask-Login) adds the small set of properties that
    Flask-Login needs: is_authenticated, is_active, get_id(), etc.
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    # We store only a *hash* of the password, never the password itself.
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # --- Password helpers ---
    def set_password(self, password: str) -> None:
        """Hash the plain-text password and store the hash."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Return True if the plain-text password matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        # Shown when you print a User in the shell — handy for debugging.
        return f"<User {self.username}>"


@login_manager.user_loader
def load_user(user_id: str):
    """
    Flask-Login stores only the user's id in the session cookie. On each
    request it calls this function to turn that id back into a User object.
    """
    return db.session.get(User, int(user_id))

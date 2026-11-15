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


class Holding(db.Model):
    """
    One stock position in a user's portfolio, e.g. "10 shares of AAPL bought
    at an average of $150.00".

    One row per (user, ticker). If a user buys the same stock again, they
    update the share count and average price instead of adding a second row.
    Live prices are NOT stored here: they change constantly, so they are
    fetched (and cached) by a service in Phase 3B, not kept in the database.
    """

    __tablename__ = "holdings"

    id = db.Column(db.Integer, primary_key=True)

    # ForeignKey: this column must match the id of a row in the users table.
    # ondelete="CASCADE" + the relationship below mean deleting a user also
    # deletes that user's holdings, so no orphan rows are left behind.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ticker = db.Column(db.String(10), nullable=False)
    # Float is used for shares and price. Fractional shares (e.g. 2.5) are
    # common with modern brokers, and every calculation in Phase 3 runs in
    # pandas, which works in floats anyway.
    shares = db.Column(db.Float, nullable=False)
    avg_price = db.Column(db.Float, nullable=False)
    # Optional: not everyone remembers when they bought.
    purchase_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.String(200), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    # Database-level rule: the same user can't have two rows for one ticker.
    # The form checks this too (friendlier message); this is the safety net.
    __table_args__ = (
        db.UniqueConstraint("user_id", "ticker", name="uq_holding_user_ticker"),
    )

    # relationship(): lets us write `holding.owner` to get the User, and
    # `user.holdings` to get a list of that user's Holding rows.
    owner = db.relationship(
        "User",
        backref=db.backref(
            "holdings", lazy=True, cascade="all, delete-orphan", order_by="Holding.ticker"
        ),
    )

    # @property makes a method usable like an attribute: holding.cost_basis
    # (no parentheses). It is calculated on the fly, never stored.
    @property
    def cost_basis(self) -> float:
        """Total amount invested in this position: shares x average price."""
        return self.shares * self.avg_price

    def __repr__(self) -> str:
        return f"<Holding {self.ticker} x{self.shares} (user {self.user_id})>"

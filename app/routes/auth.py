"""
app/routes/auth.py — registration, login, and logout.

Flask-Login does the session bookkeeping:
  login_user(user)   -> stores the user's id in a signed cookie
  logout_user()      -> clears it
  current_user       -> the User for this request (or an anonymous object)
  @login_required    -> redirects logged-out visitors to the login page
"""
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.forms import LoginForm, RegistrationForm
from app.models import User

auth_bp = Blueprint("auth", __name__)


def _safe_next_url(default: str) -> str:
    """
    Flask-Login adds ?next=/some/page when it redirects a logged-out user to
    the login page. We only honour it if it's a *relative* path on our own
    site, so nobody can craft a link that bounces users to another domain.
    """
    next_url = request.args.get("next")
    if next_url and not urlsplit(next_url).netloc and next_url.startswith("/"):
        return next_url
    return default


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data.strip(),
            email=form.email.data.strip().lower(),
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        flash("Account created. You can log in now.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()

        # Same message whether the username or the password is wrong, so an
        # attacker can't use the login page to discover which usernames exist.
        if user is None or not user.check_password(form.password.data):
            flash("Invalid username or password.", "danger")
            return render_template("auth/login.html", form=form), 401

        login_user(user, remember=form.remember_me.data)
        flash(f"Welcome back, {user.username}.", "success")
        return redirect(_safe_next_url(url_for("main.home")))

    return render_template("auth/login.html", form=form)


# Logout is a POST (a small form in the navbar) rather than a GET link, so a
# third-party page can't log users out just by embedding an image URL.
@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))

"""
app/routes/main.py — general pages (home page for now).

A Blueprint is a group of related routes. Instead of attaching every route
to the app directly, each area of the site gets its own blueprint, and
create_app() registers them all. This keeps routes organized as the app grows.
"""
from flask import Blueprint, render_template

# "main" is the blueprint's name. Templates link to its pages with
# url_for("main.home").
main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    return render_template("home.html")

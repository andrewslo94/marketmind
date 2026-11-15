"""
app/routes/portfolio.py — the user's portfolio: list, add, edit, delete holdings.

Every route here is @login_required, and every database query is filtered
by current_user.id, so a user can only ever see or change their own rows.
Phase 3A stores positions only; live prices and gain/loss arrive in 3B via
a market-data service (routes never call external APIs directly).
"""
from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms import HoldingForm
from app.models import Holding

portfolio_bp = Blueprint("portfolio", __name__, url_prefix="/portfolio")


# ---------- Template filters (reusable number formatting) ----------
# app_template_filter registers the filter app-wide, so later pages
# (stock detail, dashboard totals) can use {{ value|money }} too.
@portfolio_bp.app_template_filter("money")
def money(value) -> str:
    """1234.5 -> '$1,234.50'. Shows 'Data unavailable' for None."""
    if value is None:
        return "Data unavailable"
    return f"${value:,.2f}"


@portfolio_bp.app_template_filter("shares")
def shares_fmt(value) -> str:
    """10.0 -> '10', 2.5 -> '2.5', 0.1234 -> '0.1234' (up to 4 decimals)."""
    if value is None:
        return "—"
    text = f"{value:,.4f}".rstrip("0").rstrip(".")
    return text or "0"


# ---------- Helpers ----------
def _get_own_holding(holding_id: int) -> Holding:
    """
    Load a holding that belongs to the logged-in user, or stop with 404.
    Using 404 (not 403) for someone else's row avoids confirming that the
    row exists at all.
    """
    holding = Holding.query.filter_by(id=holding_id, user_id=current_user.id).first()
    if holding is None:
        abort(404)
    return holding


# ---------- Routes ----------
@portfolio_bp.route("/")
@login_required
def dashboard():
    holdings = (
        Holding.query.filter_by(user_id=current_user.id)
        .order_by(Holding.ticker)
        .all()
    )
    total_invested = sum(h.cost_basis for h in holdings)
    return render_template(
        "portfolio/dashboard.html",
        holdings=holdings,
        total_invested=total_invested,
    )


@portfolio_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_holding():
    form = HoldingForm()
    if form.validate_on_submit():
        holding = Holding(
            user_id=current_user.id,
            ticker=form.ticker.data,
            shares=float(form.shares.data),
            avg_price=float(form.avg_price.data),
            purchase_date=form.purchase_date.data,
            notes=(form.notes.data or "").strip() or None,
        )
        db.session.add(holding)
        db.session.commit()
        flash(f"Added {holding.ticker} to your portfolio.", "success")
        return redirect(url_for("portfolio.dashboard"))

    return render_template("portfolio/holding_form.html", form=form, mode="add")


@portfolio_bp.route("/<int:holding_id>/edit", methods=["GET", "POST"])
@login_required
def edit_holding(holding_id: int):
    holding = _get_own_holding(holding_id)
    # obj=holding pre-fills the form with the row's current values on GET.
    form = HoldingForm(obj=holding, holding_id=holding.id)
    if form.validate_on_submit():
        holding.ticker = form.ticker.data
        holding.shares = float(form.shares.data)
        holding.avg_price = float(form.avg_price.data)
        holding.purchase_date = form.purchase_date.data
        holding.notes = (form.notes.data or "").strip() or None
        db.session.commit()
        flash(f"Updated {holding.ticker}.", "success")
        return redirect(url_for("portfolio.dashboard"))

    return render_template(
        "portfolio/holding_form.html", form=form, mode="edit", holding=holding
    )


# Delete is POST-only (a small form with a CSRF token), never a GET link,
# so a crafted link or image tag can't delete a user's data.
@portfolio_bp.route("/<int:holding_id>/delete", methods=["POST"])
@login_required
def delete_holding(holding_id: int):
    holding = _get_own_holding(holding_id)
    ticker = holding.ticker
    db.session.delete(holding)
    db.session.commit()
    flash(f"Removed {ticker} from your portfolio.", "info")
    return redirect(url_for("portfolio.dashboard"))

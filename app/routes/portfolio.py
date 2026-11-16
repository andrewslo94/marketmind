"""
app/routes/portfolio.py — the user's portfolio: list, add, edit, delete holdings.

Every route here is @login_required, and every database query is filtered
by current_user.id, so a user can only ever see or change their own rows.
Phase 3A stores positions only; live prices and gain/loss arrive in 3B via
a market-data service (routes never call external APIs directly).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms import HoldingForm
from app.models import Holding
from app.services.market_data import SOURCE, get_quote, normalize_ticker
from app.services.portfolio_calc import allocation_chart_data, build_portfolio

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


@portfolio_bp.app_template_filter("signed_money")
def signed_money(value) -> str:
    """-12.5 -> '-$12.50', 3 -> '+$3.00' (sign always shown for changes)."""
    if value is None:
        return "—"
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.2f}"


@portfolio_bp.app_template_filter("pct")
def pct(value, signed=True) -> str:
    """1.234 -> '+1.23%'; None -> '—'."""
    if value is None:
        return "—"
    return f"{value:+.2f}%" if signed else f"{value:.2f}%"


@portfolio_bp.app_template_filter("big_number")
def big_number(value) -> str:
    """5177380000000 -> '$5.18T' for market caps and volumes."""
    if value is None:
        return "Data unavailable"
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(value) >= size:
            return f"{value / size:,.2f}{unit}"
    return f"{value:,.0f}"


ET = ZoneInfo("America/New_York")


@portfolio_bp.app_template_filter("et_time")
def et_time(value: datetime) -> str:
    """UTC datetime -> 'Nov 13, 4:00 PM ET' (US market time)."""
    if value is None:
        return "time unavailable"
    local = value.astimezone(ET)
    return local.strftime("%b %d, %-I:%M %p ET")


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


def _warn_if_unverified(form: HoldingForm) -> None:
    """The form sets ticker_unverified when the data provider was unreachable."""
    if getattr(form, "ticker_unverified", False):
        flash(
            f"Could not verify {form.ticker.data} with the data provider right now. "
            "It was saved, but double-check the symbol.",
            "warning",
        )


# ---------- Routes ----------
@portfolio_bp.route("/")
@login_required
def dashboard():
    holdings = (
        Holding.query.filter_by(user_id=current_user.id)
        .order_by(Holding.ticker)
        .all()
    )
    # The calculation service combines holdings with cached quotes; the
    # route only passes the results to the template.
    summary = build_portfolio(holdings)
    return render_template(
        "portfolio/dashboard.html",
        summary=summary,
        chart=allocation_chart_data(summary),
        source=SOURCE,
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
        _warn_if_unverified(form)
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
        _warn_if_unverified(form)
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


# ---------- JSON helper for the add/edit form ----------
# The form's JavaScript calls this when the ticker field loses focus, to
# show the company name and current (delayed) price. jsonify() turns a dict
# into an HTTP response with JSON text, which the browser's fetch() reads.
# Goes through the cache like everything else, so typing AAPL twice costs
# one provider call at most every 15 minutes.
@portfolio_bp.route("/quote/<ticker>")
@login_required
def quote_lookup(ticker: str):
    ticker = normalize_ticker(ticker)
    if not (1 <= len(ticker) <= 10):
        return jsonify(ok=False, reason="invalid"), 400
    try:
        result = get_quote(ticker)
    except Exception:  # noqa: BLE001 — provider unreachable, no cached copy
        return jsonify(ok=False, reason="unavailable"), 503

    q = result.value
    if q is None:
        return jsonify(ok=False, reason="not_found", ticker=ticker), 404

    return jsonify(
        ok=True,
        ticker=q["ticker"],
        name=q["name"],
        price=q["price"],
        currency=q["currency"],
        market_time=q["market_time"],      # Yahoo's quote timestamp (UTC ISO)
        market_state=q["market_state"],
        fetched_at=result.fetched_at.isoformat(),
        stale=result.stale,
        delayed=True,
        source=q["source"],
    )

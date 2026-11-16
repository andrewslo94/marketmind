"""
app/routes/stocks.py — one page per ticker: the full delayed quote plus an
interactive price-history chart.

Two routes:
  GET /stocks/<ticker>              the page
  GET /stocks/<ticker>/history.json?range=1M
                                    chart data for one range (called by
                                    static/js/stock_chart.js when a range
                                    button is clicked)
Both are login-protected so only signed-in users trigger provider calls.
"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from app.models import Holding
from app.services.market_data import (
    HISTORY_RANGES,
    SOURCE,
    get_history,
    get_quote,
    normalize_ticker,
)

stocks_bp = Blueprint("stocks", __name__, url_prefix="/stocks")

ET = ZoneInfo("America/New_York")
TICKER_RE = re.compile(r"^[A-Z]{1,5}([.-][A-Z]{1,2})?$")


def _r(value, places: int = 4):
    return None if value is None else round(value, places)


@stocks_bp.route("/<ticker>")
@login_required
def detail(ticker: str):
    ticker = normalize_ticker(ticker)
    if not TICKER_RE.match(ticker):
        return render_template("stocks/not_found.html", ticker=ticker), 404

    try:
        result = get_quote(ticker)
    except Exception:  # noqa: BLE001 — provider down and nothing cached
        return render_template("stocks/not_found.html", ticker=ticker, unavailable=True), 503

    quote = result.value
    if quote is None:
        return render_template("stocks/not_found.html", ticker=ticker), 404

    # If the user owns this stock, show their position on the page too.
    holding = Holding.query.filter_by(user_id=current_user.id, ticker=ticker).first()

    return render_template(
        "stocks/detail.html",
        q=quote,
        fetched_at=result.fetched_at,
        stale=result.stale,
        holding=holding,
        ranges=list(HISTORY_RANGES),
        source=SOURCE,
    )


@stocks_bp.route("/<ticker>/history.json")
@login_required
def history_json(ticker: str):
    """
    Price history for the chart. Timestamps are converted to US Eastern
    time and sent WITHOUT a timezone suffix, because plotly.js plots date
    strings exactly as given — so the axis reads in market time.
    """
    ticker = normalize_ticker(ticker)
    range_key = request.args.get("range", "1M").upper()
    if not TICKER_RE.match(ticker) or range_key not in HISTORY_RANGES:
        return jsonify(ok=False, reason="invalid"), 400

    try:
        result = get_history(ticker, range_key)
    except Exception as exc:  # noqa: BLE001
        return jsonify(ok=False, reason="unavailable", detail=str(exc)), 503

    period, interval, _ttl = HISTORY_RANGES[range_key]
    intraday = interval.endswith("m")  # "5m", "30m" -> minute bars

    points = []
    for row in result.value or []:
        ts = datetime.fromisoformat(row["t"]).astimezone(ET)
        points.append(
            {
                "t": ts.strftime("%Y-%m-%d %H:%M" if intraday else "%Y-%m-%d"),
                # round(): the provider returns float noise like 356.39999389
                "o": _r(row["o"]),
                "h": _r(row["h"]),
                "l": _r(row["l"]),
                "c": _r(row["c"]),
                "v": row["v"],
            }
        )

    return jsonify(
        ok=True,
        ticker=ticker,
        range=range_key,
        interval=interval,
        intraday=intraday,
        points=points,
        fetched_at=result.fetched_at.isoformat(),
        stale=result.stale,
        source=SOURCE,
        delayed=True,
        timezone="America/New_York",
    )

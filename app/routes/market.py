"""
app/routes/market.py — Section C, Market Overview.

GET /market/                          the page: indexes, Treasury yields, commodities,
                                      and U.S. economic indicators (FRED)
GET /market/performance.json?range=   chart data: % change of three U.S. indexes
                                      (called by static/js/market_chart.js)
GET /market/developments              market news grouped into topics, with
                                      rule-based sector impact (interpretation)

Login-protected like the other data pages, so only signed-in users trigger
provider calls. All data and calculations live in services/market_overview.py
and services/fred_service.py.
"""
from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from app.services.fred_service import build_indicators
from app.services.market_data import SOURCE
from app.services.market_news import FACT_ARTICLES_SHOWN, build_developments
from app.services.market_overview import PERFORMANCE_RANGES, build_overview, index_performance

market_bp = Blueprint("market", __name__, url_prefix="/market")

DEFAULT_RANGE = "1Y"


@market_bp.route("/")
@login_required
def index():
    return render_template(
        "market/index.html",
        ov=build_overview(),
        econ=build_indicators(),
        ranges=PERFORMANCE_RANGES,
        default_range=DEFAULT_RANGE,
        source=SOURCE,
    )


@market_bp.route("/performance.json")
@login_required
def performance_json():
    range_key = request.args.get("range", DEFAULT_RANGE).upper()
    if range_key not in PERFORMANCE_RANGES:
        return jsonify(ok=False, reason="invalid"), 400

    data = index_performance(range_key)
    if not data["series"]:
        return jsonify(ok=False, reason="unavailable", failed=data["failed"]), 503

    return jsonify(ok=True, source=SOURCE, delayed=True, timezone="America/New_York", **data)


@market_bp.route("/developments")
@login_required
def developments():
    return render_template("market/developments.html", dev=build_developments(), shown=FACT_ARTICLES_SHOWN)

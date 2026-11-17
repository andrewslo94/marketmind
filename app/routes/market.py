"""
app/routes/market.py — Section C, Market Overview.

GET /market/                          the page: indexes, Treasury yields, commodities
GET /market/performance.json?range=   chart data: % change of three U.S. indexes
                                      (called by static/js/market_chart.js)

Login-protected like the other data pages, so only signed-in users trigger
provider calls. All data and calculations live in services/market_overview.py.
"""
from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from app.services.market_data import SOURCE
from app.services.market_overview import PERFORMANCE_RANGES, build_overview, index_performance

market_bp = Blueprint("market", __name__, url_prefix="/market")

DEFAULT_RANGE = "1Y"


@market_bp.route("/")
@login_required
def index():
    return render_template(
        "market/index.html",
        ov=build_overview(),
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

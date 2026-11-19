"""
app/routes/research.py — Section D, the Investment Research Engine.

GET /research/            companies the user doesn't hold with the strongest
                          research case, plus a table of all 64 companies
GET /research/<ticker>    one company's full research page

Scores come from the saved batch (scoring.load_snapshot), calculated by
`flask --app run research-scores`: scoring every company needs ~64 news
calls and Finnhub allows 60 a minute, so pages never score on the fly. Pages
add live (delayed) prices and news only for what they show.
"""
from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from app.models import Holding
from app.services import research_data as rd
from app.services.market_data import get_quote, get_quotes
from app.services.market_news import build_developments
from app.services.news_service import get_company_news
from app.services.portfolio_calc import build_portfolio, sector_exposure
from app.services.scoring import DISCLAIMER, WEIGHTS, explain_opportunity, load_snapshot
from app.services.sentiment import analyze_article

research_bp = Blueprint("research", __name__, url_prefix="/research")

CONCENTRATION_WARNING = 25.0  # % of portfolio value in one sector counts as heavy
OUTLOOK_CLASS = {"Positive": "positive", "Neutral": "either", "Negative": "negative"}


def _portfolio_context():
    """The user's holdings, the tickers they hold, and their sector exposure."""
    holdings = Holding.query.filter_by(user_id=current_user.id).all()
    return {h.ticker for h in holdings}, sector_exposure(build_portfolio(holdings))


def concentration_check(sector: str, exposure: dict) -> dict:
    """
    Diversification check for adding a company in `sector`. A fact about the
    user's own portfolio (share of current value), never advice.
    level: "heavy" (>= CONCENTRATION_WARNING %), "some", "none", or "empty" (no holdings).
    """
    if not exposure["has_holdings"]:
        return {"level": "empty", "pct": 0.0, "tickers": [], "funds": []}
    info = exposure["sectors"].get(sector)
    funds = [u["ticker"] for u in exposure["unclassified"] if u.get("pct")]
    if not info:
        return {"level": "none", "pct": 0.0, "tickers": [], "funds": funds}
    level = "heavy" if info["pct"] >= CONCENTRATION_WARNING else "some"
    return {"level": level, "pct": info["pct"], "tickers": info["tickers"], "funds": funds}


def _coverage_topics() -> dict:
    """ticker -> names of current market-coverage topics that name the company."""
    try:
        developments = build_developments()["developments"]
    except Exception:  # noqa: BLE001 — coverage is a bonus; the page works without it
        return {}
    named = {}
    for d in developments:
        for c in d.mentioned:
            named.setdefault(c["ticker"], []).append(d.name)
    return named


@research_bp.route("/")
@login_required
def index():
    snap = load_snapshot()
    held, exposure = _portfolio_context()
    if snap is None:
        return render_template("research/index.html", snap=None, disclaimer=DISCLAIMER)

    cards = snap["cards"]
    candidates = [c for c in cards if c["ticker"] not in held and c["overall"] is not None]
    picks = [c for c in candidates if c["outlook"] == "Positive"]
    fallback = not picks
    if fallback:  # nothing reaches the positive threshold: show the highest scores, and say so
        picks = candidates[:5]

    topics = _coverage_topics()
    quotes = get_quotes([c["ticker"] for c in picks])
    opportunities = []
    for rank, card in enumerate(picks, start=1):
        result = quotes.get(card["ticker"])
        opportunities.append({
            "card": card,  # the saved card is shared by the cache: never modified here
            "why": explain_opportunity(card, rank, len(candidates), topics.get(card["ticker"])),
            "check": concentration_check(card["sector"], exposure),
            "quote": result.value if result else None,
            "outlook_class": OUTLOOK_CLASS.get(card["outlook"], "either"),
        })

    # The all-companies table, with simple GET filters
    sectors = sorted({c["sector"] for c in cards})
    f_sector = request.args.get("sector", "")
    f_outlook = request.args.get("outlook", "")
    hide_held = request.args.get("hide_held") == "1"
    table = [c for c in cards
             if (not f_sector or c["sector"] == f_sector)
             and (not f_outlook or c["outlook"] == f_outlook)
             and not (hide_held and c["ticker"] in held)]

    return render_template(
        "research/index.html", snap=snap, opportunities=opportunities, fallback=fallback,
        total_candidates=len(candidates), table=table, sectors=sectors, held=held,
        filters={"sector": f_sector, "outlook": f_outlook, "hide_held": hide_held},
        exposure=exposure, threshold=CONCENTRATION_WARNING, weights=WEIGHTS,
        outlook_class=OUTLOOK_CLASS, disclaimer=DISCLAIMER,
    )


@research_bp.route("/<ticker>")
@login_required
def company(ticker: str):
    company = rd.get_company(ticker)
    if company is None:
        return render_template("research/company.html", missing=ticker.upper()[:12], disclaimer=DISCLAIMER), 404

    snap = load_snapshot()
    card = next((c for c in snap["cards"] if c["ticker"] == company.ticker), None) if snap else None
    held, exposure = _portfolio_context()

    try:
        quote = get_quote(company.ticker).value
    except Exception:  # noqa: BLE001
        quote = None

    # Statements (facts) and the metrics calculated from them
    try:
        record = rd.get_fundamentals(company.ticker).value
    except Exception:  # noqa: BLE001
        record = None
    metrics = rd.compute_metrics(record, (quote or {}).get("market_cap"), company.industry) if record else None

    # This week's news (facts), each with MarketMind's sentiment label (interpretation)
    news, news_error = [], None
    try:
        for a in (get_company_news(company.ticker, 7).value or [])[:8]:
            item = dict(a)
            item["sentiment"] = analyze_article(a)["label"]
            news.append(item)
    except Exception as exc:  # noqa: BLE001
        news_error = str(exc)

    rank = total = None
    if card and card["ticker"] not in held and card["overall"] is not None:
        candidates = [c for c in snap["cards"] if c["ticker"] not in held and c["overall"] is not None]
        rank, total = next(i for i, c in enumerate(candidates, 1) if c["ticker"] == card["ticker"]), len(candidates)
    why = explain_opportunity(card, rank, total, _coverage_topics().get(company.ticker),
                              include_strengths=False) if rank else []

    return render_template(
        "research/company.html", missing=None, company=company, card=card, snap=snap, quote=quote,
        record=record, metrics=metrics, news=news, news_error=news_error, why=why,
        is_held=company.ticker in held, check=concentration_check(company.sector, exposure),
        threshold=CONCENTRATION_WARNING, outlook_class=OUTLOOK_CLASS, disclaimer=DISCLAIMER,
    )

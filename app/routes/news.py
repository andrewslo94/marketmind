"""
app/routes/news.py — Section B: news about the stocks the user holds.

Facts (headline, publisher, time, ticker, link, provider summary) come from
Finnhub via news_service. The interpretation layer (sentiment, extractive
summary, implications) is computed per article and labeled as such. Filters
(4D) are plain GET parameters applied to the fetched list, so the URL is
shareable and the back button works.
"""
from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from app.models import Holding
from app.services.news_service import (
    SOURCE,
    active_filter_count,
    filter_articles,
    get_portfolio_news,
    parse_filters,
)
from app.services.implications import METHOD as IMPLICATIONS_METHOD, implications_for_article
from app.services.market_data import get_quotes
from app.services.sentiment import METHOD as SENTIMENT_METHOD, analyze_article
from app.services.summarizer import METHOD as SUMMARY_METHOD, summarize_article

news_bp = Blueprint("news", __name__, url_prefix="/news")

DAYS = 7


@news_bp.route("/")
@login_required
def index():
    holdings = Holding.query.filter_by(user_id=current_user.id).order_by(Holding.ticker).all()
    tickers = [h.ticker for h in holdings]

    filters = parse_filters(request.args, tickers)

    articles, meta, names = [], {"fetched_at": None, "oldest_fetch": None, "stale": False, "failed": {}}, {}
    if tickers:
        # Always fetch for every holding (each ticker is cached separately),
        # then filter in memory, so the filter options reflect the full set.
        articles, meta = get_portfolio_news(tickers, DAYS)
        # Company names from the cached quotes: used by the summarizer and
        # by the text search. Missing names are fine.
        names = {t: r.value["name"] for t, r in get_quotes(tickers).items() if r.value}
        for a in articles:
            # Interpretation layer: sentiment (4B), summary + implications (4C).
            # Cheap dictionary work, so it runs on every request, no caching.
            a["sentiment"] = analyze_article(a)
            a["summary_auto"] = summarize_article(a, company=names.get(a["tickers"][0]))
            a["implications"] = implications_for_article(a)

    total = len(articles)
    categories = sorted({(a.get("category") or "").lower() for a in articles if a.get("category")})
    shown = filter_articles(articles, filters, names)

    return render_template(
        "news/index.html",
        articles=shown,
        total=total,
        meta=meta,
        tickers=tickers,
        names=names,
        categories=categories,
        filters=filters,
        active_filters=active_filter_count(filters),
        days=DAYS,
        source=SOURCE,
        sentiment_method=SENTIMENT_METHOD,
        summary_method=SUMMARY_METHOD,
        implications_method=IMPLICATIONS_METHOD,
    )

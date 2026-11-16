"""
app/routes/news.py — Section B: news about the stocks the user holds.

Phase 4A shows the facts only: headline, publisher, time, ticker(s), link,
and the provider's own short summary. Sentiment, extractive summaries, and
implications are added in 4B/4C and will be labeled as interpretation.
"""
from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from app.models import Holding
from app.services.news_service import SOURCE, get_portfolio_news
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

    # Optional ?ticker=AAPL narrows the list (full filters come in 4D).
    selected = request.args.get("ticker", "").strip().upper()
    if selected and selected not in tickers:
        selected = ""

    articles, meta = [], {"fetched_at": None, "oldest_fetch": None, "stale": False, "failed": {}}
    if tickers:
        articles, meta = get_portfolio_news([selected] if selected else tickers, DAYS)
        # Interpretation layer (4B): rule-based sentiment per article. Cheap
        # (a dictionary lookup), so it runs on every request, no caching.
        # Company names (from the cached quotes) help the summarizer spot
        # sentences that name the company. Missing names are fine.
        names = {t: r.value["name"] for t, r in get_quotes(tickers).items() if r.value}
        for a in articles:
            a["sentiment"] = analyze_article(a)
            # 4C: extractive summary + rule-based implications (both interpretation).
            a["summary_auto"] = summarize_article(a, company=names.get(a["tickers"][0]))
            a["implications"] = implications_for_article(a)

    return render_template(
        "news/index.html",
        articles=articles,
        meta=meta,
        tickers=tickers,
        selected=selected,
        days=DAYS,
        source=SOURCE,
        sentiment_method=SENTIMENT_METHOD,
        summary_method=SUMMARY_METHOD,
        implications_method=IMPLICATIONS_METHOD,
    )

"""
app/services/news_service.py — company news from Finnhub, through the cache.

About the provider
------------------
Finnhub (finnhub.io) is a financial-data API. We use its REST "company-news"
endpoint: articles the provider has tagged with a ticker. Free tier: personal
non-commercial use, 60 calls per minute (the response headers confirm this:
X-Ratelimit-Limit: 60). The key lives in .env as FINNHUB_API_KEY and is sent
in a request header, never in the URL, so it doesn't end up in logs.

What we show is exactly what Finnhub returns (headline, publisher, time,
their short summary, link). Nothing is generated here. Note that Finnhub's
tagging is loose: a story mainly about another company can be tagged with a
ticker it merely mentions. The UI says so.

Public functions
----------------
get_company_news(ticker, days=7) -> CacheResult, .value = list of article dicts
get_portfolio_news(tickers, days=7) -> (articles, meta)  merged, de-duplicated,
                                       newest first; meta says what failed
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import requests
from flask import current_app

from app.services.cache import CacheResult, get_or_fetch

log = logging.getLogger(__name__)

SOURCE = "Finnhub"
BASE_URL = "https://finnhub.io/api/v1"
NEWS_TTL = 30 * 60  # 30 minutes: news doesn't need to be fresher for research
TIMEOUT = 15  # seconds before we give up on a request
MAX_PER_TICKER = 40  # keep the cache entries and the page a sensible size


class NewsError(Exception):
    """Provider unreachable, rate-limited, or not configured."""


def _api_key() -> str:
    key = current_app.config.get("FINNHUB_API_KEY")
    if not key:
        raise NewsError("FINNHUB_API_KEY is not set in .env")
    return key


def _normalize(raw: dict, ticker: str) -> Optional[dict]:
    """Turn one Finnhub article into the plain dict the app uses.
    Returns None if the essentials (headline + link) are missing."""
    headline = (raw.get("headline") or "").strip()
    url = (raw.get("url") or "").strip()
    if not headline or not url:
        return None
    ts = raw.get("datetime")
    published = (
        datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat() if ts else None
    )
    return {
        "id": raw.get("id"),
        "ticker": ticker,
        "headline": headline,
        "publisher": (raw.get("source") or "Unknown publisher").strip(),
        "published_at": published,  # ISO, UTC
        "summary": (raw.get("summary") or "").strip(),  # provider's own text
        "url": url,
        "image": (raw.get("image") or "").strip() or None,
        "category": raw.get("category"),
        "source": SOURCE,
    }


def _fetch_company_news(ticker: str, days: int) -> list[dict]:
    """One real call to Finnhub."""
    today = date.today()
    params = {
        "symbol": ticker,
        "from": (today - timedelta(days=days)).isoformat(),
        "to": today.isoformat(),
    }
    try:
        resp = requests.get(
            f"{BASE_URL}/company-news",
            params=params,
            headers={"X-Finnhub-Token": _api_key()},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise NewsError(f"Could not reach Finnhub: {exc}") from exc

    if resp.status_code == 429:
        raise NewsError("Finnhub rate limit reached (60 calls/min). Try again shortly.")
    if resp.status_code in (401, 403):
        raise NewsError("Finnhub rejected the API key. Check FINNHUB_API_KEY in .env.")
    if resp.status_code != 200:
        raise NewsError(f"Finnhub error {resp.status_code}")

    data = resp.json()
    if not isinstance(data, list):
        raise NewsError("Unexpected response from Finnhub")

    articles = [a for a in (_normalize(raw, ticker) for raw in data) if a]
    articles.sort(key=lambda a: a["published_at"] or "", reverse=True)
    return articles[:MAX_PER_TICKER]


def get_company_news(ticker: str, days: int = 7) -> CacheResult:
    """Cached news for one ticker. Raises NewsError only if nothing is cached."""
    ticker = ticker.strip().upper()
    return get_or_fetch(
        f"news:{ticker}:{days}d", NEWS_TTL, lambda: _fetch_company_news(ticker, days)
    )


def get_portfolio_news(tickers, days: int = 7) -> tuple[list[dict], dict]:
    """
    News for all of the user's tickers, merged into one list, newest first.
    The same article often comes back under several tickers; it is kept
    once, with every ticker it was tagged with in `tickers`.

    Returns (articles, meta) where meta has:
        fetched_at   newest provider fetch time (datetime, UTC) or None
        oldest_fetch oldest provider fetch time
        stale        True if any ticker's news is a stale cached copy
        failed       {ticker: error message} for tickers with no data at all
    """
    merged: dict = {}
    meta = {"fetched_at": None, "oldest_fetch": None, "stale": False, "failed": {}}

    for raw in tickers:
        ticker = raw.strip().upper()
        try:
            result = get_company_news(ticker, days)
        except NewsError as exc:
            meta["failed"][ticker] = str(exc)
            continue
        except Exception as exc:  # noqa: BLE001
            log.warning("News fetch failed for %s: %s", ticker, exc)
            meta["failed"][ticker] = "Data unavailable"
            continue

        meta["stale"] = meta["stale"] or result.stale
        if meta["fetched_at"] is None or result.fetched_at > meta["fetched_at"]:
            meta["fetched_at"] = result.fetched_at
        if meta["oldest_fetch"] is None or result.fetched_at < meta["oldest_fetch"]:
            meta["oldest_fetch"] = result.fetched_at

        for a in result.value or []:
            key = a["id"] or a["url"]
            if key in merged:
                if ticker not in merged[key]["tickers"]:
                    merged[key]["tickers"].append(ticker)
            else:
                item = dict(a)
                item["tickers"] = [ticker]
                merged[key] = item

    articles = sorted(merged.values(), key=lambda a: a["published_at"] or "", reverse=True)
    return articles, meta


# ---------------------------------------------------------------------------
# Filtering (Phase 4D). Works on the already-fetched, already-analyzed list,
# so filtering never costs a provider call.
# ---------------------------------------------------------------------------
from zoneinfo import ZoneInfo  # noqa: E402  (kept with the code that uses it)

ET = ZoneInfo("America/New_York")


def parse_filters(args, tickers) -> dict:
    """
    Turn request query parameters into a clean filters dict. Invalid values
    are dropped silently (an unknown ticker or a bad date just means "no
    filter"), so a hand-edited URL can't break the page.
    """
    def _date(value):
        try:
            return date.fromisoformat(value) if value else None
        except ValueError:
            return None

    ticker = (args.get("ticker") or "").strip().upper()
    sentiment = (args.get("sentiment") or "").strip().lower()
    return {
        "ticker": ticker if ticker in tickers else "",
        "q": (args.get("q") or "").strip()[:80],
        "date_from": _date(args.get("date_from")),
        "date_to": _date(args.get("date_to")),
        "category": (args.get("category") or "").strip().lower()[:40],
        "sentiment": sentiment if sentiment in ("positive", "neutral", "negative") else "",
    }


def _published_date_et(article) -> Optional[date]:
    iso = article.get("published_at")
    if not iso:
        return None
    return datetime.fromisoformat(iso).astimezone(ET).date()


def filter_articles(articles: list[dict], f: dict, names: dict) -> list[dict]:
    """
    Keep the articles that satisfy EVERY active filter.
    names: {ticker: company name} so the company/text search also matches
    "Apple" for AAPL, not only words in the headline.
    """
    q = f["q"].lower()
    out = []
    for a in articles:
        if f["ticker"] and f["ticker"] not in a["tickers"]:
            continue
        if f["category"] and (a.get("category") or "").lower() != f["category"]:
            continue
        if f["sentiment"] and a.get("sentiment", {}).get("label") != f["sentiment"]:
            continue
        if f["date_from"] or f["date_to"]:
            d = _published_date_et(a)
            if d is None:
                continue
            if f["date_from"] and d < f["date_from"]:
                continue
            if f["date_to"] and d > f["date_to"]:
                continue
        if q:
            haystack = " ".join(
                [a["headline"], a.get("summary") or "", a["publisher"]]
                + a["tickers"]
                + [names.get(t, "") for t in a["tickers"]]
            ).lower()
            if q not in haystack:
                continue
        out.append(a)
    return out


def active_filter_count(f: dict) -> int:
    return sum(1 for v in f.values() if v)

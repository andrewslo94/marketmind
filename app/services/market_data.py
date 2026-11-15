"""
app/services/market_data.py — prices and price history from Yahoo Finance
via the yfinance library, always through the cache.

About the provider
------------------
yfinance is an unofficial, open-source wrapper around Yahoo Finance's public
endpoints. No API key. Yahoo states the data is for personal use only, and
quotes are DELAYED (typically 15 minutes or more) — so every value from here
carries source + timestamps and the UI must label it "Delayed". Rate limits
are undocumented and Yahoo temporarily blocks IPs that call too often, which
is why nothing in this module touches yfinance without going through
cache.get_or_fetch().

Public functions
----------------
get_quote(ticker)            -> CacheResult whose .value is a quote dict (or None if unknown ticker)
get_quotes([tickers])        -> {ticker: CacheResult}
get_history(ticker, "1M")    -> CacheResult whose .value is a list of OHLCV rows
history_dataframe(result)    -> pandas DataFrame built from a get_history() result
ticker_exists(ticker)        -> True / False / None (None = couldn't verify right now)
"""
import logging
import math
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf

from app.services.cache import CacheResult, get_or_fetch

log = logging.getLogger(__name__)

SOURCE = "Yahoo Finance (via yfinance)"

# How long a cached copy is considered fresh, in seconds.
QUOTE_TTL = 15 * 60  # quotes: 15 min (they're delayed ~15 min anyway)

# Chart ranges the UI offers -> (yfinance period, bar interval, cache TTL).
# Intraday bars are refreshed more often; multi-year history barely changes.
HISTORY_RANGES = {
    "1D":  ("1d",  "5m",  10 * 60),
    "1W":  ("5d",  "30m", 30 * 60),
    "1M":  ("1mo", "1d",  60 * 60),
    "3M":  ("3mo", "1d",  60 * 60),
    "6M":  ("6mo", "1d",  60 * 60),
    "1Y":  ("1y",  "1d",  6 * 60 * 60),
    "5Y":  ("5y",  "1wk", 24 * 60 * 60),
    "MAX": ("max", "1mo", 24 * 60 * 60),
}

# Only these instrument types are accepted when adding a holding.
SUPPORTED_QUOTE_TYPES = {"EQUITY", "ETF"}


class MarketDataError(Exception):
    """Raised when the provider can't be reached or returns garbage."""


# ---------- small helpers ----------
def _num(value) -> Optional[float]:
    """Convert a provider number to a plain float, or None if missing/NaN.
    JSON can't store NaN, and templates should see None -> 'Data unavailable'."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _iso_from_unix(ts) -> Optional[str]:
    """Yahoo gives the quote time as Unix seconds; store as ISO text in UTC."""
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


def normalize_ticker(ticker: str) -> str:
    return (ticker or "").strip().upper()


# ---------- quotes ----------
def _fetch_quote(ticker: str) -> Optional[dict]:
    """
    One real call to Yahoo. Returns None when the symbol is unknown, a quote
    dict when it is known, and raises MarketDataError on provider trouble.
    """
    try:
        yt = yf.Ticker(ticker)
        info = yt.info or {}
    except Exception as exc:  # network error, rate limit, etc.
        raise MarketDataError(f"Provider error for {ticker}: {exc}") from exc

    price = _num(info.get("regularMarketPrice"))
    quote_type = info.get("quoteType")
    if price is None or quote_type not in SUPPORTED_QUOTE_TYPES:
        # Yahoo answers with an almost-empty dict for unknown symbols.
        return None

    prev_close = _num(info.get("regularMarketPreviousClose"))
    change = price - prev_close if prev_close is not None else None
    change_pct = (change / prev_close * 100) if (change is not None and prev_close) else None

    return {
        "ticker": ticker,
        "name": info.get("shortName") or info.get("longName") or ticker,
        "quote_type": quote_type,
        "exchange": info.get("fullExchangeName"),
        "currency": info.get("currency"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "price": price,
        "previous_close": prev_close,
        "open": _num(info.get("regularMarketOpen")),
        "day_high": _num(info.get("regularMarketDayHigh")),
        "day_low": _num(info.get("regularMarketDayLow")),
        "change": change,
        "change_pct": change_pct,
        "volume": _num(info.get("regularMarketVolume")),
        "avg_volume": _num(info.get("averageVolume")),
        "market_cap": _num(info.get("marketCap")),
        "week52_high": _num(info.get("fiftyTwoWeekHigh")),
        "week52_low": _num(info.get("fiftyTwoWeekLow")),
        # Yahoo's own timestamp for this quote, and the market's state
        # (REGULAR = open, PRE/POST = extended hours, CLOSED).
        "market_time": _iso_from_unix(info.get("regularMarketTime")),
        "market_state": info.get("marketState"),
        "source": SOURCE,
        "delayed": True,
    }


def get_quote(ticker: str) -> CacheResult:
    """Cached quote. result.value is a dict, or None for an unknown symbol."""
    ticker = normalize_ticker(ticker)
    return get_or_fetch(f"quote:{ticker}", QUOTE_TTL, lambda: _fetch_quote(ticker))


def get_quotes(tickers) -> dict[str, CacheResult]:
    """
    Quotes for several tickers. Each is cached separately, so repeated
    dashboard loads cost zero provider calls until the TTL expires.
    A ticker whose fetch fails outright is simply left out of the dict.
    """
    results = {}
    for raw in tickers:
        t = normalize_ticker(raw)
        try:
            results[t] = get_quote(t)
        except Exception as exc:  # noqa: BLE001
            log.warning("No quote for %s: %s", t, exc)
    return results


def ticker_exists(ticker: str) -> Optional[bool]:
    """
    True if Yahoo knows the symbol as a stock/ETF, False if it doesn't,
    None if the provider couldn't be reached (caller decides what to do).
    """
    try:
        return get_quote(ticker).value is not None
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not verify ticker %s: %s", ticker, exc)
        return None


# ---------- price history ----------
def _fetch_history(ticker: str, period: str, interval: str) -> list[dict]:
    """One real call. Returns rows as plain dicts so they can be cached as JSON."""
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
    except Exception as exc:
        raise MarketDataError(f"Provider error for {ticker} history: {exc}") from exc

    rows = []
    for ts, row in df.iterrows():
        close = _num(row.get("Close"))
        if close is None:
            continue  # skip half-empty bars
        rows.append(
            {
                "t": ts.isoformat(),  # timezone-aware (exchange local time)
                "o": _num(row.get("Open")),
                "h": _num(row.get("High")),
                "l": _num(row.get("Low")),
                "c": close,
                "v": _num(row.get("Volume")),
            }
        )
    return rows


def get_history(ticker: str, range_key: str = "1M") -> CacheResult:
    """
    Cached price history for one of the HISTORY_RANGES keys.
    result.value is a list of {"t","o","h","l","c","v"} rows (may be empty).
    """
    ticker = normalize_ticker(ticker)
    range_key = range_key.upper()
    if range_key not in HISTORY_RANGES:
        raise ValueError(f"Unknown range {range_key!r}; use one of {list(HISTORY_RANGES)}")
    period, interval, ttl = HISTORY_RANGES[range_key]
    return get_or_fetch(
        f"history:{ticker}:{range_key}",
        ttl,
        lambda: _fetch_history(ticker, period, interval),
    )


def history_dataframe(result: CacheResult) -> pd.DataFrame:
    """
    Turn a get_history() result back into a pandas DataFrame indexed by time,
    with columns Open/High/Low/Close/Volume — the shape Plotly and the
    portfolio calculations expect.
    """
    rows = result.value or []
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(rows).rename(
        columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"}
    )
    df.index = pd.to_datetime(df.pop("t"), utc=True)
    df.index.name = "Date"
    return df

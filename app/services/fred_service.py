"""
app/services/fred_service.py — U.S. economic indicators from FRED.

About the provider
------------------
FRED (Federal Reserve Economic Data) is a free database from the Federal
Reserve Bank of St. Louis. It republishes official statistics: consumer
prices and jobs from the Bureau of Labor Statistics (BLS), GDP from the
Bureau of Economic Analysis (BEA), and the policy rate from the Federal
Reserve Board. Free API key; up to 120 requests per minute (FRED's errors
documentation). FRED's terms require apps to show ATTRIBUTION (below); the
Markets page does.

Security note: FRED only accepts the key as a URL parameter (?api_key=...),
so a raw network error message would contain the key. Every error is
replaced with a plain message before it can reach a log, the cache, or
the page.

What MarketMind calculates (from FRED's numbers, never estimated)
-----------------------------------------------------------------
    yoy    12-month % change of an index: (this month / same month a year ago - 1) x 100
    diff   change from the previous month (payrolls, thousands of jobs)
    level  the value exactly as published (unemployment rate, GDP growth)
    range  Fed funds target range (lower and upper limit) and when it last changed
A missing value (FRED shows ".") stays missing. Nothing is filled in; a
calculation that needs it is skipped and the page says why.

Public function
---------------
get_indicator(key) -> IndicatorView for one card, e.g. get_indicator("cpi")
build_indicators() -> {"cards": [IndicatorView, ...], "meta": {...}, ...}
    (Named "cards", not "items": in a Jinja template, econ.items would find
    the dictionary's built-in .items() method before the key.)
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Optional

import requests
from flask import current_app

from app.services.cache import get_or_fetch

log = logging.getLogger(__name__)

SOURCE = "FRED, Federal Reserve Bank of St. Louis"
ATTRIBUTION = (
    "This product uses the FRED® API but is not endorsed or certified by the "
    "Federal Reserve Bank of St. Louis."
)
OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_TTL = 6 * 60 * 60  # 6 hours: these series change at most once a day
TIMEOUT = 20
YEARS_OF_HISTORY = 3


class FredError(Exception):
    """FRED unreachable, rate-limited, not configured, or returned something unexpected."""


@dataclass(frozen=True)
class Indicator:
    key: str
    name: str
    series: tuple  # FRED series IDs (two for the Fed funds range)
    calc: str  # "yoy" | "diff" | "level" | "range"
    fmt: str  # "pct" | "signed_pct" | "jobs" | "range"
    agency: str  # who publishes the original statistic
    measures: str  # one-line definition shown on the card
    frequency: str  # "M" monthly | "Q" quarterly | "D" daily
    trend_points: int = 24  # points in the sparkline


INDICATORS = [
    Indicator("cpi", "Inflation (CPI)", ("CPIAUCSL",), "yoy", "pct",
              "U.S. Bureau of Labor Statistics",
              "12-month change in consumer prices, seasonally adjusted", "M"),
    Indicator("core_cpi", "Core inflation", ("CPILFESL",), "yoy", "pct",
              "U.S. Bureau of Labor Statistics",
              "12-month change in consumer prices excluding food and energy", "M"),
    Indicator("unemployment", "Unemployment rate", ("UNRATE",), "level", "pct",
              "U.S. Bureau of Labor Statistics",
              "Share of the labor force without a job and looking for one", "M"),
    Indicator("payrolls", "Jobs added", ("PAYEMS",), "diff", "jobs",
              "U.S. Bureau of Labor Statistics",
              "Monthly change in nonfarm payroll employment", "M"),
    Indicator("fed_funds", "Fed funds target range", ("DFEDTARL", "DFEDTARU"), "range", "range",
              "Board of Governors of the Federal Reserve System",
              "The Federal Reserve's policy interest rate", "D"),
    Indicator("gdp", "Real GDP growth", ("A191RL1Q225SBEA",), "level", "signed_pct",
              "U.S. Bureau of Economic Analysis",
              "Quarterly change in inflation-adjusted output, at an annual rate", "Q",
              trend_points=12),
]

CALC_LABELS = {
    "yoy": "calculated from the price index",
    "diff": "calculated: change from the previous month",
}


# ---------- fetching ----------
def _api_key() -> str:
    key = current_app.config.get("FRED_API_KEY")
    if not key:
        raise FredError("FRED_API_KEY is not set in .env")
    return key


def _history_start() -> str:
    today = date.today()
    return date(today.year - YEARS_OF_HISTORY, today.month, 1).isoformat()


def _fetch_observations(series_id: str) -> list:
    """One real call to FRED. Returns [[iso_date, value_or_None], ...], oldest first."""
    params = {
        "series_id": series_id,
        "api_key": _api_key(),
        "file_type": "json",
        "observation_start": _history_start(),
    }
    try:
        resp = requests.get(OBSERVATIONS_URL, params=params, timeout=TIMEOUT)
    except requests.RequestException:
        # "from None" drops the original exception, whose text includes the
        # full URL and therefore the API key.
        raise FredError("Could not reach FRED (network error)") from None

    if resp.status_code == 429:
        raise FredError("FRED rate limit reached (120 requests per minute); try again shortly")
    if resp.status_code == 400:
        try:
            about_key = "api_key" in resp.json().get("error_message", "")
        except ValueError:
            about_key = False
        raise FredError("FRED rejected the API key; check FRED_API_KEY in .env" if about_key
                        else f"FRED rejected the request for series {series_id}")
    if resp.status_code != 200:
        raise FredError(f"FRED error {resp.status_code}")

    try:
        observations = resp.json()["observations"]
    except (ValueError, KeyError, TypeError):
        raise FredError("Unexpected response from FRED") from None

    points = []
    for obs in observations:
        raw = obs.get("value")
        try:
            value = None if raw in (None, ".") else float(raw)
        except ValueError:
            value = None
        points.append([obs.get("date"), value])
    return points


def get_series(series_id: str):
    """Cached observations for one FRED series (CacheResult)."""
    return get_or_fetch(f"fred:{series_id}", FRED_TTL, lambda: _fetch_observations(series_id))


# ---------- calculations (pure functions, unit-tested) ----------
def minus_months(d: date, n: int) -> date:
    """Same day-of-month n months earlier (FRED monthly dates are the 1st)."""
    total = d.year * 12 + (d.month - 1) - n
    return date(total // 12, total % 12 + 1, d.day)


def yoy_series(points):
    """[(date, level)] -> [(date, 12-month % change or None)]."""
    by_date = dict(points)
    out = []
    for d, v in points:
        base = by_date.get(minus_months(d, 12))
        out.append((d, (v / base - 1) * 100 if v is not None and base else None))
    return out


def diff_series(points):
    """[(date, level)] -> [(date, change from previous month or None)]."""
    by_date = dict(points)
    out = []
    for d, v in points:
        before = by_date.get(minus_months(d, 1))
        out.append((d, v - before if v is not None and before is not None else None))
    return out


def format_value(fmt: str, v) -> str:
    if v is None:
        return "Data unavailable"
    if fmt == "pct":
        return f"{v:.1f}%"
    if fmt == "signed_pct":
        return f"{v:+.1f}%"
    if fmt == "jobs":
        return f"{v:+,.0f}K"  # PAYEMS is in thousands of jobs
    if fmt == "range":
        return f"{v[0]:.2f}–{v[1]:.2f}%"  # compact form, e.g. 3.75–4.00%
    return str(v)


def period_label(d: date, frequency: str) -> str:
    if frequency == "Q":
        return f"Q{(d.month - 1) // 3 + 1} {d.year}"
    if frequency == "D":
        return f"{d:%b} {d.day}, {d.year}"
    return f"{d:%b %Y}"


# ---------- sparkline (inline SVG, drawn on the server) ----------
SPARK_W, SPARK_H, SPARK_PAD = 120, 32, 5


def sparkline(points, fmt: Callable, label: Callable, step: bool = False) -> Optional[dict]:
    """
    Small trend line for a stat card. points: [(date, value or None)], oldest
    first. Missing values break the line instead of being bridged. step=True
    draws a staircase (for a policy rate that holds until it changes).
    Returns SVG path data, the end-dot position, and hover bands (each band
    carries a native browser tooltip with that period's value).
    """
    n = len(points)
    values = [v for _, v in points if v is not None]
    if n < 2 or len(values) < 2:
        return None
    lo, hi = min(values), max(values)

    def x(i):
        return SPARK_PAD + i * (SPARK_W - 2 * SPARK_PAD) / (n - 1)

    def y(v):
        if hi == lo:
            return SPARK_H / 2
        return SPARK_H - SPARK_PAD - (v - lo) / (hi - lo) * (SPARK_H - 2 * SPARK_PAD)

    path, pen_down = [], False
    for i, (_, v) in enumerate(points):
        if v is None:
            pen_down = False
            continue
        if not pen_down:
            path.append(f"M{x(i):.1f},{y(v):.1f}")
        elif step:
            path.append(f"H{x(i):.1f}V{y(v):.1f}")
        else:
            path.append(f"L{x(i):.1f},{y(v):.1f}")
        pen_down = True

    last_i = max(i for i, (_, v) in enumerate(points) if v is not None)
    bands = []
    for i, (d, v) in enumerate(points):
        left = 0 if i == 0 else (x(i - 1) + x(i)) / 2
        right = SPARK_W if i == n - 1 else (x(i) + x(i + 1)) / 2
        bands.append({
            "x": round(left, 1), "w": round(right - left, 1),
            "title": f"{label(d)}: {fmt(v) if v is not None else 'no data'}",
        })
    first_valid = next((d, v) for d, v in points if v is not None)
    return {
        "path": " ".join(path),
        "end_x": round(x(last_i), 1),
        "end_y": round(y(points[last_i][1]), 1),
        "bands": bands,
        "summary": (f"Trend from {label(first_valid[0])} ({fmt(first_valid[1])}) "
                    f"to {label(points[last_i][0])} ({fmt(points[last_i][1])})"),
        "gaps": sum(1 for _, v in points if v is None),
    }


# ---------- one card per indicator ----------
@dataclass
class IndicatorView:
    key: str
    name: str
    measures: str
    agency: str
    series_ids: tuple
    available: bool = False
    value_text: str = "Data unavailable"
    period: Optional[str] = None
    calc_label: Optional[str] = None  # set when MarketMind did the arithmetic
    comparison: Optional[str] = None
    note: Optional[str] = None
    spark: Optional[dict] = None
    fetched_at: Optional[datetime] = None
    stale: bool = False
    error: Optional[str] = None
    links: list = field(default_factory=list)


def _parse(points) -> list:
    return [(date.fromisoformat(d), v) for d, v in points]


def _build(ind: Indicator) -> IndicatorView:
    view = IndicatorView(
        key=ind.key, name=ind.name, measures=ind.measures, agency=ind.agency,
        series_ids=ind.series, calc_label=CALC_LABELS.get(ind.calc),
        links=[f"https://fred.stlouisfed.org/series/{sid}" for sid in ind.series],
    )
    try:
        results = [get_series(sid) for sid in ind.series]
    except FredError as exc:
        view.error = str(exc)
        return view
    except Exception as exc:  # noqa: BLE001
        log.warning("FRED data failed for %s: %s", ind.key, type(exc).__name__)
        view.error = "Data unavailable"
        return view

    view.fetched_at = min(r.fetched_at for r in results)
    view.stale = any(r.stale for r in results)
    raw = [_parse(r.value or []) for r in results]

    if ind.calc == "range":
        return _build_range(ind, view, raw[0], raw[1])

    levels = raw[0]
    if ind.calc == "yoy":
        series = yoy_series(levels)
    elif ind.calc == "diff":
        series = diff_series(levels)
    else:
        series = levels

    valid = [(d, v) for d, v in series if v is not None]
    if not valid:
        view.error = "Data unavailable"
        return view
    latest = valid[-1]
    view.available = True
    view.value_text = format_value(ind.fmt, latest[1])
    view.period = period_label(latest[0], ind.frequency)
    if len(valid) > 1:
        prev = valid[-2]
        view.comparison = f"vs {format_value(ind.fmt, prev[1])} in {period_label(prev[0], ind.frequency)}"

    # A newer published level whose change can't be calculated: say why.
    newest = max((d for d, v in levels if v is not None), default=None)
    if newest and newest > latest[0] and ind.calc in ("yoy", "diff"):
        needed = minus_months(newest, 12 if ind.calc == "yoy" else 1)
        kind = "12-month" if ind.calc == "yoy" else "monthly"
        view.note = (f"{period_label(newest, ind.frequency)} data is out, but its {kind} change "
                     f"can't be calculated: FRED has no value for {period_label(needed, ind.frequency)}.")

    view.spark = sparkline(
        series[-ind.trend_points:],
        fmt=lambda v: format_value(ind.fmt, v),
        label=lambda d: period_label(d, ind.frequency),
    )
    return view


def _build_range(ind: Indicator, view: IndicatorView, lower_pts, upper_pts) -> IndicatorView:
    lower = {d: v for d, v in lower_pts if v is not None}
    upper = {d: v for d, v in upper_pts if v is not None}
    dates = sorted(set(lower) & set(upper))
    if not dates:
        view.error = "Data unavailable"
        return view
    pairs = [(d, (lower[d], upper[d])) for d in dates]
    current = pairs[-1][1]

    # Walk back to the first day of the current range.
    i = len(pairs) - 1
    while i > 0 and pairs[i - 1][1] == current:
        i -= 1

    view.available = True
    view.value_text = format_value("range", current)
    view.period = period_label(pairs[-1][0], "D")
    if i > 0:
        view.comparison = (f"In effect since {period_label(pairs[i][0], 'D')} · "
                           f"previously {format_value('range', pairs[i - 1][1])}")
    else:
        view.comparison = f"Unchanged since at least {period_label(pairs[0][0], 'D')}"

    # Sparkline: the upper limit at the end of each month, as a staircase.
    by_month = {}
    for d in dates:
        by_month[(d.year, d.month)] = (date(d.year, d.month, 1), upper[d])
    monthly = [by_month[k] for k in sorted(by_month)][-ind.trend_points:]
    view.spark = sparkline(
        monthly, step=True,
        fmt=lambda v: f"{v:.2f}% upper limit",
        label=lambda d: period_label(d, "M"),
    )
    return view


def get_indicator(key: str) -> Optional[IndicatorView]:
    """One indicator card by key (e.g. "cpi"), for other pages. None if no such key."""
    ind = next((i for i in INDICATORS if i.key == key), None)
    return _build(ind) if ind else None


def build_indicators() -> dict:
    cards = [_build(ind) for ind in INDICATORS]
    ok = [v for v in cards if v.available]
    return {
        "cards": cards,
        "source": SOURCE,
        "attribution": ATTRIBUTION,
        "meta": {
            "count": len(cards),
            "available": len(ok),
            "fetched_at": max((v.fetched_at for v in ok if v.fetched_at), default=None),
            "oldest_fetch": min((v.fetched_at for v in ok if v.fetched_at), default=None),
            "stale": any(v.stale for v in ok),
            "errors": sorted({v.error for v in cards if v.error}),
        },
    }

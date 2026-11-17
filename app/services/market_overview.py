"""
app/services/market_overview.py — Section C, Market Overview: major stock
indexes, Treasury yields, and commodities.

Every number comes from Yahoo Finance through the market_data service, so it
is cached for 15 minutes and carries the provider's own quote time. This
module adds no data of its own: it chooses the instruments, formats each one
in the right unit, and computes two things from the quotes (the yield-curve
spread and percent performance over a period).

Units differ by instrument, and the formatting rules make that explicit:
    index, volatility  points            change in points and percent
    yield              percent           change in basis points (1 bp = 0.01
                       (CBOE yield index: percentage point). A percent change of
                       5.107 = 5.107%)   a yield is easy to misread, so it isn't shown.
    commodity          U.S. dollars per  change in dollars and percent
                       unit, front-month
                       futures contract

Public functions
----------------
build_overview()                -> {"groups": [...], "meta": {...}, "spread": {...}}
index_performance(range_key)    -> chart data: % change since the period start
format_value / format_change / direction_of  (unit rules, unit-tested)
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app.services.market_data import HISTORY_RANGES, get_history, get_market_quote

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Instrument:
    """One thing the page shows a quote for. frozen=True makes it read-only."""

    symbol: str  # Yahoo symbol, e.g. "^GSPC", "^TNX", "CL=F"
    name: str  # our display name
    kind: str  # "index" | "volatility" | "yield" | "commodity"
    unit: Optional[str] = None  # commodities only, e.g. "per barrel"


GROUPS = [
    {
        "key": "us",
        "title": "U.S. stock indexes",
        "note": "Index points",
        "instruments": [
            Instrument("^GSPC", "S&P 500", "index"),
            Instrument("^DJI", "Dow Jones Industrial Average", "index"),
            Instrument("^IXIC", "Nasdaq Composite", "index"),
            Instrument("^RUT", "Russell 2000", "index"),
            Instrument("^VIX", "CBOE Volatility Index (VIX)", "volatility"),
        ],
    },
    {
        "key": "global",
        "title": "Global stock indexes",
        "note": "Index points · times shown in ET",
        "instruments": [
            Instrument("^FTSE", "FTSE 100 (UK)", "index"),
            Instrument("^GDAXI", "DAX (Germany)", "index"),
            Instrument("^N225", "Nikkei 225 (Japan)", "index"),
            Instrument("^HSI", "Hang Seng (Hong Kong)", "index"),
        ],
    },
    {
        "key": "yields",
        "title": "U.S. Treasury yields",
        "note": "CBOE yield indexes · percent",
        "instruments": [
            Instrument("^IRX", "13-week bill", "yield"),
            Instrument("^FVX", "5-year note", "yield"),
            Instrument("^TNX", "10-year note", "yield"),
            Instrument("^TYX", "30-year bond", "yield"),
        ],
    },
    {
        "key": "commodities",
        "title": "Commodities",
        "note": "Front-month futures · U.S. dollars",
        "instruments": [
            Instrument("CL=F", "WTI crude oil", "commodity", "per barrel"),
            Instrument("BZ=F", "Brent crude oil", "commodity", "per barrel"),
            Instrument("GC=F", "Gold", "commodity", "per troy ounce"),
            Instrument("SI=F", "Silver", "commodity", "per troy ounce"),
        ],
    },
]

# The performance chart compares three indexes with distinct stories: large
# companies, tech-heavy, and small companies. (The Dow largely tracks the
# S&P 500, and a fourth line needs a color pair that fails the palette check.)
PERFORMANCE_INDEXES = [
    Instrument("^GSPC", "S&P 500", "index"),
    Instrument("^IXIC", "Nasdaq Composite", "index"),
    Instrument("^RUT", "Russell 2000", "index"),
]
PERFORMANCE_RANGES = ["1M", "3M", "6M", "1Y", "5Y"]

_MONTH_CONTRACT = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{2}\b")


# ---------- unit rules (pure functions, easy to test) ----------
def direction_of(change: Optional[float], kind: str = "index") -> Optional[str]:
    """'up' / 'down' / 'flat', judged at display precision so a change that
    prints as 0.00 isn't shown with an arrow."""
    if change is None:
        return None
    rounded = round(change, 3 if kind == "yield" else 2)
    return "up" if rounded > 0 else "down" if rounded < 0 else "flat"


def format_value(kind: str, value: Optional[float]) -> str:
    if value is None:
        return "Data unavailable"
    if kind == "yield":
        return f"{value:.3f}%"
    if kind == "commodity":
        return f"${value:,.2f}"
    return f"{value:,.2f}"  # index or volatility: points


def format_change(kind: str, change: Optional[float], change_pct: Optional[float]) -> tuple[str, str]:
    """Return (change_text, change_pct_text) in the instrument's unit."""
    if change is None:
        return "—", "—"
    if kind == "yield":
        return f"{change * 100:+.1f} bps", "—"
    pct = f"{change_pct:+.2f}%" if change_pct is not None else "—"
    if kind == "commodity":
        sign = "-" if round(change, 2) < 0 else "+"
        return f"{sign}${abs(change):,.2f}", pct
    return f"{change:+,.2f}", pct


def _session_label(kind: str, state: Optional[str]) -> Optional[str]:
    """Yahoo's marketState -> a plain label. Index values only update in the
    regular session, so every other state reads 'Closed' for them."""
    if not state:
        return None
    if state == "REGULAR":
        return "Open"
    if kind == "commodity" and state in ("PRE", "POST"):
        return "Extended hours"
    return "Closed"


def _parse_iso(text: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


# ---------- quotes ----------
@dataclass
class InstrumentRow:
    """One tile or table row on the page."""

    symbol: str
    name: str
    kind: str
    unit: Optional[str] = None
    available: bool = False
    price: Optional[float] = None
    previous_close: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    direction: Optional[str] = None
    value_text: str = "Data unavailable"
    change_text: str = "—"
    change_pct_text: str = "—"
    contract: Optional[str] = None  # futures: which contract month, e.g. "Crude Oil Dec 26"
    market_time: Optional[datetime] = None  # Yahoo's quote time
    fetched_at: Optional[datetime] = None  # when we fetched it
    session: Optional[str] = None  # "Open" / "Closed" / "Extended hours"
    stale: bool = False


def _build_row(inst: Instrument) -> InstrumentRow:
    row = InstrumentRow(symbol=inst.symbol, name=inst.name, kind=inst.kind, unit=inst.unit)
    try:
        result = get_market_quote(inst.symbol)
    except Exception as exc:  # noqa: BLE001 — provider down and nothing cached
        log.warning("No quote for %s: %s", inst.symbol, exc)
        return row

    quote = result.value
    if not quote or quote.get("price") is None:
        return row  # unknown symbol: stays "Data unavailable"

    row.available = True
    row.price = quote["price"]
    row.previous_close = quote.get("previous_close")
    row.change = quote.get("change")
    row.change_pct = quote.get("change_pct")
    row.direction = direction_of(row.change, inst.kind)
    row.value_text = format_value(inst.kind, row.price)
    row.change_text, row.change_pct_text = format_change(inst.kind, row.change, row.change_pct)
    if inst.kind == "commodity":
        name = quote.get("name") or ""
        # Show the contract month only when the provider names one.
        row.contract = name if _MONTH_CONTRACT.search(name) else None
    row.market_time = _parse_iso(quote.get("market_time"))
    row.fetched_at = result.fetched_at
    row.session = _session_label(inst.kind, quote.get("market_state"))
    row.stale = result.stale
    return row


def yield_spread(rows) -> dict:
    """
    10-year minus 13-week Treasury yield, in percentage points: a calculation
    from two quotes on the page. The note that goes with it is labeled as
    interpretation on the page.
    """
    by_symbol = {r.symbol: r for r in rows}
    long_, short = by_symbol.get("^TNX"), by_symbol.get("^IRX")
    if not (long_ and short and long_.available and short.available):
        return {"value": None, "text": "Data unavailable", "note": None, "inverted": None}

    value = round(long_.price - short.price, 3)
    if abs(value) < 0.005:
        shape = "Flat curve: the 10-year and 13-week yields are about equal."
    elif value < 0:
        shape = "Inverted curve: the 13-week yield is above the 10-year yield."
    else:
        shape = "Upward-sloping curve: the 10-year yield is above the 13-week yield."
    note = (
        shape + " Historically, an inverted curve (spread below zero) has come before most "
        "U.S. recessions since the late 1960s, but with long, variable lags and some false "
        "signals. Context, not a forecast."
    )
    return {"value": value, "text": f"{value:+.2f} percentage points", "note": note, "inverted": value < 0}


def build_overview() -> dict:
    """Quotes for every instrument, grouped for the page, plus page-level meta."""
    groups, all_rows = [], []
    for group in GROUPS:
        rows = [_build_row(inst) for inst in group["instruments"]]
        groups.append({"key": group["key"], "title": group["title"], "note": group["note"], "rows": rows})
        all_rows.extend(rows)

    ok = [r for r in all_rows if r.available]
    meta = {
        "count": len(all_rows),
        "available": len(ok),
        "unavailable": [r.name for r in all_rows if not r.available],
        "stale": any(r.stale for r in ok),
        "latest_fetch": max((r.fetched_at for r in ok if r.fetched_at), default=None),
        "oldest_fetch": min((r.fetched_at for r in ok if r.fetched_at), default=None),
    }
    return {"groups": groups, "meta": meta, "spread": yield_spread(all_rows)}


# ---------- performance chart ----------
def index_performance(range_key: str) -> dict:
    """
    Percent change of each PERFORMANCE_INDEXES series since the first close
    of the period, so indexes at very different levels share one axis.
    Uses the cached price history (same cache as the stock pages).
    """
    range_key = range_key.upper()
    if range_key not in PERFORMANCE_RANGES:
        raise ValueError(f"Unknown range {range_key!r}; use one of {PERFORMANCE_RANGES}")
    _period, interval, _ttl = HISTORY_RANGES[range_key]

    series, failed, fetched, stale = [], {}, [], False
    for inst in PERFORMANCE_INDEXES:
        try:
            result = get_history(inst.symbol, range_key)
        except Exception as exc:  # noqa: BLE001
            log.warning("No history for %s: %s", inst.symbol, exc)
            failed[inst.name] = "Data unavailable"
            continue
        rows = [r for r in (result.value or []) if r.get("c")]
        if len(rows) < 2:
            failed[inst.name] = "Data unavailable"
            continue

        first = rows[0]["c"]
        x = [datetime.fromisoformat(r["t"]).astimezone(ET).strftime("%Y-%m-%d") for r in rows]
        series.append(
            {
                "symbol": inst.symbol,
                "name": inst.name,
                "x": x,
                "y": [round((r["c"] / first - 1) * 100, 3) for r in rows],
                "close": [round(r["c"], 2) for r in rows],
                "start_date": x[0],
                "end_date": x[-1],
                "start": round(first, 2),
                "end": round(rows[-1]["c"], 2),
                "change_pct": round((rows[-1]["c"] / first - 1) * 100, 2),
            }
        )
        fetched.append(result.fetched_at)
        stale = stale or result.stale

    return {
        "range": range_key,
        "interval": interval,
        "series": series,
        "failed": failed,
        "fetched_at": max(fetched).isoformat() if fetched else None,
        "stale": stale,
    }

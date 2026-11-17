"""
app/services/portfolio_calc.py — turn holdings + cached quotes into the
numbers the dashboard shows.

Pure calculation: no database writes, no rendering. Every number comes from
the user's own entries (shares, average price) and the quote the
market_data service returned, and each row carries that quote's timestamps
so the page can label where and when the price came from.

Definitions (per holding, all in the quote's currency):
    cost_basis   = shares x avg_price            (what the user paid)
    value        = shares x price                (what it's worth now, delayed)
    gain         = value - cost_basis            (unrealized profit/loss)
    gain_pct     = gain / cost_basis x 100
    day_change   = shares x (price - previous_close)
    day_pct      = (price - previous_close) / previous_close x 100
    allocation   = value / total_value x 100     (share of the portfolio)

Totals only include holdings that (a) have a quote and (b) are priced in
USD, so we never add dollars to, say, Canadian dollars. Rows left out are
listed in `unpriced` / `non_usd` so the page can say so.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.services.market_data import get_quotes
from app.services.topic_map import YAHOO_TO_SECTOR

BASE_CURRENCY = "USD"


@dataclass
class HoldingRow:
    """One table row on the dashboard."""

    id: int
    ticker: str
    shares: float
    avg_price: float
    cost_basis: float
    purchase_date: Optional[object] = None
    notes: Optional[str] = None

    # Filled from the quote when available
    priced: bool = False
    name: Optional[str] = None
    currency: Optional[str] = None
    sector: Optional[str] = None  # as Yahoo reports it ("Consumer Cyclical", ...); None for funds
    quote_type: Optional[str] = None  # "EQUITY" or "ETF"
    price: Optional[float] = None
    previous_close: Optional[float] = None
    value: Optional[float] = None
    gain: Optional[float] = None
    gain_pct: Optional[float] = None
    day_change: Optional[float] = None
    day_pct: Optional[float] = None
    allocation_pct: Optional[float] = None
    market_time: Optional[datetime] = None  # Yahoo's quote timestamp
    fetched_at: Optional[datetime] = None  # when we fetched it
    market_state: Optional[str] = None
    stale: bool = False
    in_totals: bool = False
    note: Optional[str] = None  # why it's excluded from totals, if it is


@dataclass
class PortfolioSummary:
    rows: list = field(default_factory=list)
    holding_count: int = 0
    priced_count: int = 0
    total_cost: float = 0.0
    total_value: float = 0.0
    total_gain: float = 0.0
    total_gain_pct: Optional[float] = None
    day_change: float = 0.0
    day_pct: Optional[float] = None
    unpriced: list = field(default_factory=list)  # tickers with no quote
    non_usd: list = field(default_factory=list)  # tickers excluded (currency)
    any_stale: bool = False
    latest_fetch: Optional[datetime] = None
    oldest_fetch: Optional[datetime] = None
    latest_market_time: Optional[datetime] = None
    market_state: Optional[str] = None  # REGULAR / CLOSED / PRE / POST

    @property
    def complete(self) -> bool:
        """True when every holding is priced and counted in the totals."""
        return self.holding_count > 0 and self.priced_count == self.holding_count and not self.non_usd


def _parse_iso(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _pct(part: Optional[float], whole: Optional[float]) -> Optional[float]:
    if part is None or not whole:
        return None
    return part / whole * 100


def build_portfolio(holdings) -> PortfolioSummary:
    """
    holdings: the user's Holding rows (any iterable).
    Returns a PortfolioSummary with one HoldingRow per holding, sorted by
    value (largest first), unpriced rows last.
    """
    summary = PortfolioSummary(holding_count=len(holdings))
    if not holdings:
        return summary

    quotes = get_quotes([h.ticker for h in holdings])

    for h in holdings:
        row = HoldingRow(
            id=h.id,
            ticker=h.ticker,
            shares=h.shares,
            avg_price=h.avg_price,
            cost_basis=h.cost_basis,
            purchase_date=h.purchase_date,
            notes=h.notes,
        )
        summary.rows.append(row)

        result = quotes.get(h.ticker)
        quote = result.value if result else None
        if quote is None or quote.get("price") is None:
            row.note = "Data unavailable"
            summary.unpriced.append(h.ticker)
            continue

        row.priced = True
        row.name = quote.get("name")
        row.currency = quote.get("currency")
        row.sector = quote.get("sector")
        row.quote_type = quote.get("quote_type")
        row.price = quote["price"]
        row.previous_close = quote.get("previous_close")
        row.value = h.shares * row.price
        row.gain = row.value - row.cost_basis
        row.gain_pct = _pct(row.gain, row.cost_basis)
        if row.previous_close:
            row.day_change = h.shares * (row.price - row.previous_close)
            row.day_pct = _pct(row.price - row.previous_close, row.previous_close)
        row.market_time = _parse_iso(quote.get("market_time"))
        row.fetched_at = result.fetched_at
        row.market_state = quote.get("market_state")
        row.stale = result.stale
        summary.any_stale = summary.any_stale or result.stale
        summary.priced_count += 1

        if row.currency != BASE_CURRENCY:
            row.note = f"Priced in {row.currency}; not included in USD totals"
            summary.non_usd.append(h.ticker)
            continue

        row.in_totals = True
        summary.total_cost += row.cost_basis
        summary.total_value += row.value
        if row.day_change is not None:
            summary.day_change += row.day_change

        # Track the newest/oldest timestamps so the page can show
        # "as of ..." honestly for the whole portfolio.
        if row.fetched_at:
            if summary.latest_fetch is None or row.fetched_at > summary.latest_fetch:
                summary.latest_fetch = row.fetched_at
            if summary.oldest_fetch is None or row.fetched_at < summary.oldest_fetch:
                summary.oldest_fetch = row.fetched_at
        if row.market_time and (
            summary.latest_market_time is None or row.market_time > summary.latest_market_time
        ):
            summary.latest_market_time = row.market_time
            summary.market_state = row.market_state

    # Totals that depend on the sums above
    summary.total_gain = summary.total_value - summary.total_cost
    summary.total_gain_pct = _pct(summary.total_gain, summary.total_cost)
    prev_value = summary.total_value - summary.day_change
    summary.day_pct = _pct(summary.day_change, prev_value)
    for row in summary.rows:
        if row.in_totals:
            row.allocation_pct = _pct(row.value, summary.total_value)

    # Largest position first; rows without a value go to the bottom.
    summary.rows.sort(key=lambda r: (r.value is None, -(r.value or 0)))
    return summary


def allocation_chart_data(summary: PortfolioSummary) -> dict:
    """
    Data for the ranked allocation bars, largest first. Plain lists so the
    template can drop it into the page as JSON for plotly.js.
    """
    rows = [r for r in summary.rows if r.in_totals and r.allocation_pct is not None]
    return {
        "tickers": [r.ticker for r in rows],
        "names": [r.name or r.ticker for r in rows],
        "pcts": [round(r.allocation_pct, 2) for r in rows],
        "values": [round(r.value, 2) for r in rows],
    }


def sector_exposure(summary: PortfolioSummary) -> dict:
    """
    How much of the portfolio's current USD value sits in each of the 11
    sectors, using the sector Yahoo reports for each holding. A fund (ETF)
    holds many sectors and isn't split up, so it's listed separately, as are
    holdings without a price or outside the USD totals.

    Returns {"has_holdings": bool,
             "sectors": {sector: {"pct", "value", "tickers"}}  (largest first),
             "unclassified": [{"ticker", "reason", "pct"}]}
    """
    sectors, unclassified = {}, []
    for r in summary.rows:
        if not r.priced:
            unclassified.append({"ticker": r.ticker, "reason": "no price available", "pct": None})
            continue
        if not r.in_totals:
            unclassified.append({"ticker": r.ticker, "reason": f"priced in {r.currency}, outside the USD totals", "pct": None})
            continue
        sector = YAHOO_TO_SECTOR.get(r.sector or "")
        if sector is None:
            reason = "a fund (ETF) that holds many sectors" if r.quote_type == "ETF" else "no sector reported"
            unclassified.append({"ticker": r.ticker, "reason": reason, "pct": r.allocation_pct})
            continue
        entry = sectors.setdefault(sector, {"pct": 0.0, "value": 0.0, "tickers": []})
        entry["pct"] += r.allocation_pct or 0.0
        entry["value"] += r.value or 0.0
        entry["tickers"].append(r.ticker)
    ordered = dict(sorted(sectors.items(), key=lambda kv: kv[1]["pct"], reverse=True))
    return {"has_holdings": summary.holding_count > 0, "sectors": ordered, "unclassified": unclassified}

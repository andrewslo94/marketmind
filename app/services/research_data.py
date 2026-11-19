"""
app/services/research_data.py — data layer for the Research Engine (Section D).

1. The research universe: data/universe.csv, 64 curated companies across
   the 11 sectors (ticker, name, sector, industry, reporting currency). Name,
   sector, and industry were taken from Yahoo Finance, not typed by hand.
2. Company fundamentals, five annual statements per company, from ONE of:
     - Financial Modeling Prep (FMP), when the free plan covers the company
       (it serves a fixed list of popular stocks; others return HTTP 402);
     - Yahoo Finance statements (via yfinance) for everyone else.
   Both are converted to the same plain record, so the rest of the app never
   needs to know which provider was used. The record says which, and the
   page will show it.
3. Metrics calculated by MarketMind's own formulas (FORMULAS below), only
   from line items both providers report identically. A cross-check found
   revenue, net income, equity, current assets/liabilities and cash flows
   identical in both; operating income differed (Coca-Cola: 8%), so it is
   stored but never scored; total debt can differ a few percent (lease
   treatment), which the page discloses.

About FMP
---------
Free plan: 250 requests per day, 500 MB per 30 days, up to 5 years of annual
statements, current "stable" API only. The key travels in an `apikey`
request header, never in a URL, so it can't leak into logs. Each company
costs 3 calls (income, balance sheet, cash flow), cached for 7 days.

Public functions
----------------
load_universe()                 -> list of Company
get_company(ticker)             -> Company or None
get_fundamentals(ticker)        -> CacheResult, .value = normalized record
compute_metrics(record, market_cap, industry) -> {name: Metric}
fmp_calls_made()                -> FMP calls this process has made (for the daily budget)
"""
import csv
import logging
import math
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import requests
import yfinance as yf
from flask import current_app

from app.services.cache import CacheResult, get_or_fetch
from app.services.topic_map import SECTORS

log = logging.getLogger(__name__)

UNIVERSE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "universe.csv")
FMP_BASE = "https://financialmodelingprep.com/stable"
FUNDAMENTALS_TTL = 7 * 24 * 60 * 60  # statements change once a quarter; refresh weekly
TIMEOUT = 20
YEARS = 5
# "Profitable years" looks at the latest 4 years: Yahoo sometimes lacks a 5th
# year of net income where FMP has one, and the count must not depend on the provider.
PROFIT_WINDOW = 4

# Statements of banks and brokers aren't comparable with other companies'
# (no current assets/liabilities, "revenue" and "debt" defined differently,
# and differently again by each provider), so they use a shorter metric list.
BANK_INDUSTRIES = {"Banks - Diversified", "Banks - Regional", "Capital Markets"}


class FundamentalsError(Exception):
    """Neither provider could supply statements."""


class FmpNotCovered(Exception):
    """HTTP 402: this symbol isn't on FMP's free plan."""


class FmpUnavailable(Exception):
    """FMP not configured, rate-limited, unreachable, or returned junk."""


# ---------------------------------------------------------------------------
# 1. The universe
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Company:
    ticker: str
    name: str
    sector: str
    industry: str
    financial_currency: str

    @property
    def is_bank(self) -> bool:
        return self.industry in BANK_INDUSTRIES


@lru_cache(maxsize=1)  # read the CSV once per process
def load_universe() -> tuple:
    companies, seen = [], set()
    with open(UNIVERSE_PATH, newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            ticker = (row.get("ticker") or "").strip().upper()
            if not re.fullmatch(r"[A-Z]{1,5}([.-][A-Z]{1,2})?", ticker):
                raise ValueError(f"universe.csv line {i}: bad ticker {ticker!r}")
            if ticker in seen:
                raise ValueError(f"universe.csv line {i}: duplicate ticker {ticker}")
            if row.get("sector") not in SECTORS:
                raise ValueError(f"universe.csv line {i}: unknown sector {row.get('sector')!r}")
            seen.add(ticker)
            companies.append(Company(ticker, row["name"].strip(), row["sector"], row["industry"].strip(),
                                     (row.get("financial_currency") or "").strip() or "unknown"))
    return tuple(companies)


def get_company(ticker: str) -> Optional[Company]:
    ticker = (ticker or "").strip().upper()
    return next((c for c in load_universe() if c.ticker == ticker), None)


# ---------------------------------------------------------------------------
# 2. Fundamentals: FMP first, Yahoo otherwise, one normalized record
# ---------------------------------------------------------------------------
# One normalized year: every value is a plain float or None.
FIELDS = ["revenue", "operating_income", "net_income", "total_debt", "equity",
          "current_assets", "current_liabilities", "operating_cash_flow", "capital_expenditure"]

_fmp_calls = 0


def fmp_calls_made() -> int:
    return _fmp_calls


def _num(value) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _fmp_get(path: str, ticker: str) -> list:
    global _fmp_calls
    key = current_app.config.get("FMP_API_KEY")
    if not key:
        raise FmpUnavailable("FMP_API_KEY is not set in .env")
    _fmp_calls += 1
    try:
        resp = requests.get(f"{FMP_BASE}/{path}", params={"symbol": ticker, "period": "annual", "limit": YEARS},
                            headers={"apikey": key}, timeout=TIMEOUT)
    except requests.RequestException:
        raise FmpUnavailable("could not reach FMP") from None
    if resp.status_code == 402:
        raise FmpNotCovered("not on FMP's free plan")
    if resp.status_code == 429:
        raise FmpUnavailable("FMP's daily request limit was reached")
    if resp.status_code in (401, 403):
        raise FmpUnavailable("FMP rejected the API key")
    if resp.status_code != 200:
        raise FmpUnavailable(f"FMP error {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        raise FmpUnavailable("unexpected response from FMP") from None
    if not isinstance(data, list):
        raise FmpUnavailable("unexpected response from FMP")
    return data


def _from_fmp(ticker: str) -> dict:
    income = _fmp_get("income-statement", ticker)  # a 402 here stops after one call
    balance = {r.get("date"): r for r in _fmp_get("balance-sheet-statement", ticker)}
    cash = {r.get("date"): r for r in _fmp_get("cash-flow-statement", ticker)}
    years = []
    for inc in income:
        d = inc.get("date")
        bal, cf = balance.get(d, {}), cash.get(d, {})
        years.append({
            "period_end": d,
            "revenue": _num(inc.get("revenue")),
            "operating_income": _num(inc.get("operatingIncome")),
            "net_income": _num(inc.get("netIncome")),
            "total_debt": _num(bal.get("totalDebt")),
            "equity": _num(bal.get("totalStockholdersEquity")),
            "current_assets": _num(bal.get("totalCurrentAssets")),
            "current_liabilities": _num(bal.get("totalCurrentLiabilities")),
            "operating_cash_flow": _num(cf.get("operatingCashFlow")),
            "capital_expenditure": _num(cf.get("capitalExpenditure")),
        })
    if not years:
        raise FmpUnavailable("FMP returned no statements")
    currency = income[0].get("reportedCurrency") or "unknown"
    return {"ticker": ticker, "source": "Financial Modeling Prep", "currency": currency,
            "years": sorted(years, key=lambda y: y["period_end"] or "", reverse=True)[:YEARS]}


YAHOO_ROWS = {
    "revenue": ("income", "Total Revenue"),
    "operating_income": ("income", "Operating Income"),
    "net_income": ("income", "Net Income"),
    "total_debt": ("balance", "Total Debt"),
    "equity": ("balance", "Stockholders Equity"),
    "current_assets": ("balance", "Current Assets"),
    "current_liabilities": ("balance", "Current Liabilities"),
    "operating_cash_flow": ("cash", "Operating Cash Flow"),
    "capital_expenditure": ("cash", "Capital Expenditure"),
}


def _from_yahoo(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        frames = {"income": t.income_stmt, "balance": t.balance_sheet, "cash": t.cashflow}
    except Exception as exc:  # noqa: BLE001 — network, rate limit, parsing
        raise FundamentalsError(f"Yahoo Finance statements unavailable for {ticker}") from exc
    income = frames["income"]
    if income is None or income.empty:
        raise FundamentalsError(f"Yahoo Finance has no statements for {ticker}")

    years = []
    for col in income.columns:  # newest first
        year = {"period_end": col.date().isoformat()}
        for name, (statement, row) in YAHOO_ROWS.items():
            df = frames[statement]
            value = None
            if df is not None and row in df.index and col in df.columns:
                value = _num(df.loc[row, col])
            year[name] = value
        if year["revenue"] is not None or year["net_income"] is not None:
            years.append(year)
    company = get_company(ticker)
    return {"ticker": ticker, "source": "Yahoo Finance", "currency": company.financial_currency if company else "unknown",
            "years": years[:YEARS]}


def _fetch_fundamentals(ticker: str) -> dict:
    """FMP if its free plan covers the ticker; otherwise Yahoo, with the reason recorded."""
    try:
        record = _from_fmp(ticker)
        record["fmp_note"] = None
        return record
    except FmpNotCovered as exc:
        note = str(exc)
    except FmpUnavailable as exc:
        note = str(exc)
        log.warning("FMP unavailable for %s (%s); using Yahoo", ticker, note)
    record = _from_yahoo(ticker)
    record["fmp_note"] = note
    return record


def get_fundamentals(ticker: str) -> CacheResult:
    """Cached normalized statements. Raises FundamentalsError if both providers fail
    and nothing is cached."""
    ticker = ticker.strip().upper()
    return get_or_fetch(f"fund:{ticker}", FUNDAMENTALS_TTL, lambda: _fetch_fundamentals(ticker))


# ---------------------------------------------------------------------------
# 3. Metrics: MarketMind's own formulas, the same for every provider
# ---------------------------------------------------------------------------
FORMULAS = {
    "revenue_growth": "revenue this year / revenue last year - 1",
    "revenue_cagr_3y": "(revenue this year / revenue 3 years earlier) ^ (1/3) - 1",
    "net_income_growth": "net income this year / net income last year - 1 (both years profitable)",
    "net_margin": "net income / revenue",
    "roe": "net income / shareholders' equity",
    "debt_to_equity": "total debt / shareholders' equity",
    "current_ratio": "current assets / current liabilities",
    "free_cash_flow": "operating cash flow - capital expenditure",
    "fcf_margin": "free cash flow / revenue",
    "profitable_years": "years with positive net income, out of the latest 4 years available",
    "pe": "market value / net income",
    "pb": "market value / shareholders' equity",
    "ps": "market value / revenue",
    "fcf_yield": "free cash flow / market value",
}
LABELS = {
    "revenue_growth": "Revenue growth (1 yr)", "revenue_cagr_3y": "Revenue growth (3-yr avg)",
    "net_income_growth": "Net income growth (1 yr)", "net_margin": "Net profit margin", "roe": "Return on equity",
    "debt_to_equity": "Debt to equity", "current_ratio": "Current ratio", "free_cash_flow": "Free cash flow",
    "fcf_margin": "Free cash flow margin", "profitable_years": "Profitable years", "pe": "Price to earnings (P/E)",
    "pb": "Price to book (P/B)", "ps": "Price to sales (P/S)", "fcf_yield": "Free cash flow yield",
}
BANK_SKIPPED = {"revenue_growth", "revenue_cagr_3y", "net_margin", "debt_to_equity", "current_ratio",
                "free_cash_flow", "fcf_margin", "ps", "fcf_yield"}


@dataclass
class Metric:
    key: str
    value: Optional[float]
    formula: str
    label: str
    note: Optional[str] = None  # why a value is missing, or a caveat
    inputs: dict = field(default_factory=dict)


def _div(a, b) -> Optional[float]:
    return a / b if a is not None and b not in (None, 0) else None


def free_cash_flow(year: dict) -> Optional[float]:
    """Both providers report capital expenditure as a negative number."""
    ocf, capex = year.get("operating_cash_flow"), year.get("capital_expenditure")
    if ocf is None:
        return None
    return ocf - abs(capex or 0.0)


def compute_metrics(record: dict, market_cap: Optional[float], industry: str = "") -> dict:
    """
    All metrics for one company from its normalized record (newest year first)
    and its current market value (Yahoo, delayed). Returns {key: Metric}.
    A metric that can't be calculated has value None and a note saying why.
    """
    years = record.get("years") or []
    out = {}

    def put(key, value, note=None, **inputs):
        out[key] = Metric(key, value, FORMULAS[key], LABELS[key], note, inputs)

    if not years:
        for key in FORMULAS:
            put(key, None, "no statements available")
        return out

    y0 = years[0]
    y1 = years[1] if len(years) > 1 else {}
    y3 = years[3] if len(years) > 3 else {}
    rev0, rev1, rev3 = y0.get("revenue"), y1.get("revenue"), y3.get("revenue")
    ni0, ni1 = y0.get("net_income"), y1.get("net_income")
    equity, debt = y0.get("equity"), y0.get("total_debt")
    fcf = free_cash_flow(y0)
    fy = y0.get("period_end")
    bank = industry in BANK_INDUSTRIES
    usd = record.get("currency") == "USD"

    # Growth
    put("revenue_growth", _div(rev0, rev1) - 1 if rev0 and rev1 and rev1 > 0 else None,
        None if rev1 else "needs two years of revenue", this_year=rev0, last_year=rev1, fiscal_year_end=fy)
    cagr = (rev0 / rev3) ** (1 / 3) - 1 if rev0 and rev3 and rev0 > 0 and rev3 > 0 else None
    put("revenue_cagr_3y", cagr, None if cagr is not None else "needs four years of revenue",
        this_year=rev0, three_years_earlier=rev3)
    nig = ni0 / ni1 - 1 if ni0 and ni1 and ni0 > 0 and ni1 > 0 else None
    put("net_income_growth", nig, None if nig is not None else "not meaningful unless both years are profitable",
        this_year=ni0, last_year=ni1)

    # Profitability and health
    put("net_margin", _div(ni0, rev0), net_income=ni0, revenue=rev0)
    if equity is not None and equity <= 0:
        put("roe", None, "not meaningful: shareholders' equity is zero or negative", equity=equity)
        put("debt_to_equity", None, "not meaningful: shareholders' equity is zero or negative", equity=equity)
    else:
        put("roe", _div(ni0, equity), net_income=ni0, equity=equity)
        put("debt_to_equity", _div(debt, equity),
            "providers can count lease obligations differently (a few percent)", total_debt=debt, equity=equity)
    put("current_ratio", _div(y0.get("current_assets"), y0.get("current_liabilities")),
        current_assets=y0.get("current_assets"), current_liabilities=y0.get("current_liabilities"))
    put("free_cash_flow", fcf, operating_cash_flow=y0.get("operating_cash_flow"),
        capital_expenditure=y0.get("capital_expenditure"))
    put("fcf_margin", _div(fcf, rev0), free_cash_flow=fcf, revenue=rev0)
    known = [y for y in years if y.get("net_income") is not None][:PROFIT_WINDOW]
    put("profitable_years", float(sum(1 for y in known if y["net_income"] > 0)) if known else None,
        f"out of {len(known)} years", years_available=len(known))

    # Valuation (needs the current market value, in the same currency)
    if market_cap is None or not usd:
        why = "market value unavailable" if market_cap is None else "statements not in U.S. dollars"
        for key in ("pe", "pb", "ps", "fcf_yield"):
            put(key, None, why)
    else:
        put("pe", _div(market_cap, ni0) if ni0 and ni0 > 0 else None,
            None if ni0 and ni0 > 0 else "not meaningful: net loss", market_value=market_cap, net_income=ni0)
        put("pb", _div(market_cap, equity) if equity and equity > 0 else None,
            None if equity and equity > 0 else "not meaningful: equity zero or negative", market_value=market_cap, equity=equity)
        put("ps", _div(market_cap, rev0), market_value=market_cap, revenue=rev0)
        put("fcf_yield", _div(fcf, market_cap), market_value=market_cap, free_cash_flow=fcf)

    # Banks: these measures aren't comparable (see BANK_INDUSTRIES)
    if bank:
        for key in BANK_SKIPPED:
            out[key].value = None
            out[key].note = "not used for banks and brokers: their statements define revenue, debt, and cash flow differently"
    for m in out.values():
        if m.value is not None and math.isnan(m.value):
            m.value = None
    return out

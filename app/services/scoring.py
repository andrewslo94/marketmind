"""
app/services/scoring.py — the Research Confidence Score (Section D).

What it measures
----------------
How strong the research case for a company looks right now, from real data
and fixed, published rules. It is NOT the probability of making money or a
prediction of the share price, and it never says buy or sell.

Five categories, each scored 0-100, then weighted:
    Financial health               25%  statements: debt, liquidity, margins, cash flow, consistency, growth
    Industry & market conditions   20%  current developments for the sector + the sector's recent price momentum
    News & catalysts               20%  the company's news this week: sentiment and catalyst events
    Valuation                      20%  price vs. fundamentals, ranked against sector peers
    Historical performance & risk  15%  the past year's price vs. the S&P 500, volatility, worst drop

Rules
-----
* A category is the average of its sub-scores. Each sub-score comes from a
  band table (BANDS below). Valuation compares each measure with the MEDIAN
  of the company's peers (ratio or gap), which stays fair even when a group
  is small. The same rules apply to every company; nothing is tuned by hand.
* Missing data is left out, never counted as zero. A category with no data
  is left out and the other weights are rescaled; the card says how many
  categories were used. Fewer than 3 categories -> no overall score.
* Outlook: overall >= 65 positive, >= 45 neutral, otherwise negative.

Public functions
----------------
build_context(companies, news_pause=0) -> Context   (shared data: peers, sector signals, prices, news)
score_company(company, ctx)            -> ScoreCard
score_universe(news_pause=0, save=False) -> (ScoreCards best first, Context); save=True stores the batch
load_snapshot()                        -> the saved batch for the Research pages, or None
explain_opportunity(card, rank, total, topics) -> "why identified" sentences
"""
import logging
import math
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.services import research_data as rd
from app.services.cache import peek, put
from app.services.implications import implications_for_article
from app.services.market_data import get_history, get_quote
from app.services.market_news import build_developments, sector_impact
from app.services.news_service import get_company_news
from app.services.sentiment import analyze_article

log = logging.getLogger(__name__)

WEIGHTS = {"health": 25, "industry": 20, "news": 20, "valuation": 20, "performance": 15}
CATEGORY_NAMES = {
    "health": "Financial health", "industry": "Industry & market conditions", "news": "News & catalysts",
    "valuation": "Valuation", "performance": "Historical performance & risk",
}
DISCLAIMER = ("The Research Confidence Score measures the strength of the research case from current data. "
              "It is not the probability of a profit, a price prediction, or a recommendation to buy or sell.")
MIN_CATEGORIES = 3
OUTLOOK = [(65, "Positive"), (45, "Neutral")]  # otherwise "Negative"
MIN_NEWS_ARTICLES = 3
MIN_CATALYST_ARTICLES = 2
MIN_PEERS = 3  # fewer other sector peers with a value -> compare with every non-bank company

# ---------------------------------------------------------------------------
# Band tables. ("low" = lower values are better)
# Each step is (threshold, points); the first threshold the value meets wins;
# a value meeting none earns the floor.
# ---------------------------------------------------------------------------
BANDS = {
    "debt_to_equity":    ("low",  [(0.5, 100), (1.0, 75), (2.0, 50), (3.0, 25)], 0),
    "current_ratio":     ("high", [(2.0, 100), (1.5, 75), (1.0, 50), (0.75, 25)], 0),
    "net_margin":        ("high", [(0.20, 100), (0.10, 75), (0.05, 50), (0.0, 25)], 0),
    "fcf_margin":        ("high", [(0.20, 100), (0.10, 75), (0.05, 50), (0.0, 25)], 0),
    "revenue_growth":    ("high", [(0.15, 100), (0.08, 75), (0.03, 50), (-0.03, 25)], 0),
    "net_income_growth": ("high", [(0.15, 100), (0.08, 75), (0.03, 50), (-0.03, 25)], 0),
    "roe":               ("high", [(0.15, 100), (0.12, 75), (0.08, 50), (0.05, 25)], 0),
    "vs_sp500_1y":       ("high", [(20, 100), (5, 75), (-5, 50), (-20, 25)], 0),     # percentage points
    "volatility":        ("low",  [(0.20, 100), (0.30, 75), (0.40, 50), (0.60, 25)], 0),
    "max_drawdown":      ("high", [(-0.10, 100), (-0.20, 75), (-0.30, 50), (-0.45, 25)], 0),
    "sector_momentum":   ("high", [(5, 100), (2, 75), (-2, 50), (-5, 25)], 0),        # percentage points
    # Valuation vs. peers: P/E, P/S, P/B as a multiple of the peer median ...
    "value_ratio":       ("low",  [(0.75, 100), (0.90, 75), (1.10, 50), (1.33, 25)], 0),
    # ... and free cash flow yield as a gap from the peer median, in percentage points
    "yield_gap":         ("high", [(1.5, 100), (0.5, 75), (-0.5, 50), (-1.5, 25)], 0),
}
# Sector signals from Market developments (interpretation, so never 0 or 100)
SIGNAL_POINTS = {"positive": 75, "mixed": 50, "either": 50, "none": 50, "negative": 25}

# Formatting for each measured value
PCT = lambda v: f"{v * 100:.1f}%"                                            # noqa: E731
FMT = {"debt_to_equity": lambda v: f"{v:.2f}", "current_ratio": lambda v: f"{v:.2f}", "net_margin": PCT,
       "fcf_margin": PCT, "revenue_growth": PCT, "net_income_growth": PCT, "roe": PCT,
       "vs_sp500_1y": lambda v: f"{v:+.1f} pts", "volatility": lambda v: f"{v * 100:.0f}%",
       "max_drawdown": lambda v: f"{v * 100:.0f}%", "sector_momentum": lambda v: f"{v:+.1f} pts",
       "pe": lambda v: f"{v:.1f}", "pb": lambda v: f"{v:.1f}", "ps": lambda v: f"{v:.1f}", "fcf_yield": PCT,
       "value_ratio": lambda v: f"{v:.2f}×", "yield_gap": lambda v: f"{v:+.1f} pts"}


def band_points(key: str, value: float):
    """(points, rule text) for a value under the band table for `key`."""
    direction, steps, floor = BANDS[key]
    fmt = FMT[key]
    for threshold, points in steps:
        if (value <= threshold) if direction == "low" else (value >= threshold):
            return points, f"{'≤' if direction == 'low' else '≥'} {fmt(threshold)} earns {points}"
    last = steps[-1][0]
    return floor, f"{'above' if direction == 'low' else 'below'} {fmt(last)} earns {floor}"


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------
@dataclass
class SubScore:
    key: str
    label: str
    display: str  # the measured value, formatted
    points: Optional[float]  # 0-100, or None when left out
    rule: str  # how the points were decided
    context: Optional[str] = None  # e.g. "sector median 0.71"
    extra: dict = field(default_factory=dict)  # details for risks/strengths


@dataclass
class Category:
    key: str
    name: str
    weight: int
    score: Optional[float] = None
    subs: list = field(default_factory=list)
    note: Optional[str] = None


@dataclass
class ScoreCard:
    ticker: str
    name: str
    sector: str
    industry: str
    source: str  # where the statements came from
    fiscal_year_end: Optional[str]
    overall: Optional[int]
    outlook: Optional[str]
    categories: list
    risks: list
    strengths: list
    categories_used: int
    news_articles: list = field(default_factory=list)  # this week's articles (facts) for the page
    price: Optional[float] = None
    price_time: Optional[str] = None


# ---------------------------------------------------------------------------
# Shared context: everything that compares a company with others
# ---------------------------------------------------------------------------
def price_stats(ticker: str) -> Optional[dict]:
    """1-year return, annualized volatility, worst drop from a high, 3-month return."""
    rows = get_history(ticker, "1Y").value or []
    closes = [r["c"] for r in rows if r.get("c")]
    if len(closes) < 120:  # about half a year of trading days
        return None
    daily = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    peak, worst = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        worst = min(worst, c / peak - 1)
    return {
        "return_1y": closes[-1] / closes[0] - 1,
        "volatility": statistics.stdev(daily) * math.sqrt(252),
        "max_drawdown": worst,
        "return_3m": closes[-1] / closes[-64] - 1 if len(closes) > 64 else None,
        "start": rows[0]["t"][:10], "end": rows[-1]["t"][:10],
    }


@dataclass
class Context:
    companies: dict  # ticker -> Company
    metrics: dict  # ticker -> {key: Metric}
    records: dict  # ticker -> normalized statements record
    quotes: dict  # ticker -> quote dict
    stats: dict  # ticker -> price_stats or None
    sp500: Optional[dict]
    sector_rows: dict  # sector -> sector_impact row
    sector_momentum: dict  # sector -> (pp vs S&P 500, companies used)
    news: dict  # ticker -> (articles or None, reason)
    built_at: str


def build_context(companies, news_pause: float = 0.0) -> Context:
    """
    Gather every input once, from the caches where possible. news_pause
    (seconds) spaces out fresh Finnhub calls; the terminal command uses it to
    stay under Finnhub's 60 calls per minute.
    """
    metrics, records, quotes, stats, news = {}, {}, {}, {}, {}
    for c in companies:
        try:
            records[c.ticker] = rd.get_fundamentals(c.ticker).value
        except Exception as exc:  # noqa: BLE001
            log.warning("No fundamentals for %s: %s", c.ticker, exc)
            records[c.ticker] = {"years": [], "source": "unavailable", "currency": c.financial_currency}
        try:
            quotes[c.ticker] = get_quote(c.ticker).value or {}
        except Exception:  # noqa: BLE001
            quotes[c.ticker] = {}
        metrics[c.ticker] = rd.compute_metrics(records[c.ticker], quotes[c.ticker].get("market_cap"), c.industry)
        try:
            stats[c.ticker] = price_stats(c.ticker)
        except Exception:  # noqa: BLE001
            stats[c.ticker] = None
        try:
            result = get_company_news(c.ticker, 7)
            news[c.ticker] = (result.value or [], None)
            if news_pause and not result.from_cache:
                time.sleep(news_pause)
        except Exception as exc:  # noqa: BLE001
            news[c.ticker] = (None, str(exc))

    try:
        sp500 = price_stats("^GSPC")
    except Exception:  # noqa: BLE001
        sp500 = None

    try:
        dev = build_developments()
        impact = sector_impact(dev["developments"], {"sectors": {}})
        sector_rows = {r["sector"]: r for r in impact["rows"]}
    except Exception as exc:  # noqa: BLE001
        log.warning("No developments for scoring: %s", exc)
        sector_rows = {}

    momentum = {}
    if sp500 and sp500.get("return_3m") is not None:
        by_sector = {}
        for c in companies:
            s = stats.get(c.ticker)
            if s and s.get("return_3m") is not None:
                by_sector.setdefault(c.sector, []).append(s["return_3m"])
        for sector, values in by_sector.items():
            momentum[sector] = ((statistics.mean(values) - sp500["return_3m"]) * 100, len(values))

    return Context(
        companies={c.ticker: c for c in companies}, metrics=metrics, records=records, quotes=quotes,
        stats=stats, sp500=sp500, sector_rows=sector_rows, sector_momentum=momentum, news=news,
        built_at=datetime.now(timezone.utc).isoformat(),
    )


def _peer_values(ctx: Context, company, key: str):
    """(other peers' values, description). Banks vs. the other banks; everyone
    else vs. sector peers, or every non-bank company when fewer than MIN_PEERS
    sector peers have a value."""
    def valid(tickers):
        return [ctx.metrics[t][key].value for t in tickers
                if t != company.ticker and ctx.metrics[t][key].value is not None]

    if company.is_bank:
        return valid([t for t, c in ctx.companies.items() if c.is_bank]), "the other banks"
    peers = valid([t for t, c in ctx.companies.items() if c.sector == company.sector and not c.is_bank])
    if len(peers) >= MIN_PEERS:
        return peers, f"{company.sector} peers"
    everyone = valid([t for t, c in ctx.companies.items() if not c.is_bank])
    return everyone, f"all non-bank companies ({company.sector} has too few peers)"


def _sector_median(ctx: Context, company, key: str) -> Optional[float]:
    values = [ctx.metrics[t][key].value for t, c in ctx.companies.items()
              if c.sector == company.sector and c.is_bank == company.is_bank and ctx.metrics[t][key].value is not None]
    return statistics.median(values) if len(values) >= 2 else None


# ---------------------------------------------------------------------------
# The five categories
# ---------------------------------------------------------------------------
def _band_sub(key, label, value, context=None) -> SubScore:
    if value is None:
        return SubScore(key, label, "—", None, "no data: left out")
    points, rule = band_points(key, value)
    return SubScore(key, label, FMT[key](value), points, rule, context)


def _health(company, m, ctx) -> Category:
    cat = Category("health", CATEGORY_NAMES["health"], WEIGHTS["health"])
    med = lambda k: _sector_median(ctx, company, k)  # noqa: E731

    def ctx_text(k):
        v = med(k)
        return f"sector median {FMT[k](v)}" if v is not None else None

    if company.is_bank:
        cat.note = "Banks and brokers use return on equity, profit growth, and consistency (their statements aren't comparable on debt or cash flow)."
        cat.subs += [_band_sub("roe", "Return on equity", m["roe"].value, ctx_text("roe")),
                     _band_sub("net_income_growth", "Net income growth (1 yr)", m["net_income_growth"].value)]
    else:
        de = m["debt_to_equity"]
        sub = _band_sub("debt_to_equity", "Debt to equity", de.value, ctx_text("debt_to_equity"))
        if de.value is None and de.note:
            sub.rule = f"left out: {de.note}"
        cat.subs.append(sub)
        cat.subs.append(_band_sub("current_ratio", "Current ratio", m["current_ratio"].value, ctx_text("current_ratio")))
        cat.subs.append(_band_sub("net_margin", "Net profit margin", m["net_margin"].value, ctx_text("net_margin")))
        cat.subs.append(_band_sub("fcf_margin", "Free cash flow margin", m["fcf_margin"].value, ctx_text("fcf_margin")))
        growth, label = m["revenue_cagr_3y"].value, "Revenue growth (3-yr avg)"
        if growth is None:
            growth, label = m["revenue_growth"].value, "Revenue growth (1 yr)"
        cat.subs.append(_band_sub("revenue_growth", label, growth))

    py = m["profitable_years"]
    available = py.inputs.get("years_available") or 0
    if py.value is not None and available:
        cat.subs.append(SubScore("profitable_years", "Profitable years", f"{int(py.value)} of {available}",
                                 round(100 * py.value / available), "share of recent years with a profit"))
    else:
        cat.subs.append(SubScore("profitable_years", "Profitable years", "—", None, "no data: left out"))
    return cat


def _valuation(company, m, ctx) -> Category:
    cat = Category("valuation", CATEGORY_NAMES["valuation"], WEIGHTS["valuation"])
    keys = [("pe", "Price to earnings (P/E)"), ("pb", "Price to book (P/B)")] if company.is_bank else \
           [("pe", "Price to earnings (P/E)"), ("ps", "Price to sales (P/S)"), ("fcf_yield", "Free cash flow yield")]
    fewest = None
    for key, label in keys:
        value = m[key].value
        if value is None:
            cat.subs.append(SubScore(key, label, "—", None, f"left out: {m[key].note or 'no data'}"))
            continue
        peers, who = _peer_values(ctx, company, key)
        if not peers:
            cat.subs.append(SubScore(key, label, FMT[key](value), None, "left out: no peers to compare"))
            continue
        fewest = len(peers) if fewest is None else min(fewest, len(peers))
        median = statistics.median(peers)
        if key == "fcf_yield":  # higher yield = cheaper; yields can be negative, so use the gap
            gap = (value - median) * 100
            points, band = band_points("yield_gap", gap)
            rule = f"{gap:+.1f} pts vs the median of {who} ({FMT[key](median)}); {band}"
            extra = {"median": median, "gap": gap}
        else:  # lower multiple = cheaper
            ratio = value / median if median > 0 else None
            if ratio is None:
                cat.subs.append(SubScore(key, label, FMT[key](value), None, "left out: peer median not positive"))
                continue
            points, band = band_points("value_ratio", ratio)
            rule = f"{ratio:.2f}× the median of {who} ({FMT[key](median)}); {band}"
            extra = {"median": median, "ratio": ratio}
        cat.subs.append(SubScore(key, label, FMT[key](value), points, rule, f"{len(peers)} peers", extra))
    cat.note = "Relative, not absolute: cheaper than the peer median earns more points."
    if fewest is not None and fewest < 3:
        cat.note += f" Only {fewest} peer(s) to compare, so treat this category as a rough guide."
    return cat


def _performance(company, ctx) -> Category:
    cat = Category("performance", CATEGORY_NAMES["performance"], WEIGHTS["performance"])
    s, sp = ctx.stats.get(company.ticker), ctx.sp500
    if not s:
        cat.note = "Price history unavailable."
        return cat
    if sp:
        diff = (s["return_1y"] - sp["return_1y"]) * 100
        sub = _band_sub("vs_sp500_1y", "1-year return vs S&P 500", diff,
                        f"{company.ticker} {s['return_1y'] * 100:+.1f}%, S&P 500 {sp['return_1y'] * 100:+.1f}%")
        cat.subs.append(sub)
    cat.subs.append(_band_sub("volatility", "Volatility (annualized)", s["volatility"]))
    cat.subs.append(_band_sub("max_drawdown", "Worst drop from a 1-year high", s["max_drawdown"]))
    cat.note = f"Daily closes {s['start']} to {s['end']} (Yahoo Finance, dividend-adjusted)."
    return cat


def _industry(company, ctx) -> Category:
    cat = Category("industry", CATEGORY_NAMES["industry"], WEIGHTS["industry"])
    row = ctx.sector_rows.get(company.sector)
    lean = row["lean"] if row else "none"
    groups = []
    if row:
        for kind, word in (("positive", "positive"), ("negative", "negative"), ("either", "unclear")):
            names = list(dict.fromkeys(e["topic"] for e in row[kind]))
            if names:
                groups.append(f"{word}: {', '.join(names)}")
    label = row["label"] if row else "No current signal"
    cat.subs.append(SubScore("sector_signal", f"Current developments for {company.sector}", label, SIGNAL_POINTS[lean],
                             "lean positive 75 · mixed or unclear 50 · lean negative 25 (interpretation)",
                             " · ".join(groups) if groups else None))
    mom = ctx.sector_momentum.get(company.sector)
    if mom:
        pp, n = mom
        cat.subs.append(_band_sub("sector_momentum", "Sector price momentum (3 months vs S&P 500)", pp,
                                  f"average of {n} {company.sector} companies in the universe"))
    else:
        cat.subs.append(SubScore("sector_momentum", "Sector price momentum (3 months vs S&P 500)", "—", None, "no data: left out"))
    return cat


def _news(company, ctx) -> Category:
    cat = Category("news", CATEGORY_NAMES["news"], WEIGHTS["news"])
    articles, reason = ctx.news.get(company.ticker, (None, "not fetched"))
    if articles is None:
        cat.note = f"News unavailable: {reason}."
        return cat
    if len(articles) < MIN_NEWS_ARTICLES:
        cat.note = f"Only {len(articles)} article(s) this week; at least {MIN_NEWS_ARTICLES} are needed."
        return cat

    labels = [analyze_article(a)["label"] for a in articles]
    pos, neg, total = labels.count("positive"), labels.count("negative"), len(labels)
    cat.subs.append(SubScore("news_sentiment", "News sentiment (7 days)", f"{pos} positive · {neg} negative · {total} total",
                             round(50 + 50 * (pos - neg) / total), "50 + 50 × (positive − negative) ÷ total articles"))

    good, bad, topics_good, topics_bad = 0, 0, [], []
    for a in articles:
        directions = {i["direction"]: i["topic"] for i in implications_for_article(a)}
        if "positive" in directions and "negative" not in directions:
            good += 1; topics_good.append(directions["positive"])
        elif "negative" in directions and "positive" not in directions:
            bad += 1; topics_bad.append(directions["negative"])
    if good + bad >= MIN_CATALYST_ARTICLES:
        listing = lambda items: ", ".join(f"{t} ×{n}" for t, n in _count(items))  # noqa: E731
        context = " · ".join(part for part in (
            f"positive: {listing(topics_good)}" if topics_good else "",
            f"negative: {listing(topics_bad)}" if topics_bad else "") if part)
        cat.subs.append(SubScore("catalysts", "Catalyst events", f"{good} positive · {bad} negative",
                                 round(50 + 50 * (good - bad) / (good + bad)),
                                 "50 + 50 × (positive − negative) ÷ catalyst articles", context,
                                 {"good": listing(topics_good), "bad": listing(topics_bad)}))
    else:
        cat.subs.append(SubScore("catalysts", "Catalyst events", f"{good + bad} found", None,
                                 f"left out: fewer than {MIN_CATALYST_ARTICLES} articles with a catalyst"))
    cat.note = "Finnhub tags articles loosely, so some only mention the company. Labels are MarketMind's rule-based interpretation."
    return cat


def _count(items):
    out = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return sorted(out.items(), key=lambda kv: -kv[1])


# ---------------------------------------------------------------------------
# Risks and strengths: plain sentences from the same numbers
# ---------------------------------------------------------------------------
def _risks_and_strengths(company, m, cats, ctx):
    risks, strengths = [], []
    y0 = (ctx.records[company.ticker].get("years") or [{}])[0]
    val = {s.key: s for c in cats for s in c.subs}
    ni, eq = y0.get("net_income"), y0.get("equity")

    if ni is not None and ni < 0:
        risks.append(f"Lost money in the fiscal year ending {y0.get('period_end')}.")
    if not company.is_bank:
        if eq is not None and eq <= 0:
            risks.append("Shareholders' equity is negative (often from large share buybacks), so debt ratios can't be measured.")
        de = m["debt_to_equity"].value
        if de is not None and de > 2:
            risks.append(f"Debt is {de:.1f}× shareholders' equity.")
        elif de is not None and de <= 0.5:
            strengths.append(f"Low debt: {de:.2f}× shareholders' equity.")
        cr = m["current_ratio"].value
        if cr is not None and cr < 1:
            risks.append(f"Current liabilities exceed current assets (current ratio {cr:.2f}).")
        rg = m["revenue_growth"].value
        if rg is not None and rg < 0:
            risks.append(f"Revenue fell {abs(rg) * 100:.1f}% in the latest fiscal year.")
        fcf = m["free_cash_flow"].value
        if fcf is not None and fcf < 0:
            risks.append("Free cash flow was negative: capital spending exceeded cash from operations.")
        fm = m["fcf_margin"].value
        if fm is not None and fm >= 0.20:
            strengths.append(f"Strong cash generation: free cash flow was {fm * 100:.0f}% of revenue.")
        nm = m["net_margin"].value
        if nm is not None and nm >= 0.20:
            strengths.append(f"High profit margin: {nm * 100:.0f}% of revenue.")
        cagr = m["revenue_cagr_3y"].value
        if cagr is not None and cagr >= 0.15:
            strengths.append(f"Revenue grew {cagr * 100:.0f}% a year over the last 3 years.")
    else:
        roe = m["roe"].value
        if roe is not None and roe >= 0.15:
            strengths.append(f"High return on equity for a bank: {roe * 100:.1f}%.")

    nig = m["net_income_growth"].value
    if nig is not None and nig <= -0.10:
        risks.append(f"Net income fell {abs(nig) * 100:.1f}% in the latest fiscal year.")

    py = m["profitable_years"]
    if py.value is not None and py.value == py.inputs.get("years_available") and py.value >= 3:
        strengths.append(f"Profitable in each of the last {int(py.value)} years.")

    pe = val.get("pe")
    if pe and pe.points is not None and pe.extra.get("ratio"):
        if pe.points <= 25:
            risks.append(f"Valued above its peers on earnings: P/E {pe.display} vs a peer median of "
                         f"{pe.extra['median']:.1f} ({pe.extra['ratio']:.2f}×).")
        elif pe.points >= 75:
            strengths.append(f"Valued below its peers on earnings: P/E {pe.display} vs a peer median of "
                             f"{pe.extra['median']:.1f} ({pe.extra['ratio']:.2f}×).")

    s = ctx.stats.get(company.ticker)
    if s:
        if s["volatility"] > 0.40:
            risks.append(f"Large price swings: annualized volatility of {s['volatility'] * 100:.0f}%.")
        if s["max_drawdown"] < -0.30:
            risks.append(f"Fell as much as {abs(s['max_drawdown']) * 100:.0f}% from a 1-year high.")
    rel = val.get("vs_sp500_1y")
    if rel and rel.points is not None:
        if rel.points == 0:
            risks.append(f"Trailed the S&P 500 by more than 20 points over the past year ({rel.display}).")
        elif rel.points == 100:
            strengths.append(f"Beat the S&P 500 by more than 20 points over the past year ({rel.display}).")

    sent = val.get("news_sentiment")
    if sent and sent.points is not None:
        if sent.points < 40:
            risks.append(f"This week's news leans negative ({sent.display}).")
        elif sent.points >= 65:
            strengths.append(f"This week's news leans positive ({sent.display}).")
    cata = val.get("catalysts")
    if cata and cata.points is not None:
        if cata.extra.get("good"):
            strengths.append(f"Positive catalyst events this week: {cata.extra['good']}.")
        if cata.extra.get("bad"):
            risks.append(f"Negative catalyst events this week: {cata.extra['bad']}.")

    row = ctx.sector_rows.get(company.sector)
    if row and row["lean"] in ("positive", "negative"):
        topics = ", ".join(dict.fromkeys(e["topic"] for e in row[row["lean"]]))
        text = f"Current developments point {row['lean']} for {company.sector} ({topics}); this is interpretation."
        (strengths if row["lean"] == "positive" else risks).append(text)
    return risks, strengths


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------
def score_company(company, ctx: Context) -> ScoreCard:
    m = ctx.metrics[company.ticker]
    cats = [_health(company, m, ctx), _industry(company, ctx), _news(company, ctx),
            _valuation(company, m, ctx), _performance(company, ctx)]
    for cat in cats:
        points = [s.points for s in cat.subs if s.points is not None]
        cat.score = round(statistics.mean(points), 1) if points else None
        if cat.score is None and not cat.note:
            cat.note = "No data for this category."

    used = [c for c in cats if c.score is not None]
    overall = outlook = None
    if len(used) >= MIN_CATEGORIES:
        overall = round(sum(c.weight * c.score for c in used) / sum(c.weight for c in used))
        outlook = next((label for floor, label in OUTLOOK if overall >= floor), "Negative")

    risks, strengths = _risks_and_strengths(company, m, cats, ctx)
    record = ctx.records[company.ticker]
    quote = ctx.quotes.get(company.ticker) or {}
    articles = ctx.news.get(company.ticker, (None, None))[0] or []
    return ScoreCard(
        ticker=company.ticker, name=company.name, sector=company.sector, industry=company.industry,
        source=record.get("source", "unavailable"),
        fiscal_year_end=(record.get("years") or [{}])[0].get("period_end"),
        overall=overall, outlook=outlook, categories=cats, risks=risks, strengths=strengths,
        categories_used=len(used), news_articles=articles,
        price=quote.get("price"), price_time=quote.get("market_time"),
    )


def score_universe(news_pause: float = 0.0, save: bool = False):
    companies = rd.load_universe()
    ctx = build_context(companies, news_pause=news_pause)
    cards = [score_company(c, ctx) for c in companies]
    cards.sort(key=lambda c: (c.overall is None, -(c.overall or 0)))
    if save:
        save_snapshot(cards, ctx)
    return cards, ctx


# ---------------------------------------------------------------------------
# The saved batch the Research pages read. Scoring all 64 companies needs about
# 64 news calls (Finnhub allows 60 a minute), so pages never score on the fly;
# `flask --app run research-scores` calculates and saves the batch.
# ---------------------------------------------------------------------------
SNAPSHOT_KEY = "research:snapshot"
SNAPSHOT_STALE_AFTER = timedelta(hours=24)


def save_snapshot(cards, ctx) -> datetime:
    rows = []
    for card in cards:
        row = asdict(card)  # plain dicts and lists, so it can be stored as JSON
        row["news_count"] = len(row.pop("news_articles") or [])
        rows.append(row)
    return put(SNAPSHOT_KEY, {"cards": rows, "sp500": ctx.sp500, "built_at": ctx.built_at})


def load_snapshot() -> Optional[dict]:
    """{"cards": [...], "calculated_at": datetime, "stale": bool, "sp500": {...}} or None."""
    result = peek(SNAPSHOT_KEY)
    if result is None:
        return None
    return {
        "cards": result.value["cards"],
        "sp500": result.value.get("sp500"),
        "calculated_at": result.fetched_at,
        "stale": datetime.now(timezone.utc) - result.fetched_at > SNAPSHOT_STALE_AFTER,
    }


def explain_opportunity(card: dict, rank: int, total: int, coverage_topics=None, include_strengths=True) -> list:
    """
    Plain sentences saying why a company was identified for research, built
    only from its saved score card (and, if given, the market-coverage topics
    that name it). Interpretation: the page labels it so.
    """
    why = [f"Ranks {rank} of {total} companies you don't hold, with a Research Confidence Score "
           f"of {card['overall']}/100."]
    strong = [f"{c['name'].lower()} ({c['score']:.0f})" for c in card["categories"]
              if c["score"] is not None and c["score"] >= 75]
    if strong:
        why.append("Strongest areas: " + ", ".join(strong) + ".")
    if include_strengths:  # the company page lists all strengths separately
        why.extend(card["strengths"][:3])
    if coverage_topics:
        why.append("Named in current market coverage: " + ", ".join(coverage_topics) + ".")
    return why

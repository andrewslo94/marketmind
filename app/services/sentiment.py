"""
app/services/sentiment.py — rule-based news sentiment. No AI API.

How it works
------------
1. VADER (vaderSentiment) is a dictionary of ~7,500 English words with a
   human-rated score from -4 (very negative) to +4 (very positive). It also
   handles negation ("not good"), intensifiers ("very"), and punctuation.
2. VADER knows everyday English, not finance: "beats estimates" scores 0,
   "shares tumble" scores slightly positive. So we ADD a finance lexicon
   (below) to VADER's dictionary with the same -4..+4 scale.
3. Multi-word phrases ("raises guidance", "cut guidance") can't go in a
   word dictionary, so the text is pre-processed to fold each phrase into
   one token ("raises_guidance") that IS in the dictionary.
4. VADER's "compound" score (-1..+1) is mapped to a label:
       >= +0.10 positive  |  <= -0.10 negative  |  otherwise neutral
   and every finance term that matched is reported as the REASON, so the
   page can show why a label was assigned.

This is interpretation, not fact. The UI labels it that way.

Public function
---------------
analyze(text) -> dict(label, score, matched=[{term, polarity, weight}], ...)
analyze_article(article) -> same, computed on headline + provider summary
"""
import re

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

METHOD = "VADER lexicon + MarketMind finance keyword list (rule-based, no AI model)"
POSITIVE_THRESHOLD = 0.10
NEGATIVE_THRESHOLD = -0.10

# ---------------------------------------------------------------------------
# Finance lexicon. Scores are on VADER's -4..+4 scale. Edit freely: this is
# the "keyword list we write together". Keys must be single lowercase tokens;
# phrases are folded into tokens via PHRASES below (space -> underscore).
# ---------------------------------------------------------------------------
FINANCE_LEXICON = {
    # --- Positive: results, guidance, ratings ---
    "beat": 2.0, "beats": 2.0, "beating": 2.0, "outperform": 2.0, "outperforms": 2.0,
    "outperformed": 2.0, "upgrade": 2.2, "upgrades": 2.2, "upgraded": 2.2,
    "raises_guidance": 2.8, "raised_guidance": 2.8, "record_high": 2.4, "record_revenue": 2.4,
    "record_profit": 2.4, "all_time_high": 2.4, "strong_demand": 2.0, "better_than_expected": 2.4,
    "topped_estimates": 2.2, "tops_estimates": 2.2, "exceeded_expectations": 2.4,
    # --- Positive: price action & growth ---
    "surge": 1.8, "surges": 1.8, "surged": 1.8, "soar": 1.8, "soars": 1.8, "soared": 1.8,
    "rally": 1.5, "rallies": 1.5, "rallied": 1.5, "jump": 1.3, "jumps": 1.3, "jumped": 1.3,
    "climb": 1.0, "climbs": 1.0, "climbed": 1.0, "gain": 1.0, "gains": 1.0, "gained": 1.0,
    "rebound": 1.2, "rebounds": 1.2, "rebounded": 1.2, "growth": 1.2, "expansion": 1.2,
    "profitable": 1.6, "profitability": 1.4, "momentum": 0.8, "bullish": 1.8,
    # --- Positive: corporate actions & events ---
    "buyback": 1.6, "buybacks": 1.6, "dividend_increase": 2.0, "raises_dividend": 2.0,
    "approval": 1.6, "approves": 1.6, "approved": 1.6, "partnership": 1.0, "contract_win": 2.0,
    "wins_contract": 2.0, "acquisition": 0.4, "acquires": 0.4, "launch": 0.6, "launches": 0.6,
    "breakthrough": 1.8, "milestone": 1.2, "innovation": 0.8,
    # --- Negative: results, guidance, ratings ---
    "miss": -2.0, "misses": -2.0, "missed": -2.0, "underperform": -2.0, "underperforms": -2.0,
    "downgrade": -2.2, "downgrades": -2.2, "downgraded": -2.2, "cut_guidance": -2.8,
    "cuts_guidance": -2.8, "lowers_guidance": -2.6, "lowered_guidance": -2.6, "weak_demand": -2.0,
    "weak_guidance": -2.2, "soft_guidance": -1.8, "disappointing": -1.8, "disappoints": -1.8,
    "worse_than_expected": -2.4, "below_expectations": -2.2, "profit_warning": -2.8, "shortfall": -1.8,
    # --- Negative: price action & performance ---
    "plunge": -2.2, "plunges": -2.2, "plunged": -2.2, "tumble": -1.8, "tumbles": -1.8, "tumbled": -1.8,
    "slump": -1.6, "slumps": -1.6, "slumped": -1.6, "sink": -1.4, "sinks": -1.4, "sank": -1.4,
    "fall": -1.0, "falls": -1.0, "fell": -1.0, "drop": -1.0, "drops": -1.0, "dropped": -1.0,
    "decline": -1.0, "declines": -1.0, "declined": -1.0, "slide": -1.0, "slides": -1.0, "slid": -1.0,
    "selloff": -1.8, "sell_off": -1.8, "bearish": -1.8, "volatility": -0.6, "losses": -1.6,
    "loss": -1.4, "unprofitable": -1.6, "write_down": -1.8, "writedown": -1.8, "impairment": -1.8,
    # --- Negative: corporate / legal / regulatory events ---
    "layoff": -1.6, "layoffs": -1.6, "job_cuts": -1.6, "closure": -1.2, "closures": -1.2,
    "lawsuit": -1.8, "sued": -1.8, "litigation": -1.4, "investigation": -1.8, "probe": -1.6,
    "subpoena": -1.8, "fine": -1.4, "fined": -1.6, "penalty": -1.6, "antitrust": -1.4,
    "recall": -1.8, "recalls": -1.8, "recalled": -1.8, "defect": -1.6, "outage": -1.4, "breach": -2.0,
    "hack": -1.8, "fraud": -2.6, "bankruptcy": -3.0, "bankrupt": -3.0, "default": -2.2,
    "delisting": -2.4, "dilution": -1.4, "dividend_cut": -2.4, "cuts_dividend": -2.4,
    "suspends_dividend": -2.4, "short_seller": -1.6, "delay": -1.0, "delays": -1.0, "delayed": -1.0,
    "tariff": -0.8, "tariffs": -0.8, "sanction": -1.2, "sanctions": -1.2, "strike": -1.2,
    "downturn": -1.6, "recession": -1.8, "headwind": -1.2, "headwinds": -1.2,
    # --- Words VADER scores the wrong way in finance: override ---
    "sell": -0.8,     # "downgrades to sell"
    "cut": -1.0, "cuts": -1.0,
    "record": 0.0,    # neutral alone; "record_high" carries the signal
    "high": 0.0,      # VADER gives "high" +0.3? keep neutral in finance text
}

# Phrases folded into single tokens BEFORE scoring (longest first so
# "all-time high" is matched before "high"). Hyphens are treated as spaces.
PHRASES = sorted(
    [k.replace("_", " ") for k in FINANCE_LEXICON if "_" in k],
    key=len,
    reverse=True,
)

_analyzer = SentimentIntensityAnalyzer()
_analyzer.lexicon.update(FINANCE_LEXICON)

_WORD_RE = re.compile(r"[a-z_]+")


def _prepare(text: str) -> str:
    """Lowercase, normalize hyphens, and fold known phrases into tokens."""
    t = (text or "").lower().replace("-", " ").replace("’", "'")
    t = re.sub(r"\s+", " ", t)
    for phrase in PHRASES:
        t = t.replace(phrase, phrase.replace(" ", "_"))
    return t


def _matched_terms(prepared: str) -> list[dict]:
    """Every finance term present in the text, with its polarity and weight."""
    seen, found = set(), []
    for token in _WORD_RE.findall(prepared):
        weight = FINANCE_LEXICON.get(token)
        if weight is None or weight == 0 or token in seen:
            continue
        seen.add(token)
        found.append(
            {
                "term": token.replace("_", " "),
                "weight": weight,
                "polarity": "positive" if weight > 0 else "negative",
            }
        )
    # Strongest signals first so the page can show the top few.
    found.sort(key=lambda m: abs(m["weight"]), reverse=True)
    return found


def analyze(text: str) -> dict:
    """
    Score one piece of text.
    Returns: label ('positive' | 'neutral' | 'negative'), score (VADER
    compound, -1..+1), matched (finance terms found), method, thresholds.
    """
    prepared = _prepare(text)
    scores = _analyzer.polarity_scores(prepared) if prepared.strip() else {"compound": 0.0}
    compound = round(scores["compound"], 3)
    if compound >= POSITIVE_THRESHOLD:
        label = "positive"
    elif compound <= NEGATIVE_THRESHOLD:
        label = "negative"
    else:
        label = "neutral"
    return {
        "label": label,
        "score": compound,
        "matched": _matched_terms(prepared),
        "method": METHOD,
        "thresholds": {"positive": POSITIVE_THRESHOLD, "negative": NEGATIVE_THRESHOLD},
    }


def analyze_article(article: dict) -> dict:
    """
    Sentiment for a news article dict from news_service: scored on the
    headline plus the provider's summary (the only article text we have —
    we never fetch or invent the full article).
    """
    text = " . ".join(part for part in (article.get("headline"), article.get("summary")) if part)
    result = analyze(text)
    result["text_used"] = "headline + provider summary" if article.get("summary") else "headline only"
    return result

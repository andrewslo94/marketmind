"""
app/services/market_news.py — Section C, "Market developments": general
market news grouped into topics, with rule-based sector impact.

Facts vs interpretation
-----------------------
Facts:          headlines, publishers, times, links (Finnhub general news), and
                which example companies are named in that text.
Interpretation: which topic an article belongs to, the direction the coverage
                leans, and which sectors could see positive or negative
                implications. All of it comes from the keyword map in
                topic_map.py, and the page labels it as interpretation.

How matching works
------------------
Text is lower-cased and hyphens become spaces. A keyword must appear as a
whole word or phrase ("ai" matches "AI chips" but not "airline"). An article
joins a topic if one keyword is in its headline, or two different keywords
are in its summary. Each topic's keywords (and each direction's phrases)
are compiled into ONE combined regular expression, so checking 100 articles
against thousands of phrases stays fast.

Known limit: keyword rules can't read negation ("no rate cut") or sarcasm,
so the page shows the matched words for every signal and lets you judge.

Public function
---------------
build_developments() -> {"developments": [...], "quiet": [...], "headlines": [...], "meta": {...}}
"""
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.services import topic_map as tm
from app.services.news_service import NewsError, get_market_news

log = logging.getLogger(__name__)

HEADLINE_HITS_NEEDED = 1
SUMMARY_HITS_NEEDED = 2
FACT_ARTICLES_SHOWN = 3
LEAN_RATIO = 2  # one direction needs at least 2x the articles of the other


def normalize(text: Optional[str]) -> str:
    t = (text or "").lower()
    t = t.replace("’", "'").replace("‘", "'").replace("-", " ").replace("—", " ").replace("–", " ")
    return re.sub(r"\s+", " ", t).strip()


def compile_phrases(phrases) -> re.Pattern:
    """One regex matching any of the phrases as whole words. Longest first,
    so 'rate cuts' wins over 'rate cut' when both could match."""
    unique = sorted({normalize(p) for p in phrases}, key=len, reverse=True)
    body = "|".join(re.escape(p) for p in unique)
    return re.compile(r"(?<![a-z0-9])(?:" + body + r")(?![a-z0-9])")


def find(pattern: re.Pattern, text: str) -> set:
    return {m.group(0) for m in pattern.finditer(text)}


# Compile everything once, when the module is first imported.
_KEYWORDS = {t["key"]: compile_phrases(t["keywords"]) for t in tm.TOPICS}
_EXCLUDE = {t["key"]: [normalize(x) for x in t.get("exclude", [])] for t in tm.TOPICS}
_SCENARIO = {(t["key"], s["key"]): compile_phrases(s["phrases"]) for t in tm.TOPICS for s in t["scenarios"]}
_ALIASES = [(ticker, compile_phrases(aliases)) for ticker, (_name, _sector, aliases) in tm.COMPANIES.items()]


def _without_excluded(text: str, topic_key: str) -> str:
    for phrase in _EXCLUDE[topic_key]:
        text = text.replace(phrase, " ")
    return text


def classify(article: dict) -> dict:
    """{topic_key: [matched keywords]} for every topic this article belongs to."""
    head, summary = normalize(article.get("headline")), normalize(article.get("summary"))
    out = {}
    for t in tm.TOPICS:
        k = t["key"]
        in_head = find(_KEYWORDS[k], _without_excluded(head, k))
        in_summary = find(_KEYWORDS[k], _without_excluded(summary, k))
        if len(in_head) >= HEADLINE_HITS_NEEDED or len(in_summary) >= SUMMARY_HITS_NEEDED:
            out[k] = sorted(in_head | in_summary)
    return out


def mentioned_companies(articles) -> list:
    """Example-list companies named in the articles' text (a fact about the text)."""
    found = []
    for a in articles:
        text = normalize(f"{a.get('headline')} . {a.get('summary')}")
        for ticker, pattern in _ALIASES:
            if ticker not in found and pattern.search(text):
                found.append(ticker)
    return found


def detect_signal(topic: dict, articles) -> dict:
    """
    Which direction does the coverage lean? Counts articles (not words) that
    contain each scenario's phrases. A scenario 'leads' when it has more
    articles than the other and at least LEAN_RATIO times as many.
    """
    counts, words = {}, {}
    for s in topic["scenarios"]:
        n, seen = 0, Counter()
        for a in articles:
            text = _without_excluded(normalize(f"{a.get('headline')} . {a.get('summary')}"), topic["key"])
            hits = find(_SCENARIO[(topic["key"], s["key"])], text)
            if hits:
                n += 1
                seen.update(hits)
        counts[s["key"]] = n
        words[s["key"]] = seen.most_common(4)

    first, second = topic["scenarios"]
    a, b = counts[first["key"]], counts[second["key"]]
    if a == b == 0:
        status, lead = "none", None
    elif a > b and a >= LEAN_RATIO * b:
        status, lead = "leans", first
    elif b > a and b >= LEAN_RATIO * a:
        status, lead = "leans", second
    else:
        status, lead = "mixed", None
    return {"status": status, "lead": lead, "counts": counts, "words": words}


# ---------- building the page model ----------
def _company(ticker: str) -> dict:
    name, sector, _aliases = tm.COMPANIES[ticker]
    return {"ticker": ticker, "name": name, "sector": sector}


def _effects(lines) -> list:
    return [{"sector": sector, "detail": detail, "companies": [_company(t) for t in tickers]}
            for sector, detail, tickers in lines]


def _read_through(lines, mentioned) -> list:
    """Earnings: replace the generic line with the sectors of companies named in the coverage."""
    if not lines:
        return []
    detail = lines[0][1]
    by_sector = {}
    for ticker in mentioned:
        by_sector.setdefault(tm.COMPANIES[ticker][1], []).append(ticker)
    if not by_sector:
        return _effects(lines)
    return [{"sector": f"{sector} (industry of companies named in the coverage)", "detail": detail,
             "companies": [_company(t) for t in tickers]} for sector, tickers in by_sector.items()]


@dataclass
class Development:
    key: str
    name: str
    why: str
    articles: list  # most matched keywords first, then newest; each has "topics"
    coverage: int
    signal: dict
    scenarios: list = field(default_factory=list)  # [{key, label, positive, negative}]
    lead_key: Optional[str] = None
    mentioned: list = field(default_factory=list)
    monitor: list = field(default_factory=list)

    @property
    def shown(self):
        return self.articles[:FACT_ARTICLES_SHOWN]

    @property
    def more(self):
        return self.articles[FACT_ARTICLES_SHOWN:]


def _build_development(topic: dict, members: list) -> Development:
    mentioned = mentioned_companies(members)
    signal = detect_signal(topic, members)
    scenarios = []
    for s in topic["scenarios"]:
        if topic.get("read_through"):
            positive, negative = _read_through(s["positive"], mentioned), _read_through(s["negative"], mentioned)
        else:
            positive, negative = _effects(s["positive"]), _effects(s["negative"])
        scenarios.append({"key": s["key"], "label": s["label"], "positive": positive, "negative": negative})
    if signal["lead"]:  # lead with the direction the coverage points to
        scenarios.sort(key=lambda sc: sc["key"] != signal["lead"]["key"])
    return Development(
        key=topic["key"], name=topic["name"], why=topic["why"], articles=members,
        coverage=len(members), signal=signal, scenarios=scenarios,
        lead_key=signal["lead"]["key"] if signal["lead"] else None,
        mentioned=[_company(t) for t in mentioned], monitor=topic["monitor"],
    )


def build_developments() -> dict:
    """Group the latest general market news into topic 'developments'."""
    try:
        result = get_market_news()
    except NewsError as exc:
        return {"error": str(exc), "developments": [], "quiet": [], "headlines": [], "meta": {}}
    except Exception as exc:  # noqa: BLE001
        log.warning("Market news failed: %s", exc)
        return {"error": "Data unavailable", "developments": [], "quiet": [], "headlines": [], "meta": {}}

    headlines = []
    for a in result.value or []:
        item = dict(a)
        item["topics"] = classify(a)
        headlines.append(item)

    developments = []
    for t in tm.TOPICS:
        members = [a for a in headlines if t["key"] in a["topics"]]
        if members:
            # Most on-topic first (most matched keywords), newest first among equals,
            # so a card leads with its most representative story, not just the latest.
            members.sort(key=lambda a: a["published_at"] or "", reverse=True)
            members.sort(key=lambda a: len(a["topics"][t["key"]]), reverse=True)
            developments.append(_build_development(t, members))
    # Most-covered first; ties go to the topic with the most recent story. (Python's
    # sort is stable, so sorting by date first and coverage second gives exactly that.)
    developments.sort(key=lambda d: max(a["published_at"] or "" for a in d.articles), reverse=True)
    developments.sort(key=lambda d: d.coverage, reverse=True)

    covered = {d.key for d in developments}
    names = {t["key"]: t["name"] for t in tm.TOPICS}
    matched = sum(1 for a in headlines if a["topics"])
    return {
        "error": None,
        "developments": developments,
        "quiet": [t["name"] for t in tm.TOPICS if t["key"] not in covered],
        "headlines": headlines,
        "topic_names": names,
        "meta": {
            "total": len(headlines),
            "matched": matched,
            "unmatched": len(headlines) - matched,
            "fetched_at": result.fetched_at,
            "stale": result.stale,
            "oldest": min((a["published_at"] for a in headlines if a["published_at"]), default=None),
            "newest": max((a["published_at"] for a in headlines if a["published_at"]), default=None),
            "sources": [s for s, _n in Counter(a["publisher"] for a in headlines).most_common()],
        },
    }

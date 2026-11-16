"""
app/services/summarizer.py — EXTRACTIVE summaries. No AI, no new words.

"Extractive" means the summary is made only of sentences copied verbatim
from the source text (here: the headline and the provider's own summary).
We never paraphrase or generate text, so nothing can be invented. The page
labels the result as auto-selected sentences.

How a sentence earns its place (simple, explainable scoring):
    +1.0  it is the first sentence (news puts the key fact first)
    +2.0  it names the company (ticker or a word from the company name)
    +1.5  it contains a number, percentage, or dollar amount (concrete fact)
    +0.5  per finance keyword from sentiment.FINANCE_LEXICON (max +2.0)
    -1.0  very short (< 6 words) or very long (> 45 words)
    skip  boilerplate ("read more", "sign up", "copyright", ...)
The top-scoring sentences (default 2) are shown in their original order.

Public function
---------------
summarize(text, ticker=None, company=None, max_sentences=2) -> dict
summarize_article(article, company=None) -> dict
"""
import re

from app.services.sentiment import FINANCE_LEXICON, _prepare

METHOD = "extractive: top-scoring sentences copied from the provider's text, no generated wording"

# Protect common abbreviations so "Inc." doesn't end a sentence.
_ABBREVIATIONS = ["inc", "corp", "co", "ltd", "llc", "u.s", "u.k", "e.u", "vs", "mr", "ms", "dr", "jr", "sr", "no", "st"]
_ABBR_RE = re.compile(r"\b(" + "|".join(re.escape(a) for a in _ABBREVIATIONS) + r")\.", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"“(]?[A-Z0-9])")
_NUMBER_RE = re.compile(r"(\$\s?\d|\d+(\.\d+)?\s?%|\b\d{2,}\b|\b\d+\.\d+\b)")
_BOILERPLATE = ("read more", "click here", "sign up", "subscribe", "copyright", "all rights reserved",
                "terms of use", "privacy policy", "the views and opinions", "this article was")
_STOPWORDS = {"inc", "corp", "corporation", "company", "co", "ltd", "the", "and", "of", "group", "holdings", "plc"}


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, keeping abbreviations intact."""
    if not text:
        return []
    protected = _ABBR_RE.sub(lambda m: m.group(1) + "<DOT>", text.strip())
    parts = _SENTENCE_END.split(protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


def _company_words(ticker, company) -> set[str]:
    words = set()
    if ticker:
        words.add(ticker.lower())
    for w in re.findall(r"[a-z]+", (company or "").lower()):
        if len(w) > 3 and w not in _STOPWORDS:
            words.add(w)
    return words


def _score(sentence: str, index: int, company_words: set[str]) -> tuple[float, list[str]]:
    low = sentence.lower()
    if any(b in low for b in _BOILERPLATE):
        return float("-inf"), ["boilerplate"]
    reasons, score = [], 0.0
    if index == 0:
        score += 1.0; reasons.append("first sentence")
    tokens = set(re.findall(r"[a-z]+", low))
    if company_words & tokens:
        score += 2.0; reasons.append("names the company")
    if _NUMBER_RE.search(sentence):
        score += 1.5; reasons.append("contains a figure")
    hits = [t for t in re.findall(r"[a-z_]+", _prepare(sentence)) if FINANCE_LEXICON.get(t)]
    if hits:
        bonus = min(2.0, 0.5 * len(set(hits))); score += bonus
        reasons.append(f"finance terms: {', '.join(sorted(set(h.replace('_', ' ') for h in hits)))}")
    n_words = len(sentence.split())
    if n_words < 6 or n_words > 45:
        score -= 1.0; reasons.append("length penalty")
    return score, reasons


def summarize(text: str, ticker=None, company=None, max_sentences: int = 2) -> dict:
    """
    Returns:
        summary        the selected sentences joined, in original order ('' if none)
        sentences      [{text, score, reasons, selected}] for the "why" display
        is_full_text   True if the source had <= max_sentences sentences
                       (nothing was left out, so it isn't really a summary)
        method         description for the label
    """
    sentences = split_sentences(text)
    company_words = _company_words(ticker, company)
    scored = []
    for i, s in enumerate(sentences):
        sc, why = _score(s, i, company_words)
        scored.append({"text": s, "score": sc, "reasons": why, "selected": False})

    candidates = [s for s in scored if s["score"] != float("-inf")]
    is_full_text = len(candidates) <= max_sentences
    top = sorted(candidates, key=lambda s: s["score"], reverse=True)[:max_sentences]
    for s in top:
        s["selected"] = True
    chosen = [s["text"] for s in scored if s["selected"]]  # original order
    return {
        "summary": " ".join(chosen),
        "sentences": scored,
        "is_full_text": is_full_text,
        "sentence_count": len(sentences),
        "method": METHOD,
    }


def summarize_article(article: dict, company=None) -> dict:
    """Summarize headline + provider summary of a news_service article."""
    text = " ".join(p for p in (article.get("headline"), article.get("summary")) if p)
    ticker = (article.get("tickers") or [article.get("ticker")])[0]
    return summarize(text, ticker=ticker, company=company)

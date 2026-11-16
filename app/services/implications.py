"""
app/services/implications.py — rule-based "potential implications" for a
news article. Interpretation, not fact; never a recommendation.

Each RULE has: a topic name, trigger keywords (matched as whole words or
phrases in the article's headline + provider summary), a direction, a
generic implication for the company, and what to watch next. Only rules
whose keywords actually appear are reported, together with the keywords
that fired, so the reader can see exactly why. If nothing matches, the
page says so instead of inventing an implication.

Public function
---------------
find_implications(text) -> list of {topic, direction, matched, implication, watch}
implications_for_article(article) -> same, on headline + provider summary
"""
import re

METHOD = "keyword rules written by MarketMind; generic by design, not specific advice"

RULES = [
    {
        "topic": "Results above expectations",
        "direction": "positive",
        "keywords": ["beats", "beat estimates", "beat expectations", "topped estimates", "tops estimates",
                     "better than expected", "exceeded expectations", "record revenue", "record profit", "record quarter"],
        "implication": "Reported results above expectations can support near-term sentiment and may lead analysts to revise estimates upward.",
        "watch": "Forward guidance, margin trends, and whether the beat relied on one-time items.",
    },
    {
        "topic": "Results below expectations",
        "direction": "negative",
        "keywords": ["misses", "missed estimates", "missed expectations", "below expectations", "worse than expected",
                     "shortfall", "disappointing results", "disappoints"],
        "implication": "Results below expectations often pressure the share price and can trigger estimate cuts.",
        "watch": "Management's explanation, whether the miss is one-off or structural, and the next quarter's guidance.",
    },
    {
        "topic": "Guidance raised",
        "direction": "positive",
        "keywords": ["raises guidance", "raised guidance", "raises outlook", "raised outlook", "raises forecast", "lifts guidance"],
        "implication": "Higher guidance signals management expects stronger demand or margins than previously communicated.",
        "watch": "Whether later quarters deliver on the raised targets; consensus estimate revisions.",
    },
    {
        "topic": "Guidance cut or warning",
        "direction": "negative",
        "keywords": ["cuts guidance", "cut guidance", "lowers guidance", "lowered guidance", "profit warning",
                     "weak guidance", "soft guidance", "lowers outlook", "cuts outlook", "cuts forecast"],
        "implication": "Lower guidance usually weighs on the stock and raises questions about demand, costs, or execution.",
        "watch": "The stated reasons, the size of the cut, and whether peers report similar pressure.",
    },
    {
        "topic": "Analyst upgrade",
        "direction": "positive",
        "keywords": ["upgrade", "upgrades", "upgraded", "raises price target", "price target raised", "initiates with buy", "overweight"],
        "implication": "Rating or target upgrades can draw attention and short-term buying interest, but are one firm's opinion.",
        "watch": "The reasoning behind the call and whether other analysts follow.",
    },
    {
        "topic": "Analyst downgrade",
        "direction": "negative",
        "keywords": ["downgrade", "downgrades", "downgraded", "cuts price target", "price target cut", "underweight", "to sell"],
        "implication": "Downgrades can pressure the share price and signal concerns about valuation or fundamentals.",
        "watch": "The specific concern raised (valuation, growth, competition) and whether the data supports it.",
    },
    {
        "topic": "Merger or acquisition",
        "direction": "mixed",
        "keywords": ["acquire", "acquires", "acquisition", "merger", "merge", "to buy", "takeover", "buyout", "deal to"],
        "implication": "Deals can add growth or scale but also carry integration risk, debt, and regulatory review; the effect differs for buyer and target.",
        "watch": "Deal price versus value, financing, antitrust review, and expected synergies.",
    },
    {
        "topic": "Product launch or approval",
        "direction": "positive",
        "keywords": ["launch", "launches", "launched", "unveils", "unveiled", "approval", "approves", "approved", "fda", "wins contract", "contract win"],
        "implication": "New products, approvals, or contracts can open revenue opportunities, though commercial impact takes time to show in results.",
        "watch": "Adoption or sales figures in coming quarters and competitor responses.",
    },
    {
        "topic": "Legal or regulatory action",
        "direction": "negative",
        "keywords": ["lawsuit", "sued", "litigation", "investigation", "probe", "subpoena", "antitrust", "regulator", "regulators",
                     "fine", "fined", "penalty", "settlement", "sec charges", "ftc", "doj"],
        "implication": "Legal and regulatory actions create uncertainty and possible costs; outcomes are often slow and hard to predict.",
        "watch": "Potential penalty size relative to the company's earnings, and any required business changes.",
    },
    {
        "topic": "Layoffs or restructuring",
        "direction": "mixed",
        "keywords": ["layoff", "layoffs", "job cuts", "cuts jobs", "restructuring", "restructure", "closure", "closures", "cost cuts", "cost cutting"],
        "implication": "Cost reductions can lift margins but may also signal weaker demand; markets read them differently depending on context.",
        "watch": "Restructuring charges, savings targets, and revenue trends after the cuts.",
    },
    {
        "topic": "Dividend or buyback change",
        "direction": "mixed",
        "keywords": ["dividend", "buyback", "buybacks", "share repurchase", "repurchase program"],
        "implication": "Increases return cash to shareholders and signal confidence; cuts or suspensions usually signal financial strain.",
        "watch": "Whether the payout is covered by free cash flow and how debt levels change.",
    },
    {
        "topic": "Security incident or outage",
        "direction": "negative",
        "keywords": ["outage", "breach", "data breach", "hack", "hacked", "cyberattack", "ransomware", "recall", "recalls", "defect"],
        "implication": "Operational incidents can bring direct costs, customer trust issues, and regulatory scrutiny.",
        "watch": "Scope of the incident, remediation costs, and any customer or contract losses.",
    },
    {
        "topic": "Leadership change",
        "direction": "mixed",
        "keywords": ["ceo", "chief executive", "cfo", "steps down", "resigns", "resigned", "appoints", "appointed", "names new", "successor"],
        "implication": "Executive changes can shift strategy; the market reaction depends on the reason and the successor's track record.",
        "watch": "Stated reasons for the change and any strategy updates from the new leadership.",
    },
    {
        "topic": "Tariffs or trade policy",
        "direction": "negative",
        "keywords": ["tariff", "tariffs", "trade war", "export controls", "export ban", "sanction", "sanctions", "import duties"],
        "implication": "Trade measures can raise input costs or limit market access; companies with global supply chains are most exposed.",
        "watch": "Which products or countries are covered, exemptions, and management's mitigation plans.",
    },
    {
        "topic": "Interest rates or inflation",
        "direction": "mixed",
        "keywords": ["interest rate", "interest rates", "rate hike", "rate cut", "federal reserve", "the fed", "fed ", "inflation", "cpi", "treasury yields"],
        "implication": "Rate and inflation shifts change borrowing costs and valuations; growth stocks and rate-sensitive sectors tend to react most.",
        "watch": "The next central-bank decision, inflation prints, and the company's debt maturity profile.",
    },
    {
        "topic": "AI or technology investment",
        "direction": "mixed",
        "keywords": ["artificial intelligence", " ai ", "ai chip", "ai chips", "data center", "data centers", "cloud", "semiconductor", "gpu", "gpus"],
        "implication": "AI and infrastructure spending can be a growth driver for suppliers and a cost burden for buyers until returns show up.",
        "watch": "Capital-expenditure guidance, customer demand signals, and margin impact.",
    },
]


def _compile(keywords):
    pats = []
    for k in keywords:
        k = k.strip()
        if k.startswith(" ") or k.endswith(" "):
            pats.append(re.compile(re.escape(k.strip()).join((r"(?<![a-z])", r"(?![a-z])"))))
        else:
            pats.append(re.compile(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])"))
    return pats


for _rule in RULES:
    _rule["_patterns"] = list(zip(_rule["keywords"], _compile(_rule["keywords"])))


def find_implications(text: str) -> list[dict]:
    """All rules whose keywords appear in `text`, with the matched keywords."""
    low = " " + re.sub(r"\s+", " ", (text or "").lower().replace("-", " ")) + " "
    found = []
    for rule in RULES:
        matched = [kw.strip() for kw, pat in rule["_patterns"] if pat.search(low)]
        if matched:
            found.append(
                {
                    "topic": rule["topic"],
                    "direction": rule["direction"],
                    "matched": sorted(set(matched)),
                    "implication": rule["implication"],
                    "watch": rule["watch"],
                }
            )
    return found


def implications_for_article(article: dict) -> list[dict]:
    text = " . ".join(p for p in (article.get("headline"), article.get("summary")) if p)
    return find_implications(text)

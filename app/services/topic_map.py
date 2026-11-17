"""
app/services/topic_map.py — the keyword -> topic -> sector map behind
"Market developments" (Section C). This file is DATA, written to be read and
edited: change a keyword or a sector line here and the page follows. The
matching logic lives in market_news.py.

Everything below is MarketMind's rule-based INTERPRETATION, shown on the page
with that label. It describes how a kind of news *could* affect sectors in
general (textbook relationships), never what a stock will do, and never a
recommendation. Example companies only illustrate a sector.

How a topic is used
-------------------
keywords   An article belongs to the topic if a keyword is in its headline,
           or two different keywords are in its summary.
exclude    Phrases removed before matching (so "trade war" isn't counted as
           geopolitical "war").
scenarios  Two opposite directions (rates falling vs rising, ...). Each has
           `phrases` that signal it, and the sectors that could see
           potential positive or negative implications in that direction.
           If coverage clearly leans one way, the page leads with that
           scenario; otherwise it shows both.
"""

# ---------------------------------------------------------------------------
# Building blocks for direction phrases.
# moves(["oil"], "up") -> ["oil rises", "oil jumps", ..., "rising oil", "higher oil", ...]
# ---------------------------------------------------------------------------
UP_VERBS = ["rise", "rises", "rose", "climb", "climbs", "climbed", "jump", "jumps", "jumped",
            "surge", "surges", "surged", "gain", "gains", "gained", "rally", "rallies", "rallied",
            "soar", "soars", "soared", "increase", "increases", "increased", "higher",
            "accelerate", "accelerates", "accelerated", "rebound", "rebounds", "rebounded", "beat", "beats"]
DOWN_VERBS = ["fall", "falls", "fell", "drop", "drops", "dropped", "slip", "slips", "slipped",
              "slide", "slides", "slid", "sink", "sinks", "sank", "tumble", "tumbles", "tumbled",
              "plunge", "plunges", "plunged", "decline", "declines", "declined", "decrease", "decreases",
              "lower", "slow", "slows", "slowed", "cool", "cools", "cooled", "ease", "eases", "eased",
              "weaken", "weakens", "weakened", "miss", "misses", "missed"]
# Adjectives that come BEFORE the subject: "rising oil prices", "lower rates".
UP_ADJ = ["rising", "higher", "soaring", "surging", "climbing", "accelerating"]
DOWN_ADJ = ["falling", "lower", "sinking", "slumping", "easing", "cooling", "declining", "slowing"]


def moves(subjects, direction):
    """Every phrase saying a subject moved up or down, in both word orders:
    moves(["oil"], "up") -> ["oil rises", ..., "rising oil", ...]."""
    verbs, adjectives = (UP_VERBS, UP_ADJ) if direction == "up" else (DOWN_VERBS, DOWN_ADJ)
    return [f"{s} {v}" for s in subjects for v in verbs] + [f"{a} {s}" for s in subjects for a in adjectives]


# ---------------------------------------------------------------------------
# Sectors (the 11 standard market sectors) and example companies.
# Ticker: (name, sector, aliases used to spot the company in news text)
# ---------------------------------------------------------------------------
SECTORS = [
    "Technology", "Communication Services", "Consumer Discretionary", "Consumer Staples",
    "Energy", "Financials", "Healthcare", "Industrials", "Materials", "Real Estate", "Utilities",
]

COMPANIES = {
    "AAPL": ("Apple", "Technology", ["apple"]),
    "MSFT": ("Microsoft", "Technology", ["microsoft"]),
    "NVDA": ("NVIDIA", "Technology", ["nvidia"]),
    "AMD": ("Advanced Micro Devices", "Technology", ["amd", "advanced micro devices"]),
    "AVGO": ("Broadcom", "Technology", ["broadcom"]),
    "GOOGL": ("Alphabet", "Communication Services", ["alphabet", "google"]),
    "META": ("Meta Platforms", "Communication Services", ["meta platforms", "facebook"]),
    "AMZN": ("Amazon", "Consumer Discretionary", ["amazon"]),
    "HD": ("Home Depot", "Consumer Discretionary", ["home depot"]),
    "NKE": ("Nike", "Consumer Discretionary", ["nike"]),
    "GM": ("General Motors", "Consumer Discretionary", ["general motors"]),
    "F": ("Ford Motor", "Consumer Discretionary", ["ford motor"]),
    "DHI": ("D.R. Horton", "Consumer Discretionary", ["d.r. horton", "dr horton"]),
    "LEN": ("Lennar", "Consumer Discretionary", ["lennar"]),
    "BKNG": ("Booking Holdings", "Consumer Discretionary", ["booking holdings"]),
    "PG": ("Procter & Gamble", "Consumer Staples", ["procter & gamble", "procter and gamble"]),
    "KO": ("Coca-Cola", "Consumer Staples", ["coca cola"]),
    "WMT": ("Walmart", "Consumer Staples", ["walmart"]),
    "XOM": ("Exxon Mobil", "Energy", ["exxon", "exxonmobil"]),
    "CVX": ("Chevron", "Energy", ["chevron"]),
    "COP": ("ConocoPhillips", "Energy", ["conocophillips"]),
    "JPM": ("JPMorgan Chase", "Financials", ["jpmorgan"]),
    "BAC": ("Bank of America", "Financials", ["bank of america"]),
    "JNJ": ("Johnson & Johnson", "Healthcare", ["johnson & johnson", "johnson and johnson"]),
    "CAT": ("Caterpillar", "Industrials", ["caterpillar"]),
    "UNP": ("Union Pacific", "Industrials", ["union pacific"]),
    "BA": ("Boeing", "Industrials", ["boeing"]),
    "DAL": ("Delta Air Lines", "Industrials", ["delta air lines", "delta airlines"]),
    "UAL": ("United Airlines", "Industrials", ["united airlines"]),
    "UPS": ("United Parcel Service", "Industrials", ["united parcel service"]),
    "LMT": ("Lockheed Martin", "Industrials", ["lockheed"]),
    "RTX": ("RTX", "Industrials", ["rtx", "raytheon"]),
    "NOC": ("Northrop Grumman", "Industrials", ["northrop"]),
    "LIN": ("Linde", "Materials", ["linde"]),
    "FCX": ("Freeport-McMoRan", "Materials", ["freeport mcmoran"]),
    "NUE": ("Nucor", "Materials", ["nucor"]),
    "STLD": ("Steel Dynamics", "Materials", ["steel dynamics"]),
    "DOW": ("Dow Inc.", "Materials", ["dow inc", "dow chemical"]),
    "NEM": ("Newmont", "Materials", ["newmont"]),
    "PLD": ("Prologis", "Real Estate", ["prologis"]),
    "O": ("Realty Income", "Real Estate", ["realty income"]),
    "EQIX": ("Equinix", "Real Estate", ["equinix"]),
    "DLR": ("Digital Realty", "Real Estate", ["digital realty"]),
    "NEE": ("NextEra Energy", "Utilities", ["nextera"]),
    "DUK": ("Duke Energy", "Utilities", ["duke energy"]),
}

# Used by the earnings topic: its sector lines are filled in from the
# companies actually named in the coverage.
READ_THROUGH = "Same industry as the reporting company"

# ---------------------------------------------------------------------------
# The eight topics. Sector lines: (sector, why it could be affected, examples)
# ---------------------------------------------------------------------------
TOPICS = [
    {
        "key": "rates",
        "name": "Interest rates & central banks",
        "why": ("Interest rates set what companies and households pay to borrow and how much investors "
                "will pay today for profits expected later. Housing is one of the most rate-sensitive "
                "parts of the economy, so housing news is grouped here too."),
        "keywords": ["federal reserve", "fed", "the fed", "fed's", "fed chair", "fomc", "central bank", "central banks",
                     "interest rate", "interest rates", "rate cut", "rate cuts", "rate hike", "rate hikes",
                     "monetary policy", "treasury yield", "treasury yields", "bond yield", "bond yields",
                     "borrowing costs", "mortgage", "mortgages", "mortgage rates", "housing market",
                     "home sales", "homebuilder", "homebuilders", "housing starts"],
        # "fed" is also a verb ("fed into", "fed up"); those uses are removed before matching.
        "exclude": ["fed up", "fed into", "fed by", "fed through", "fed on", "well fed", "spoon fed", "fed back"],
        "scenarios": [
            {
                "key": "easing", "label": "Rates falling (easing)",
                "phrases": ["rate cut", "rate cuts", "cuts rates", "cut rates", "cutting rates", "lowers rates",
                            "dovish", "easing cycle"]
                           + moves(["rates", "interest rates", "yields", "treasury yields", "bond yields", "mortgage rates", "borrowing costs"], "down"),
                "positive": [
                    ("Real Estate", "Cheaper financing can support property values and landlords' borrowing.", ["PLD", "O"]),
                    ("Utilities", "Debt-heavy businesses; their dividends look more attractive when bond yields fall.", ["NEE", "DUK"]),
                    ("Consumer Discretionary", "Cheaper mortgages and car loans support big purchases; homebuilders are especially sensitive.", ["DHI", "LEN", "HD"]),
                    ("Technology", "Profits expected far in the future are worth more today when rates are lower.", ["MSFT", "NVDA"]),
                ],
                "negative": [
                    ("Financials", "Banks can earn less on the gap between what they charge borrowers and pay depositors.", ["JPM", "BAC"]),
                ],
            },
            {
                "key": "tightening", "label": "Rates rising (tightening)",
                "phrases": ["rate hike", "rate hikes", "raises rates", "raise rates", "hiking rates", "hawkish",
                            "higher for longer", "tightening"]
                           + moves(["rates", "interest rates", "yields", "treasury yields", "bond yields", "mortgage rates", "borrowing costs"], "up"),
                "positive": [
                    ("Financials", "Banks can earn more on loans, though sharp increases can hurt borrowers and bond holdings.", ["JPM", "BAC"]),
                ],
                "negative": [
                    ("Real Estate", "Higher financing costs can weigh on property values.", ["PLD", "O"]),
                    ("Utilities", "Borrowing costs rise, and bonds compete with their dividends.", ["NEE", "DUK"]),
                    ("Consumer Discretionary", "Pricier mortgages and loans can slow big purchases and home building.", ["DHI", "LEN", "HD"]),
                    ("Technology", "Profits expected far in the future are discounted more heavily.", ["MSFT", "NVDA"]),
                ],
            },
        ],
        "monitor": ["The next central-bank rate decision and statement", "Inflation and jobs reports",
                    "The 10-year Treasury yield", "Mortgage rates and home sales"],
    },
    {
        "key": "inflation",
        "name": "Inflation",
        "why": ("Inflation changes what consumers can afford and what companies pay for materials and wages, "
                "and it is the main input to central banks' interest-rate decisions."),
        "keywords": ["inflation", "consumer prices", "cpi", "pce", "price index", "cost of living",
                     "disinflation", "deflation", "producer prices", "price pressures"],
        "scenarios": [
            {
                "key": "heating", "label": "Inflation heating up",
                "phrases": ["hotter than expected", "sticky inflation", "price pressures build", "inflation picks up"]
                           + moves(["inflation", "consumer prices", "prices", "cpi", "core inflation"], "up"),
                "positive": [
                    ("Energy", "Commodity producers can sell what they produce at higher prices.", ["XOM", "CVX"]),
                    ("Materials", "Raw-material producers often pass higher prices through.", ["LIN", "FCX", "NUE"]),
                ],
                "negative": [
                    ("Consumer Discretionary", "Stretched budgets leave less for non-essential purchases.", ["AMZN", "NKE"]),
                    ("Technology", "Persistent inflation can mean higher rates, which weigh on growth-stock valuations.", ["MSFT", "NVDA"]),
                    ("Real Estate", "Higher expected rates raise financing costs.", ["PLD", "O"]),
                ],
            },
            {
                "key": "cooling", "label": "Inflation cooling",
                "phrases": ["cooler than expected", "softer than expected", "disinflation", "price pressures ease"]
                           + moves(["inflation", "consumer prices", "prices", "cpi", "core inflation"], "down"),
                "positive": [
                    ("Consumer Discretionary", "Easing prices leave consumers more room to spend.", ["AMZN", "NKE"]),
                    ("Technology", "Cooler inflation can open the door to lower rates.", ["MSFT", "NVDA"]),
                    ("Real Estate", "Lower expected rates ease financing costs.", ["PLD", "O"]),
                ],
                "negative": [
                    ("Energy", "Falling prices can squeeze commodity producers' revenue.", ["XOM", "CVX"]),
                    ("Materials", "Weaker pricing power for raw-material producers.", ["LIN", "FCX", "NUE"]),
                ],
            },
        ],
        "monitor": ["The next CPI and PCE inflation reports", "Wage growth", "Energy and food prices",
                    "Central-bank comments on inflation"],
    },
    {
        "key": "jobs",
        "name": "Jobs & consumer spending",
        "why": ("Paychecks fund consumer spending, the largest part of the U.S. economy, so job and spending "
                "data signal where company sales, and interest rates, may head."),
        "keywords": ["jobs report", "payrolls", "nonfarm", "unemployment", "jobless claims", "labor market",
                     "hiring", "layoffs", "job cuts", "job openings", "wage growth", "retail sales",
                     "consumer spending", "consumer confidence", "consumer sentiment"],
        "scenarios": [
            {
                "key": "strengthening", "label": "Jobs and spending strengthening",
                "phrases": ["unemployment falls", "unemployment fell", "jobless claims fall", "jobless claims fell",
                            "strong hiring", "hiring picks up"]
                           + moves(["payrolls", "hiring", "job growth", "retail sales", "consumer spending",
                                    "consumer confidence", "consumer sentiment", "wages"], "up"),
                "positive": [
                    ("Consumer Discretionary", "More income can mean more spending on non-essentials.", ["AMZN", "HD"]),
                    ("Financials", "More borrowing and fewer loan defaults.", ["JPM", "BAC"]),
                    ("Industrials", "A busier economy moves and builds more.", ["CAT", "UNP"]),
                ],
                "negative": [
                    ("Real Estate", "A hot job market can keep interest rates higher for longer.", ["PLD", "O"]),
                    ("Utilities", "Higher-for-longer rates weigh on rate-sensitive sectors.", ["NEE", "DUK"]),
                ],
            },
            {
                "key": "weakening", "label": "Jobs and spending weakening",
                "phrases": ["layoffs", "job cuts", "cuts jobs", "cut jobs", "unemployment rises", "unemployment rose",
                            "jobless claims rise", "jobless claims rose"]
                           + moves(["payrolls", "hiring", "job growth", "retail sales", "consumer spending",
                                    "consumer confidence", "consumer sentiment"], "down"),
                "positive": [
                    ("Consumer Staples", "Everyday essentials tend to hold up when budgets tighten.", ["PG", "KO", "WMT"]),
                    ("Healthcare", "Demand for healthcare changes little with the economy.", ["JNJ"]),
                    ("Utilities", "Weaker data can make interest-rate cuts more likely.", ["NEE", "DUK"]),
                ],
                "negative": [
                    ("Consumer Discretionary", "Households cut back on non-essential purchases first.", ["AMZN", "HD"]),
                    ("Financials", "Loan defaults tend to rise when unemployment rises.", ["JPM", "BAC"]),
                    ("Industrials", "Slower activity means fewer goods to make and move.", ["CAT", "UNP"]),
                ],
            },
        ],
        "monitor": ["The monthly jobs report", "Weekly jobless claims", "Retail sales and consumer confidence",
                    "Company layoff and hiring announcements"],
    },
    {
        "key": "trade",
        "name": "Tariffs & trade",
        "why": ("Tariffs are taxes on imported goods. They raise costs for companies that import parts or "
                "products, can shield some domestic producers, and can trigger retaliation against exporters."),
        "keywords": ["tariff", "tariffs", "trade war", "trade deal", "trade talks", "trade agreement",
                     "trade tensions", "export controls", "export ban", "export restrictions", "import duties",
                     "trade deficit", "retaliatory", "customs duties"],
        "scenarios": [
            {
                "key": "rising", "label": "Trade barriers rising",
                "phrases": ["new tariffs", "raises tariffs", "tariff hike", "tariff hikes", "imposes tariffs",
                            "higher tariffs", "trade war", "export controls", "export ban", "export restrictions",
                            "retaliatory", "retaliation", "trade tensions"],
                "positive": [
                    ("Materials", "Domestic steel and metals producers can face less foreign competition.", ["NUE", "STLD"]),
                ],
                "negative": [
                    ("Consumer Discretionary", "Importers of finished goods and car parts pay more.", ["NKE", "GM", "F"]),
                    ("Technology", "Chip export limits and pricier components hit global supply chains.", ["NVDA", "AMD", "AAPL"]),
                    ("Industrials", "Exporters can face retaliation, and imported inputs cost more.", ["CAT", "BA"]),
                ],
            },
            {
                "key": "easing", "label": "Trade barriers easing",
                "phrases": ["trade deal", "trade agreement", "trade truce", "tariff cut", "tariff cuts", "cuts tariffs",
                            "lifts tariffs", "lowers tariffs", "tariff exemption", "tariff exemptions", "eases tariffs",
                            "delays tariffs", "pauses tariffs"],
                "positive": [
                    ("Consumer Discretionary", "Lower import costs for finished goods and car parts.", ["NKE", "GM", "F"]),
                    ("Technology", "Smoother supply chains and access to more markets.", ["NVDA", "AMD", "AAPL"]),
                    ("Industrials", "Exporters regain access to markets; inputs cost less.", ["CAT", "BA"]),
                ],
                "negative": [
                    ("Materials", "Domestic metals producers face more foreign competition.", ["NUE", "STLD"]),
                ],
            },
        ],
        "monitor": ["Announced tariff rates and start dates", "Exemptions and retaliation by trading partners",
                    "Company comments on costs and prices"],
    },
    {
        "key": "energy",
        "name": "Oil & commodities",
        "why": ("Energy is a cost for almost every business. Oil and gas prices move producers' profits and the "
                "costs of airlines, shippers, chemical makers, and drivers. Metals such as gold and copper are "
                "grouped here too; their moves matter most for miners."),
        "keywords": ["oil", "crude", "brent", "wti", "opec", "natural gas", "gasoline", "diesel", "lng",
                     "barrel", "refinery", "tanker", "tankers", "gold", "copper", "commodities", "commodity"],
        "scenarios": [
            {
                "key": "rising", "label": "Energy prices rising",
                "phrases": ["opec cut", "opec cuts", "output cut", "output cuts", "supply disruption",
                            "supply disruptions", "tanker attack", "tanker attacks"]
                           + moves(["oil", "oil prices", "crude", "crude prices", "brent", "wti", "gas prices",
                                    "gasoline prices"], "up"),
                "positive": [
                    ("Energy", "Producers earn more for each barrel they sell.", ["XOM", "CVX", "COP"]),
                ],
                "negative": [
                    ("Industrials", "Airlines and shippers pay more for fuel.", ["DAL", "UAL", "UPS"]),
                    ("Materials", "Chemical makers pay more for oil-based raw materials.", ["DOW"]),
                    ("Consumer Discretionary", "Higher fuel bills leave less for other spending.", ["AMZN", "HD"]),
                ],
            },
            {
                "key": "falling", "label": "Energy prices falling",
                "phrases": ["oversupply", "supply glut", "output increase", "raises output", "boosts output",
                            "output hike"]
                           + moves(["oil", "oil prices", "crude", "crude prices", "brent", "wti", "gas prices",
                                    "gasoline prices"], "down"),
                "positive": [
                    ("Industrials", "Lower fuel costs for airlines and shippers.", ["DAL", "UAL", "UPS"]),
                    ("Materials", "Cheaper oil-based raw materials for chemical makers.", ["DOW"]),
                    ("Consumer Discretionary", "Lower fuel bills free up spending.", ["AMZN", "HD"]),
                ],
                "negative": [
                    ("Energy", "Producers earn less for each barrel they sell.", ["XOM", "CVX", "COP"]),
                ],
            },
        ],
        "monitor": ["OPEC+ production decisions", "Weekly U.S. crude inventory data",
                    "Disruptions on major shipping routes", "Gasoline prices"],
    },
    {
        "key": "earnings",
        "name": "Corporate earnings",
        "why": ("Earnings show whether companies are growing their profits. Results and forecasts from large "
                "companies can move their whole industry, because investors read them as signals for peers."),
        "keywords": ["earnings", "quarterly results", "quarterly profit", "quarterly revenue", "quarterly",
                     "guidance", "beat estimates", "beats estimates", "missed estimates", "misses estimates",
                     "profit warning", "earnings call", "revenue forecast", "profit forecast", "sales forecast",
                     "results"],
        "exclude": ["election results", "poll results", "test results", "trial results", "search results"],
        "read_through": True,
        "scenarios": [
            {
                "key": "strong", "label": "Results beating expectations",
                "phrases": ["beat estimates", "beats estimates", "tops estimates", "topped estimates",
                            "record profit", "record revenue", "raises guidance", "raised guidance",
                            "raises forecast", "raised forecast"]
                           + moves(["profit", "profits", "revenue", "sales", "earnings"], "up"),
                "positive": [(READ_THROUGH, "Strong results can lift peers that serve similar customers.", [])],
                "negative": [],
            },
            {
                "key": "weak", "label": "Results missing expectations",
                "phrases": ["missed estimates", "misses estimates", "profit warning", "cuts guidance", "cut guidance",
                            "lowers guidance", "cuts forecast", "lowers forecast"]
                           + moves(["profit", "profits", "revenue", "sales", "earnings"], "down"),
                "positive": [],
                "negative": [(READ_THROUGH, "Weak results can raise doubts about peers in the same industry.", [])],
            },
        ],
        "monitor": ["Revenue and profit versus analyst expectations", "Guidance for the next quarter",
                    "Comments on demand, costs, and margins", "How competitors' shares react"],
    },
    {
        "key": "tech_ai",
        "name": "Technology & AI",
        "why": ("Spending on artificial intelligence, chips, and data centers is one of the largest investment "
                "themes in markets. It drives demand for semiconductors, cloud services, and electricity."),
        "keywords": ["artificial intelligence", "ai", "chip", "chips", "chipmaker", "chipmakers", "semiconductor",
                     "semiconductors", "data center", "data centers", "gpu", "gpus", "cloud computing",
                     "cloud services", "hyperscaler", "hyperscalers", "ai model", "ai models"],
        "scenarios": [
            {
                "key": "growing", "label": "AI and chip demand growing",
                "phrases": ["ai boom", "record demand", "raises capex", "new data center", "builds data center",
                            "expands data center"]
                           + moves(["ai spending", "ai investment", "chip demand", "chip sales", "capex",
                                    "capital spending", "cloud revenue", "ai demand"], "up"),
                "positive": [
                    ("Technology", "Chipmakers and cloud providers sell more.", ["NVDA", "AMD", "AVGO", "MSFT"]),
                    ("Utilities", "Data centers need large amounts of electricity.", ["NEE", "DUK"]),
                    ("Real Estate", "Data-center landlords lease more space.", ["EQIX", "DLR"]),
                ],
                "negative": [
                    ("Communication Services", "Heavy AI spending can squeeze profit margins until it pays off.", ["META", "GOOGL"]),
                ],
            },
            {
                "key": "cooling", "label": "AI and chip demand cooling",
                "phrases": ["ai bubble", "capex cuts", "spending cuts", "chip glut", "export controls", "export ban",
                            "export restrictions", "tech selloff", "tech sell off"]
                           + moves(["ai spending", "ai investment", "chip demand", "chip sales", "capex",
                                    "capital spending", "cloud revenue", "ai demand", "ai stocks", "chip stocks",
                                    "tech stocks"], "down"),
                "positive": [
                    ("Consumer Staples", "Investors sometimes shift toward steadier businesses when tech enthusiasm cools.", ["PG", "KO"]),
                ],
                "negative": [
                    ("Technology", "Chipmakers and cloud providers could see slower orders.", ["NVDA", "AMD", "AVGO", "MSFT"]),
                    ("Utilities", "Less expected electricity demand from data centers.", ["NEE", "DUK"]),
                    ("Real Estate", "Slower leasing for data-center landlords.", ["EQIX", "DLR"]),
                ],
            },
        ],
        "monitor": ["AI spending plans of the largest tech companies", "Chipmaker earnings and order backlogs",
                    "Export rules for advanced chips", "Power-grid and data-center construction news"],
    },
    {
        "key": "geopolitics",
        "name": "Geopolitics & conflict",
        "why": ("Conflicts, sanctions, and diplomacy can disrupt energy supplies and shipping, change defense "
                "spending, and push investors toward assets they see as safer, such as gold."),
        "keywords": ["geopolitical", "military", "missile", "missiles", "sanctions", "ceasefire", "invasion",
                     "troops", "airstrike", "airstrikes", "armed conflict", "drone attack", "drone attacks",
                     "attack", "attacks", "attacked", "war", "warship", "warships", "militia", "militias"],
        "exclude": ["trade war", "trade wars", "price war", "bidding war", "culture war", "war chest",
                    "talent war", "star wars", "heart attack", "cyber attack", "cyberattack"],
        "scenarios": [
            {
                "key": "rising", "label": "Tensions rising",
                "phrases": ["attack", "attacks", "attacked", "escalation", "escalates", "escalating", "airstrike",
                            "airstrikes", "missile strike", "missile strikes", "drone attack", "drone attacks",
                            "invasion", "new sanctions", "imposes sanctions", "threatens", "plot", "military buildup"],
                "positive": [
                    ("Industrials", "Defense contractors can see more orders.", ["LMT", "RTX", "NOC"]),
                    ("Energy", "Supply fears can lift oil prices.", ["XOM", "CVX"]),
                    ("Materials", "Gold miners can benefit when investors seek safe havens.", ["NEM"]),
                ],
                "negative": [
                    ("Industrials", "Airlines face higher fuel costs and travel disruptions.", ["DAL", "UAL"]),
                    ("Consumer Discretionary", "Travel and global consumer demand can weaken.", ["BKNG"]),
                    ("Technology", "Global supply chains can be disrupted.", ["AAPL"]),
                ],
            },
            {
                "key": "easing", "label": "Tensions easing",
                "phrases": ["ceasefire", "truce", "peace talks", "peace deal", "peace agreement", "de escalation",
                            "lifts sanctions", "sanctions lifted", "eases sanctions", "talks resume"],
                "positive": [
                    ("Industrials", "Airlines benefit from steadier fuel costs and travel.", ["DAL", "UAL"]),
                    ("Consumer Discretionary", "Travel and global demand can recover.", ["BKNG"]),
                    ("Technology", "Fewer supply-chain disruptions.", ["AAPL"]),
                ],
                "negative": [
                    ("Industrials", "Defense contractors may see less urgency in orders.", ["LMT", "RTX", "NOC"]),
                    ("Energy", "Easing supply fears can lower oil prices.", ["XOM", "CVX"]),
                    ("Materials", "Less demand for safe havens such as gold.", ["NEM"]),
                ],
            },
        ],
        "monitor": ["Developments in active conflicts and peace talks", "New sanctions or export restrictions",
                    "Oil prices and shipping routes", "Defense budgets"],
    },
]

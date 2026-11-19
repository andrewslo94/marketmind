# MarketMind — Complete Project Guide for Claude Code

ROLE: Act as my lead Python developer, fintech software architect, Python instructor, and project manager for this entire project. Treat it as a real fintech startup product, not a simple school assignment — but keep the scope realistic for a solo student with a December deadline.

---

## 1. About me and my situation
- Solo student, INFO SYS 201 – AI in Business capstone. The "AI" part of the course is **using AI (you) to help build Python code**. The app itself does **NOT** use an AI API (no OpenAI/Claude/Gemini calls).
- I understand basic Python but I'm not an advanced programmer. When you introduce a new Python concept, briefly explain what it does and why we need it.
- I'm on a **Mac**, using **VS Code** with its integrated terminal. Use `python3` before the virtual environment is active; `python` once `(.venv)` is active.
- **Deadline: final demo in early-to-mid December 2026** (exact date TBD — I'll update this line).
- I want to understand how everything works so I can confidently demo it to my professor and explain it in my professional portfolio.
- GitHub for version control. (As of 2026-11-12: git 2.54 is installed, but I don't have a GitHub account yet — set it up during Phase 1.)

## 2. How to work with me (very important)
1. Work on **one phase (or sub-part) at a time**. Do not rush ahead before the current step works.
2. **Create or change no more than ~4–5 files per step.** Then stop.
3. After each step, tell me:
   - FILES: which files were created/changed, and whether a file was replaced entirely or only a section changed.
   - PURPOSE: what each file does and how the files connect.
   - HOW TO RUN: exact terminal command(s).
   - HOW TO TEST: exactly what to do and what I should see.
   - POTENTIAL ERRORS: common problems and fixes.
4. **Wait for me to confirm testing succeeded** before moving to the next step or phase.
5. **Ask before** installing packages, deleting files, or restructuring. After installs, update `requirements.txt` with `pip freeze > requirements.txt`.
6. Never assume I already have a package, API key, database, or tool installed. Don't skip setup steps.
7. When I report an error, use the actual error message to identify the cause and fix that specifically — don't rewrite everything.
8. Avoid unnecessary complexity. Use clean, organized, reusable, commented Python.
9. If you need information from me, ask direct questions rather than making major assumptions.
10. After each completed step, append an entry to `DEVLOG.md`: date, what we built, problems encountered, how we fixed them. (I'll use this to present how I used AI to build the app.)
11. At the end of each working step, suggest a git commit with a clear message.
12. Keep the "Current status" section at the bottom of this file updated.

## 3. Non-negotiable quality and safety rules
- **Never invent data.** No made-up prices, news articles, financial statements, or market statistics. If data is unavailable, show a clear "Data unavailable" message.
- Clearly label any sample/placeholder content and distinguish it from real functionality.
- **No buttons or features that look functional but do nothing.**
- Every price shows a **timestamp** and a market-hours/**"Delayed data"** label. Never claim real-time unless the provider's plan and documentation confirm it. Clearly disclose API limitations in the UI.
- Visually separate **verified facts** (headlines, sources, numbers) from **analytical interpretation** (sentiment, sector impact, explanations). Interpretation must be labeled as such.
- Never tell users to buy or sell. Present research, evidence, risks, and educational insights.
- Security: hash passwords (Werkzeug), keep secrets only in `.env` (never hardcoded, never committed), validate all user input, users can only access their own data.
- Include error handling and data validation throughout.
- Cache all external API calls so we don't hit rate limits (especially during the demo).
- The app should look like a professional, modern fintech product — easy to navigate, reasonably responsive, and structured so it could be expanded commercially.

## 4. Tech stack (decided)
| Layer | Choice |
|---|---|
| Language | Python |
| Backend | Flask (application factory + blueprints) |
| Database | SQLite via Flask-SQLAlchemy (DB file in `instance/`); designed so switching to PostgreSQL is a config change |
| Auth | Flask-Login + Werkzeug password hashing |
| Frontend | Jinja templates, HTML/CSS/JS, Bootstrap 5, dark professional fintech theme |
| Data analysis | pandas |
| Charts | Plotly (interactive) |
| Prices, history, market cap, 52-wk range | yfinance — unofficial, undocumented rate limits → cache aggressively, always label delayed |
| Backup quotes + company/market news | Finnhub free tier (API key; personal/non-commercial use) |
| Company fundamentals | **Hybrid (decided 2026-11-19):** Financial Modeling Prep free tier where it covers the company (fixed free symbol list: 31 of our 64), otherwise Yahoo Finance statements via yfinance. MarketMind computes every ratio from raw statement figures with one set of formulas (cross-checked identical across providers; debt can differ a few % from lease accounting); the source is shown per company. FMP: 250 requests/day, key sent in an `apikey` header. |
| Economic indicators (yields, CPI, unemployment, Fed funds) | FRED (free API key) |
| Sentiment & summaries | Rule-based NLP, **no AI API**: VADER sentiment + a finance-specific keyword list; extractive summaries from the article's own sentences. Show *why* each label was assigned (matched keywords). |

When we connect each external API, explain: what it does, why we need it, free vs paid, its limitations, how to get a key, how to store it securely in `.env`, and how it connects to the app. Verify current free-tier limits on the provider's official site at that time.

App runs on **port 5001** (macOS uses 5000 for AirPlay).

## 5. Architecture and folder structure (target)
```
marketmind/
├── run.py               # starts the app
├── config.py            # settings, loads .env
├── requirements.txt
├── .env                 # secrets — never committed
├── .gitignore
├── CLAUDE.md            # this file
├── DEVLOG.md            # development log
├── README.md
├── app/
│   ├── __init__.py      # create_app() factory
│   ├── extensions.py    # db, login_manager
│   ├── models.py        # database tables
│   ├── routes/          # main, auth, portfolio, stocks, news, market, research, insights
│   ├── services/        # market_data, news_service, sentiment, portfolio_calc, scoring, cache
│   ├── templates/
│   └── static/          # css/, js/
├── data/                # curated stock universe CSV (ticker, name, sector, industry)
├── instance/            # SQLite DB (git-ignored)
└── tests/
```
Principle: **routes** handle pages/URLs; **services** handle data fetching, calculations, and logic. Routes never call external APIs directly.

## 6. Application features

### Section A — Personal Investment Portfolio
Users create an account and enter investments they own.
- Add stocks by ticker symbol (validate the ticker exists), number of shares, average purchase price, optional purchase date.
- Edit or remove holdings. Multiple stocks per portfolio.

Portfolio dashboard calculates and displays:
- Total portfolio value, total amount invested, total unrealized profit/loss, overall % return, daily portfolio gain/loss, individual stock performance, allocation by investment (chart).

Individual stock pages display:
- Current price, previous close, open, daily high/low, daily % change, trading volume, market cap, 52-week high/low, historical price chart.
- Chart filters: 1D, 1W, 1M, 3M, 6M, 1Y, 5Y, Max.
- Clear delayed-data label and timestamp.

### Section B — Personalized Investment News
Automatically collect news related to stocks in the user's portfolio. For each article show:
- Headline, publisher, publication date/time, related company and ticker, article link.
- Extractive summary (concise but informative), clearly labeled as auto-generated from the article text.
- Sentiment (positive / negative / neutral) with the reason (matched keywords).
- Potential implications for the company/stock — rule-based and labeled as interpretation.

Filters: ticker, company, date, news category, sentiment.
Never invent articles or present generated text as verified reporting.

### Section C — Global Market Intelligence
Three areas:
1. **Global Financial News** — important developments affecting markets.
2. **Sector Impact Analysis** — how developments could affect sectors (technology, financials, healthcare, energy, utilities, industrials, consumer discretionary, etc.).
3. **Market Overview** — major indexes, market performance, Treasury yields, commodities (oil, gold), key economic indicators (from FRED).

Topic detection is rule-based (keyword → topic → affected sectors/companies map that we write together). Scoped for the deadline to **6–8 topics**: interest rates/Fed, inflation, employment, tariffs/trade, oil & commodities, corporate earnings (add regulation, geopolitics, technology if time allows).

For each major development, show (facts vs interpretation clearly separated):
- What happened? (fact: headline, source, date)
- Why does it matter?
- Which industries could be affected?
- Which individual companies could be affected?
- Potential positive implications / potential negative implications
- What should investors monitor next?

### Section D — Investment Research Engine (the differentiator)
Identify companies the user does **not** own that may be worth researching based on current developments, industry trends, fundamentals, and market conditions. Example: news about AI infrastructure investment → semiconductors, networking, data-center companies.
- Use a curated universe of **~50–75 companies** in `data/` (tagged by sector/industry).

For each opportunity display: company name, ticker, current price + timestamp, why it was identified, related news articles, industry, financial health, valuation info, historical performance, potential growth opportunities, potential risks, and how it relates to current market developments.

**Research Confidence Score** — calculated by transparent Python rules on actual data (never arbitrary):
- Financial health 25% · Industry & market conditions 20% · News & catalysts 20% · Valuation 20% · Historical performance & risk 15%

Display: overall score /100, outlook (positive / neutral / negative), each category score, supporting evidence, key risks, explanation of why it's worth researching.
- State clearly: the score measures the strength of the research case — **not** the probability of profit or a guaranteed return.
- **Diversification check:** if the user already has heavy exposure to that sector, show a concentration-risk warning.
- Never say "buy" or "sell."

### Section E — Insights (replaces an AI chatbot)
A page of built-in questions answered from real app data (portfolio, prices, news, indicators), each listing its sources and data timestamps. Scoped to 3–4 for the deadline:
- "Why is my portfolio up/down today?" (which holdings drove the change, related news)
- "What are the biggest risks / concentration in my portfolio?" (sector exposure)
- "Which of my holdings are most exposed to interest rate changes?" (rule-based sector sensitivity)
- "Compare two stocks" (side-by-side fundamentals)
Answers are generated from templates + calculations — never fabricated.

## 7. Development phases and schedule (solo, ~4 weeks)
| Week | Dates | Work |
|---|---|---|
| 1 | Nov 12–18 | **Phase 1:** venv, packages, folder structure, basic Flask app, base layout/nav/styling, Git + GitHub. **Phase 2:** database + tables, registration/login, user-specific portfolios, test storage/retrieval |
| 2 | Nov 19–25 | **Phase 3:** holdings CRUD, connect yfinance, current + historical prices, caching, portfolio calculations, dashboard, stock pages, Plotly charts, test calculations |
| 3 | Nov 26–Dec 2 (Thanksgiving) | **Phase 4:** news API, company news linked to holdings, summaries, sentiment, filters. Start **Phase 5:** market overview (indexes, yields, commodities, FRED) |
| 4 | Dec 3–9 | Finish **Phase 5** (topic → sector impact). **Phase 6:** research score + opportunities + diversification check. **Phase 7:** Insights page. **Phase 8:** UI polish, full testing, bug fixes, performance, README, demo script, help with presentation |

### Cut for now (future-roadmap slide; only if time remains)
Watchlists, price alerts, earnings calendar, economic events calendar, dividend tracking, historical portfolio performance, paper trading, optional AI-API integration. S&P 500 benchmarking and sector exposure chart are the first to add if time allows.

## 8. Final quality expectations
- Professional fintech-style UI, easy navigation, functional pages and interactive elements.
- Genuine data from reliable sources, accurate calculations, clear data timestamps and delay disclosures.
- Secure accounts and data storage.
- Reliable and reasonably responsive (thanks to caching).
- Organized so it could grow into a commercial product.

## 9. Current status
- **Phase 1 complete (2026-11-12).** 1A: venv, `.env`, config, app factory, `run.py` on port 5001, Flask 3.1.3 + python-dotenv. 1B: `main` blueprint, `base.html` layout (navbar, footer, Bootstrap 5.3.3, dark theme in `static/css/style.css`), new `home.html`. 1C: private GitHub repo `marketmind` published from VS Code; both commits verified online.
- **Phase 2A complete (2026-11-14).** Flask-SQLAlchemy 3.1.1 + Flask-Login 0.6.3 installed. `app/extensions.py` (db, login_manager), `app/models.py` (User table with Werkzeug password hashing + user_loader), `SQLALCHEMY_DATABASE_URI` in `config.py`, `db.create_all()` in the factory. SQLite DB created at `instance/marketmind.db`.
- **Phase 2B complete (2026-11-14).** Flask-WTF 1.3.0 + email-validator. `app/forms.py` (RegistrationForm, LoginForm), `app/routes/auth.py` (/register, /login, POST /logout, safe `next` redirect), `templates/auth/`, navbar login state + flash messages in `base.html`, CSRFProtect enabled. **Phase 2 complete.**
- **Phase 3A complete (2026-11-15).** 2B browser test confirmed. `Holding` model (user_id FK with cascade, ticker, shares, avg_price, purchase_date, notes; unique per user+ticker; `cost_basis` property). `HoldingForm` (format-only ticker check, > 0 amounts, no future dates, duplicate check). `portfolio` blueprint at `/portfolio`: dashboard, add, edit, POST-only delete, all scoped to `current_user`. `money` and `shares` Jinja filters. Nav link shown when logged in. Live-price cards are labeled placeholders.
- **Phase 3B complete (2026-11-15).** yfinance 1.8.0 + pandas 3.1.1 installed. `app/services/cache.py` (`get_or_fetch` → `CacheResult`; memory → `cache_entries` table → provider; stale fallback) and `app/services/market_data.py` (`get_quote`, `get_quotes`, `ticker_exists`, `get_history` with 8 ranges + per-range TTLs, `history_dataframe`; always source + delayed flag + Yahoo quote time). `CacheEntry` model. `HoldingForm` now verifies the ticker exists (EQUITY/ETF only); if the provider is unreachable the holding saves with a warning. Add/edit form looks up the ticker via `GET /portfolio/quote/<ticker>` (JSON) + `static/js/holding_form.js`: shows name + delayed price with timestamp and pre-fills the price box when empty.
- **Phase 3C complete (2026-11-15).** `app/services/portfolio_calc.py` (`build_portfolio` → `PortfolioSummary`/`HoldingRow`; USD-only totals, unpriced + non-USD flagged; `allocation_chart_data`). Dashboard shows live delayed values, P/L, today's change, allocation %, per-row quote times, a provenance banner, and a ranked-bar allocation chart via **plotly.js 3.0.1 from CDN** (no Python plotly package). Filters: `money`, `shares`, `signed_money`, `pct`, `big_number`, `et_time`.
- **Phase 3D complete (2026-11-15). Phase 3 complete.** `stocks` blueprint: `/stocks/<ticker>` detail page (headline price + change, provenance banner, key statistics, "Your position" if held, 404/503 pages) and `/stocks/<ticker>/history.json?range=` (ET timestamps, rounded OHLCV). `static/js/stock_chart.js`: plotly.js line chart with 1D–Max buttons, unified hover, rangebreaks for nights/weekends, period summary. Dashboard tickers link to detail pages. `fromiso` filter added.
- **Phase 4A complete (2026-11-16).** `FINNHUB_API_KEY` in `.env` + `config.py`. `app/services/news_service.py` (`get_company_news` cached 30 min, `get_portfolio_news` merged/de-duplicated with `meta`; `NewsError` for 429/401/network/not-configured). `news` blueprint at `/news` with `?ticker=` quick filter; template with "Verified facts" banner, ticker badges → stock pages, provider summary labeled. Nav link. `.vscode/` git-ignored.
- **Phase 4B complete (2026-11-16).** vaderSentiment 3.3.2 installed. `app/services/sentiment.py`: VADER lexicon extended with a ~170-term finance keyword list (`FINANCE_LEXICON`, -4..+4 scale; multi-word phrases folded into tokens), thresholds ±0.10, `analyze()` / `analyze_article()` return label, compound score, matched terms (the reason), method, text used. News route attaches `article["sentiment"]`; template shows it in a dashed "Interpretation" block separate from the facts, with a banner note.
- **Phase 4C complete (2026-11-16).** `app/services/summarizer.py` (extractive: scored sentences, top 2 in original order, boilerplate skipped, `is_full_text` flag, per-sentence reasons) and `app/services/implications.py` (16 keyword `RULES` → topic, direction, matched keywords, generic implication, watch item; whole-word matching; empty list when nothing matches). News page shows "Auto-summary" and "Potential implications" in the interpretation layer; banner states all three methods.
- **Phase 4D complete (2026-11-16). Phase 4 complete.** `parse_filters` / `filter_articles` / `active_filter_count` in `news_service.py`; GET filter form on `/news` (ticker, company/keyword, date range, category, sentiment), "Showing X of Y", clear-filters state. Filtering is in-memory on the cached list.
- **Phase 5A complete (2026-11-17).** `FRED_API_KEY` in `.env` (verified, not yet used in code). `get_market_quote` (INDEX/FUTURE, `mquote:` cache key) in `market_data.py`. `app/services/market_overview.py` (17 instruments in 4 groups, unit-aware formatting incl. yields in bps, 10y–13wk spread, `index_performance`). `market` blueprint `/market/` + `/market/performance.json`. `static/js/market_chart.js`: % change chart for S&P 500 / Nasdaq / Russell 2000 (3 lines: palette validated all-pairs on `#121826`), conditional end labels, table view. CSS fix: `.table > :not(caption) > * > .mm-gain/.mm-loss` (also fixed dashboard P/L colors). Visual QA via headless Chrome screenshots now possible. Known follow-up: Home page "Planned" badges are outdated (Phase 8).
- **Phase 5B complete (2026-11-17).** `FRED_API_KEY` in `config.py`. `app/services/fred_service.py` (7 series cached 6 h; CPI & core CPI 12-month change, unemployment, payroll change, Fed funds target range + last change, real GDP growth; server-side SVG sparklines with gaps and hover titles; key scrubbed from all errors since FRED requires it in the URL). "U.S. economic indicators" section on `/market/` with the FRED attribution notice required by FRED's terms. Oct 2025 is missing in FRED for CPI/UNRATE (2025 shutdown), so Oct 2026 inflation shows as not calculable with a note.
- **Phase 5C complete (2026-11-17).** `app/services/topic_map.py` (the editable keyword → topic → sector map: 8 topics, two opposite scenarios each with direction phrases and sector effects + example companies, 45 companies), `app/services/market_news.py` (combined-regex classification, direction signal by article counts, companies named, relevance ordering, earnings read-through), `get_market_news()` + shared `_finnhub_get` in `news_service.py`. `/market/developments` page (facts left, dashed interpretation right, full headline feed) with Overview/Developments tabs.
- **Phase 5D complete (2026-11-17). Phase 5 complete.** `YAHOO_TO_SECTOR` + per-topic `live` numbers in `topic_map.py` (45 example companies' sectors verified against Yahoo). `sector_exposure()` in `portfolio_calc.py` (reusable for Phases 6–7). `sector_impact()`, `link_holdings()`, `attach_live_numbers()` in `market_news.py`; a direction now needs ≥ 2 articles (`MIN_LEAN_ARTICLES`). `instrument_row()` / `get_indicator()` lookups. Developments page: sector impact summary, "your portfolio and these developments" panel, related numbers per topic, holdings per topic.
- **Phase 6A complete (2026-11-19).** `FMP_API_KEY` in `.env` + `config.py`. `data/universe.csv` (64 companies, 4–9 per sector; name/sector/industry from Yahoo, all USD reporters; includes all 45 topic-map companies). `app/services/research_data.py`: `load_universe()`, `get_fundamentals()` (FMP → Yahoo fallback on HTTP 402 / limit / no key; normalized 5 annual years; cached 7 days, key `fund:<T>`), `compute_metrics()` (14 metrics by our own formulas, notes when not meaningful; banks JPM/BAC/GS use 5; operating income stored but never scored). `app/cli.py`: `flask --app run refresh-fundamentals [TICKERS]` warms the cache (first full run: 116 FMP calls, 81 s; repeat: 0 calls).
- **Phase 6B complete (2026-11-19).** `app/services/scoring.py`: Research Confidence Score with `BANDS` / `SIGNAL_POINTS` / `WEIGHTS` / `OUTLOOK` tables; health (6 sub-scores; bank set of 3), industry (developments label + 3-month sector momentum), news (sentiment + catalysts, ≥ 3 articles), valuation (ratio/gap vs. the peer **median**; banks vs. banks, flagged as rough), performance (1-yr vs S&P 500, volatility, drawdown). Missing data left out, weights rescale, ≥ 3 categories needed; risks/strengths sentences; `DISCLAIMER`. CLI: `flask --app run research-scores [--explain TICKER]`. Live: 14 Positive / 44 Neutral / 6 Negative.
- **Next: Phase 6C** — `research` blueprint: opportunities page = companies the user does **not** hold, ranked by score, each with "why identified" (strengths + links to current developments for its sector), price + timestamp, category scores, key risks, and a **diversification check** using `sector_exposure()` (warn when the user's exposure to that sector is already heavy). Company research page with the full breakdown (like `--explain`), related news (facts), statements source, and the disclaimer. Scores computed in the CLI batch and cached for the page (page must not trigger 64 Finnhub calls).

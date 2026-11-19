# MarketMind — Development Log

A record of how MarketMind was built with AI assistance (Claude Code).

---

## 2026-11-12 — Phase 1A: Project setup and minimal Flask app

**What we built**
- Created the `marketmind/` project folder and a Python 3.13 virtual environment (`.venv`).
- Created `.env` with a randomly generated `SECRET_KEY` (made with Python's `secrets` module) and a `.gitignore` that keeps `.env`, `.venv/`, and `instance/` out of Git.
- `config.py` loads settings from `.env` using python-dotenv.
- `app/__init__.py` holds the `create_app()` application factory, with a temporary home route.
- `run.py` starts the dev server on port 5001 (macOS reserves port 5000 for AirPlay).
- `app/templates/home.html` is a placeholder home page.

**Problems encountered / fixes**
- CLAUDE.md existed only as pasted text, so it was saved into the new project folder.
- No GitHub account yet. The GitHub setup was moved to a later Phase 1 step.
- The VS Code ▶ Run button runs whichever file is open. With `app/__init__.py` open, nothing started, because that file only defines `create_app()`. Fix: run `run.py`.
- `python run.py` failed because Flask and python-dotenv had never been installed in `.venv` (`pip list` showed only pip). Fix: installed both with `.venv/bin/python -m pip install flask python-dotenv`, then saved versions with `pip freeze > requirements.txt` (Flask 3.1.3, python-dotenv 1.2.4). Checked with Flask's test client: `GET /` returned 200.

---

## 2026-11-12 — Phase 1B: Blueprint, base layout, dark theme

**What we built**
- `app/routes/main.py`: a `main` **blueprint** (a group of routes) holding the home page. `create_app()` now registers blueprints instead of defining routes itself.
- `app/templates/base.html`: a shared layout that every page extends. It has the navbar (collapses on mobile), a content block, and a footer with the disclaimer. It uses Bootstrap 5.3.3 from a CDN with SRI integrity hashes and Bootstrap's built-in dark mode.
- `app/static/css/style.css`: the MarketMind dark fintech theme, built on color tokens (CSS variables).
- `app/templates/home.html` was rewritten to extend `base.html`. It shows a hero, the planned feature sections (each clearly badged "Planned · Phase N", not clickable), and the data-honesty principles.

**Decisions**
- The navbar only links to pages that exist. Future sections appear as clearly labeled "Planned" cards, so there are no buttons that do nothing.

**Testing**
- Flask test client: `/` returns 200 and the Home link is highlighted as active, `/static/css/style.css` returns 200, and an unknown URL returns 404.
- Checked the Bootstrap CDN SRI hashes against the live files. Both match.

---

## 2026-11-12 — Phase 1C: GitHub

**What we did**
- Created a GitHub account and published the repository (private for now) from VS Code using **Publish to GitHub**, which handles sign-in through the browser. No GitHub CLI or Homebrew needed.
- Verified on github.com that `.env` and `.venv/` are not in the repo (kept out by `.gitignore`) and that both Phase 1A and 1B commits are there.

**Notes**
- Found that Phase 1B had not been committed yet (`git status` showed modified and untracked files), so we committed it before publishing.
- From here on, each step ends with `git add .`, `git commit -m "..."`, `git push`.

Phase 1 complete.

---

## 2026-11-14 — Phase 2A: Database and User model

**What we built**
- Installed **Flask-SQLAlchemy 3.1.1** (database ORM) and **Flask-Login 0.6.3** (login sessions). `requirements.txt` updated with `pip freeze`.
- `config.py`: added `SQLALCHEMY_DATABASE_URI`. Defaults to SQLite at `instance/marketmind.db`; a `DATABASE_URL` line in `.env` overrides it, so switching to PostgreSQL later is a config change only.
- `app/extensions.py`: creates the shared `db` and `login_manager` objects. They live in their own module (not in `__init__.py`) to avoid circular imports between the app factory and the models.
- `app/models.py`: the `User` table (id, username, email, password_hash, created_at) with `set_password()` / `check_password()` using Werkzeug hashing, plus the `user_loader` that Flask-Login uses to look up the logged-in user from the session cookie.
- `app/__init__.py`: `create_app()` now calls `db.init_app()`, `login_manager.init_app()`, imports the models, and runs `db.create_all()` so the tables are created on first start.

**Testing**
- Built the app in a script: the `users` table was created in `instance/marketmind.db`. Added a test user, read it back, confirmed the correct password returns True and a wrong one returns False, confirmed Flask-Login's `get_id()` works, then deleted the test user. Home page still returns 200.
- Werkzeug's default hash is scrypt (hash string starts with `scrypt:32768`), so no plain-text passwords are ever stored.

**Notes**
- `instance/` is git-ignored, so the database file never goes to GitHub.

---

## 2026-11-14 — Phase 2B: Registration, login, logout

**What we built**
- Installed **Flask-WTF 1.3.0** (forms + CSRF protection) and **email-validator 2.4.0** (needed by the Email validator). `requirements.txt` updated.
- `app/forms.py`: `RegistrationForm` (username 3–30 chars, letters/numbers/underscore; valid email; password ≥ 8 chars; confirm must match; username and email must be unused) and `LoginForm` (username, password, "keep me logged in").
- `app/routes/auth.py`: the `auth` blueprint with `/register`, `/login`, and `/logout`. Login uses one generic "Invalid username or password" message so the page can't be used to discover which usernames exist. The `?next=` redirect is only followed if it is a relative path on our own site. Logout is POST-only.
- `app/templates/auth/`: `register.html`, `login.html`, and a `_form_field.html` macro that renders a field with its label and error messages (so both pages share one piece of markup).
- `app/templates/base.html`: navbar now shows "Log in / Create account" when logged out and the username + a "Log out" button when logged in. Added a flash-message area above the page content.
- `app/extensions.py` + `app/__init__.py`: added `CSRFProtect`, registered the auth blueprint.
- `style.css`: dark-theme styling for form inputs, the auth card, and the navbar user chip.

**Decisions**
- Flask-WTF instead of hand-written forms, for CSRF protection and declarative validation.
- Emails are stored lowercased so `Demo@Example.com` and `demo@example.com` are the same account.

**Testing (Flask test client)**
- Register/login pages load (200). Bad input shows all three validation errors. Good registration redirects to login with a success flash and stores a scrypt hash, not the password. Duplicate username/email are rejected.
- Wrong password returns 401 with the generic message. Correct login shows the username and Log out button in the navbar. GET /logout is blocked (405); POST logs out; POST while logged out redirects to login.
- A POST without a CSRF token is rejected with 400, and the token is present in the rendered form.

---

## 2026-11-15 — Phase 3A: Holding table and portfolio CRUD (no live prices yet)

**Before starting:** confirmed Phase 2B in the browser (validation errors, registration, duplicate check, bad login, good login, logout). All six steps passed.

**What we built**
- `app/models.py`: new `Holding` table (user_id FK → users with ON DELETE CASCADE, ticker, shares, avg_price, optional purchase_date and notes, created_at/updated_at). A `UniqueConstraint(user_id, ticker)` means one row per stock per user. `cost_basis` is a `@property` (shares × avg price) calculated on the fly, never stored. `user.holdings` / `holding.owner` relationship with cascade delete.
- `app/forms.py`: `HoldingForm`. Ticker is trimmed and upper-cased by a filter, then checked against a regex (1–5 letters, optional `.B`-style suffix). Shares and price use `DecimalField` + `NumberRange` (> 0). `DateField` with `Optional()`; future dates rejected. `validate_ticker` rejects a ticker the user already holds, except the row being edited (`holding_id` passed in).
- `app/routes/portfolio.py`: `portfolio` blueprint at `/portfolio` with dashboard, add, edit, and POST-only delete. Every query filters by `current_user.id`; a helper returns 404 for any holding the user doesn't own. Also registers two app-wide Jinja filters, `money` and `shares`, for consistent number formatting in later phases.
- `app/templates/portfolio/dashboard.html` (summary cards + holdings table + empty state) and `holding_form.html` (shared by add and edit; reuses the `render_field` macro from `auth/`).
- Hookups: blueprint registered in `app/__init__.py`; "Portfolio" nav link in `base.html` shown only when logged in; stat-card and table styles in `style.css`.

**Decisions**
- Ticker *format* only is validated in 3A. Checking that a ticker really exists needs the market-data service, which is 3B.
- "Current value" and "Unrealized P/L" cards are shown as dashed placeholders labeled "Needs live prices · Phase 3B" rather than fake numbers, per the no-invented-data rule.
- Float columns (not Numeric) for shares/price: SQLite has no native decimal type, and Phase 3 calculations run in pandas floats anyway.

**Testing (Flask test client, in-memory DB)**
- Logged-out `/portfolio/` redirects to login with `?next=`. Empty state renders. Bad input (ticker `apple!`, 0 shares, negative price, future date) shows all four errors. ` aapl ` is stored as `AAPL`; `brk.b` as `BRK.B`. Duplicate ticker rejected on add and on edit-to-existing. Dashboard totals correct ($1,502.50 + $1,000.00 = $2,502.50). Edit pre-fills and updates. A second user gets 404 on another user's edit/delete and sees an empty table. GET delete is 405; POST delete works. Deleting a user cascades to their holdings.
- Real app started: `holdings` table created in `instance/marketmind.db` alongside `users`.

**Problems**
- One test assertion failed on `can't` because Jinja HTML-escapes the apostrophe as `&#39;`. The page displays correctly; only the test string needed changing.

---

## 2026-11-15 — Phase 3B: yfinance market data + caching

**Before starting:** Logan confirmed the Phase 3A browser test (all seven steps) and committed 335577b. Approved installing yfinance + pandas when asked.

**What we built**
- Installed **yfinance 1.8.0** (released 2026-11-03) and **pandas 3.1.1** (plus numpy, requests, curl_cffi as dependencies). `requirements.txt` refreshed. Checked the yfinance changelog first: 1.0 declared "no breaking changes", and `Ticker.info` / `history()` are unchanged through 1.8.0.
- `app/services/__init__.py`: the services layer (routes → services → provider; routes never call APIs directly).
- `app/models.py`: `CacheEntry` table (key, JSON value, fetched_at). A database-backed cache survives the dev server's auto-restarts, so prices fetched before the demo are still there when it starts.
- `app/services/cache.py`: `get_or_fetch(key, ttl_seconds, fetch)`. Checks memory → `cache_entries` → provider. Returns a `CacheResult` dataclass (value, fetched_at, from_cache, stale, error). If the provider fails and a stale copy exists, the stale copy is served with `stale=True` so the UI can say "last updated X ago" instead of breaking.
- `app/services/market_data.py`: `get_quote` (built from `Ticker.info`: price, previous close, open, day high/low, volume, market cap, 52-week range, name, sector, industry, exchange, Yahoo's quote timestamp, market state; always `source` + `delayed=True`), `get_quotes` (batch, each cached), `ticker_exists` (True / False / None = unreachable), `get_history(ticker, range)` with the 8 UI ranges mapped to yfinance period/interval and per-range TTLs (10 min intraday → 24 h for 5Y/MAX), and `history_dataframe` to rebuild a pandas frame from the cached JSON rows. Only EQUITY and ETF quote types are accepted.
- `app/forms.py`: `HoldingForm.validate_ticker` now also asks `ticker_exists`. Unknown → "was not found as a stock or ETF symbol". Provider unreachable → the holding is still saved and `routes/portfolio.py` flashes a "could not verify" warning (small helper added there).

**About the provider (for the write-up)**
- yfinance is unofficial and free, no API key. Yahoo's terms: personal use only. Quotes are delayed; rate limits are undocumented and Yahoo temporarily blocks IPs that call too often (`YFRateLimitError`). Hence: every call goes through the cache, quotes have a 15-minute TTL, and nothing is ever fetched twice within a TTL.

**Testing (in-memory DB + live Yahoo calls)**
- Cache: second call is a hit; survives clearing memory (DB layer); refetches after TTL; serves stale copy with error text when the fetcher raises; raises if there is no copy at all.
- AAPL quote fetched in ~0.5 s, second call < 0.05 s from cache, row present in `cache_entries`. Unknown symbol → None. SPY accepted as ETF. Batch of three all served from cache.
- History: all 8 ranges returned data (1D: 78 five-minute bars … MAX: 503 monthly bars back to 1985). Unknown ticker → empty DataFrame. Bad range key → ValueError.
- Form: `ZZZZQ` rejected with the not-found message; `msft` saved as MSFT with no warning.
- Real app boots and `cache_entries` now exists in `instance/marketmind.db`.

**Notes / nuances**
- The last 5-minute bar of the 1D range (15:55 ET) can differ by a few cents from the official closing price in the quote; both are correct, they're different prints.
- yfinance logs an `HTTP Error 404` line for unknown symbols. That's the provider saying "not found", not an app error.

**Addendum (same day) — price auto-fill on the holding form.** Logan asked that entering a valid ticker fill in its current price. Added `GET /portfolio/quote/<ticker>` (login-required, returns JSON via the cache: name, price, currency, Yahoo quote time, market state, stale flag, source, `delayed: true`), a `{% block scripts %}` hook in `base.html`, `static/js/holding_form.js` (looks up the ticker on blur/Enter with `fetch()`, shows a labeled "Delayed data" quote box, fills the price box only if it is empty or still holds our previous auto-fill, and tells the user to change it to what they actually paid), and quote-box styles. Tested: 200/404/400/302 responses and the rendered form markup. Design note: the auto-filled value is today's delayed price, not the purchase price, and the box says so.

---

## 2026-11-15 — Phase 3C: Live dashboard numbers + allocation chart

**Before starting:** Logan committed 3B (8fd709f) and said "Start 3C".

**What we built**
- `app/services/portfolio_calc.py`: `build_portfolio(holdings)` → `PortfolioSummary` with one `HoldingRow` per holding (value, unrealized gain $ and %, today's change $ and %, allocation %, quote time, fetch time, stale flag) and portfolio totals. Totals include only holdings that have a quote **and** are priced in USD; others are listed in `unpriced` / `non_usd` with a note on the row, so dollars are never added to other currencies and missing data is never hidden. Rows sorted largest value first. `allocation_chart_data()` returns plain lists for the chart.
- `app/routes/portfolio.py`: dashboard route now calls the service; new Jinja filters `signed_money`, `pct`, `big_number`, `et_time` (UTC → Eastern, since that's market time).
- `app/templates/portfolio/dashboard.html` (replaced): provenance banner (Delayed-data badge, source, latest quote time + market state, provider refresh time, 15-minute cache note, warnings for stale/unpriced/non-USD), four KPI tiles, holdings table with per-row quote timestamp, and the allocation chart card. Gains/losses use color **plus** a ▲/▼ sign so they're not color-alone.
- `app/static/js/dashboard_chart.js`: ranked horizontal bars, largest first, one hue (`#3987e5`), percentage printed at each bar end, hover shows the dollar value. Data arrives as JSON in a `<script type="application/json">` tag.
- Plotly is loaded as **plotly.js 3.0.1 from cdn.plot.ly** only on the dashboard. No Python `plotly` package needed: the figure is a JSON description that we build ourselves, which also shows what the Python wrapper would generate.
- `style.css`: gain/loss colors, provenance note, delayed badge.

**Decisions**
- Ranked bars instead of a donut for allocation: bars on one baseline make close values (23.7% vs 22.7%) readable; a donut does not.
- Per-row timestamps as well as a portfolio-level "latest/oldest refresh", because cached quotes for different tickers can be fetched at different times.

**Testing (in-memory DB, live quotes)**
- Portfolio of AAPL, MSFT, SPY (USD), SHOP.TO (CAD), ZZZZQ (unknown, inserted directly to simulate a delisted symbol). Totals, overall %, today's change, and allocations (sum = 100%) all equal hand-computed values from the same quotes. SHOP.TO priced but excluded from totals with a note; ZZZZQ shows "Data unavailable" and sorts last. Dashboard renders the banner, warnings, KPI values, chart JSON, and Plotly script; empty state still renders for a user with no holdings.
- Not yet verified visually in a browser (no browser automation here): Logan to check the chart layout.

---

## 2026-11-15 — Phase 3D: Stock detail pages with range-filtered price chart (Phase 3 complete)

**Before starting:** Logan committed 3C (cae6aab) and said "Please do 3D".

**What we built**
- `app/routes/stocks.py`: `stocks` blueprint. `/stocks/<ticker>` renders the full delayed quote (price, change, previous close, open, day range, 52-week range, volume, average volume, market cap, currency, exchange, sector/industry) with the same provenance banner as the dashboard, plus a "Your position" panel when the user holds the stock. Unknown symbol → a 404 page; provider down with nothing cached → a 503 "Data unavailable" page. `/stocks/<ticker>/history.json?range=1M` returns chart points for one of the eight ranges, timestamps converted to US Eastern and sent without a timezone suffix (plotly.js plots date strings as given), values rounded to 4 decimals.
- `app/templates/stocks/detail.html` and `not_found.html`.
- `app/static/js/stock_chart.js`: one-series line chart (2px, one hue), unified hover with crosshair, y-axis padded around the data instead of starting at zero, Plotly `rangebreaks` to drop weekends and non-trading hours so intraday charts have no flat overnight segments. The range buttons fetch and redraw with `Plotly.react`. A summary line under the chart shows the period change, range, bar count, and the delayed-data/source note.
- Hookups: blueprint registered; dashboard tickers link to detail pages; `fromiso` filter; CSS for the stats grid, hero price, and range buttons.

**Testing (in-memory DB, live data)**
- Logged-out → redirect. AAPL page shows name, quote time "Nov 13, 4:00 PM ET (market closed)", key stats including $5.18T market cap, and the position panel for a held stock; MSFT shows "Not in your portfolio". ZZZZQ → 404 page, `bad!ticker` → 404. All eight ranges return points (1D: 78 five-minute bars from 09:30 to 15:55 ET; MAX: 503 monthly bars from 1985). Bad range → 400. Unknown ticker history → empty points (chart shows "Data unavailable"). Dashboard links present.
- Not viewed in a browser here; Logan to check the chart (range buttons, hover, no overnight gaps).

**Phase 3 is complete:** holdings CRUD, yfinance + cache, live dashboard, stock pages with charts.

---

## 2026-11-16 — Phase 4A: Finnhub company news for holdings

**Before starting:** Logan created a free Finnhub account and added `FINNHUB_API_KEY` to `.env` (verified structurally without printing it; one test call returned 200 with `X-Ratelimit-Limit: 60`).

**About the provider**
- Finnhub REST API, free tier: personal/non-commercial use, 60 calls per minute (confirmed by the response headers). Key sent in the `X-Finnhub-Token` header, never in the URL, so it can't leak into logs. Company-news endpoint returns id, headline, source, unix datetime, summary, url, image, category, related.
- Observed limitation: Finnhub's ticker tagging is loose (a Berkshire/Nvidia story was tagged AAPL). The page says so.

**What we built**
- `config.py`: `FINNHUB_API_KEY` setting (None if missing).
- `app/services/news_service.py`: `get_company_news(ticker, days)` → cached 30 min (`news:AAPL:7d`), normalizes each article to a plain dict (ISO UTC `published_at`, provider summary kept verbatim), caps at 40 per ticker, maps 429 / 401 / network errors to `NewsError` so the cache can serve a stale copy. `get_portfolio_news(tickers)` merges per-ticker results, de-duplicates by article id (collecting every ticker an article was tagged with), sorts newest first, and returns `meta` (fetch times, stale flag, per-ticker failures).
- `app/routes/news.py`: `news` blueprint at `/news`, login-required, holdings → tickers → articles; `?ticker=` quick filter (full filters in 4D).
- `app/templates/news/index.html`: "Verified facts" banner (source, fetch time, 30-min cache note, tagging caveat, stale/failed warnings), article list with ticker badges linking to stock pages, headline → article link (`rel="noopener noreferrer"`), publisher + time in ET, and the provider summary labeled "Provider summary". Empty states for no holdings / no articles.
- Hookups: blueprint registered, "News" nav link, CSS. `.vscode/` added to `.gitignore`.

**Testing (in-memory DB, live Finnhub)**
- Two holdings → 76 merged articles, none duplicated, 4 tagged with both tickers, newest first; second call from cache. Logged-out → redirect; page shows banner, summaries, links, nav link; `?ticker=AAPL` filters; unknown ticker filter ignored; user with no holdings sees the empty state. With `FINNHUB_API_KEY=None` the page still renders and shows "Data unavailable (FINNHUB_API_KEY is not set in .env)" per ticker with a warning border.

**Notes**
- Article URLs are Finnhub redirect links (`finnhub.io/api/news?id=...`) that forward to the publisher. That's how the provider delivers them.

---

## 2026-11-16 — Phase 4B: Rule-based sentiment with reasons

**Before starting:** Logan committed 4A (e69fcdf) and approved installing vaderSentiment.

**Why a finance keyword list was needed (measured, not assumed)**
- Plain VADER on finance headlines: "Apple beats earnings estimates, raises guidance" → 0.00; "shares tumble after it misses revenue expectations" → +0.08; "Stock hits record high as demand surges" → −0.13. None of *beats, downgrade, tumble, layoffs, record* are in its 7,506-word lexicon.

**What we built**
- Installed **vaderSentiment 3.3.2** (dictionary-based, no model, no network). `requirements.txt` refreshed.
- `app/services/sentiment.py`: `FINANCE_LEXICON` (~170 finance terms scored on VADER's −4..+4 scale: results/guidance/ratings, price action, corporate/legal/regulatory events, plus overrides for words VADER gets wrong in finance such as *sell*, *cut*, *record*, *high*). Multi-word phrases ("raises guidance", "record high", "cuts dividend") are folded into single tokens before scoring so they can live in the dictionary while VADER's negation and intensifier rules still apply. `analyze(text)` returns label (thresholds ±0.10 on the compound score), score, and the matched finance terms as the reason; `analyze_article()` scores headline + provider summary (the only article text we have).
- `app/routes/news.py`: attaches `sentiment` to each article (cheap, uncached).
- `app/templates/news/index.html`: dashed purple "Interpretation" block under each article (label with ▲/●/▼, score, matched terms colored by polarity, which text was used), plus a banner line stating sentiment is computed by MarketMind and not part of the reporting. `style.css`: interpretation styles.

**Testing**
- 12 hand-written headlines: all labeled as expected (e.g. beats/raises guidance → +0.78 positive; cuts dividend/losses → −0.72 negative; "to report results Thursday" → neutral). "Shares did not fall despite weak guidance" → positive via VADER's negation flip, which is debatable; added *weak guidance / soft guidance / disappointing* to the list afterward.
- Live page with AAPL + MSFT: 76 articles labeled (43 positive / 20 negative / 13 neutral), interpretation block and banner present.

**Notes**
- The keyword list is deliberately a plain Python dict at the top of `sentiment.py` so it can be shown and edited in the demo.

---

## 2026-11-16 — Phase 4C: Extractive summaries + rule-based implications

**Before starting:** Logan committed 4B (cf63cf7) and said "start phase 4c". No install needed.

**What we built**
- `app/services/summarizer.py`: **extractive** summaries. Sentences are split (abbreviations like *Inc.*, *U.S.* protected), scored with explainable rules (+1 first sentence, +2 names the company, +1.5 contains a figure, +0.5 per finance keyword up to +2, −1 too short/long, boilerplate such as "sign up"/"read more" excluded), and the top two are shown in original order. Nothing is paraphrased or generated. If the source text has ≤ 2 usable sentences, `is_full_text=True` and the page shows no auto-summary (the provider summary already is the whole text). Every sentence's score and reasons are returned for transparency.
- `app/services/implications.py`: 16 keyword rules (results beat/miss, guidance raised/cut, analyst upgrade/downgrade, M&A, product launch/approval, legal/regulatory, layoffs, dividend/buyback, security incident/outage, leadership change, tariffs/trade, rates/inflation, AI/technology investment). Each fires only when its keywords appear (whole-word matching; " ai " guarded so "airline" doesn't match), and reports the matched keywords, a generic implication, and "what to watch". No rule → "No rule matched" shown, nothing invented. Wording deliberately avoids buy/sell language.
- `app/routes/news.py`: attaches `summary_auto` and `implications` per article; passes company names from cached quotes to the summarizer.
- `app/templates/news/index.html`: "Auto-summary" paragraph (dashed purple left border, "n of m sentences selected; no generated wording") and a "Potential implications" block (topic colored by direction, matched keywords, implication, watch item; up to 3). Banner now states the methods for sentiment, summary, and implications. `style.css` additions.

**Testing**
- Splitter: 3 sentences from text containing "Inc." and "U.S.". Summarizer on a 5-sentence sample: picked the lead sentence (5.5 points: first, names company, figure, finance terms) and the buyback sentence; excluded the newsletter boilerplate and the low-value "based in Redmond" sentence. Short text flagged as full text.
- Implications: beat + raised guidance + buyback + upgrade all detected with their keywords; plain text matches nothing; "airline" doesn't trigger the AI rule; no buy/sell words in any rule text.
- Live page (AAPL + MSFT, 76 articles): 17 auto-summaries (the rest were ≤ 2 sentences), 39 articles with implications, 37 "No rule matched". Most common topic: AI/technology investment.

**Decisions**
- Implications are generic by design (same wording per topic). Making them company-specific would require inventing analysis, which the rules forbid; the sector-level analysis comes in Phase 5 with the topic → sector map.

---

## 2026-11-16 — Phase 4D: News filters (Phase 4 complete)

**Before starting:** Logan committed 4C (f600bf4) and said "Please start 4D". No install.

**What we built**
- `app/services/news_service.py`: `parse_filters(args, tickers)` turns the URL's query parameters into a clean dict (unknown ticker, bad date, or bogus sentiment value → that filter is simply off, so a hand-edited URL can't break the page); `filter_articles(articles, filters, names)` keeps articles that satisfy every active filter: ticker, company/keyword text (searched across headline, provider summary, publisher, tickers, and the company names from cached quotes, so "Apple" finds AAPL stories), date range (publication date in US Eastern), category, sentiment (MarketMind's label); `active_filter_count`. Filtering runs on the already-fetched list, so it never costs a provider call.
- `app/routes/news.py`: always fetches all holdings' news (each ticker is cached), analyzes, then filters; passes `total`, `categories` (from the data), `names`, `filters`, `active_filters`.
- `app/templates/news/index.html`: GET filter form (ticker select with company names, text search, from/to dates, category, sentiment, Apply, ✕ clear) replaces the quick ticker buttons; "Showing X of Y articles (N filters active)" line; "No articles match these filters" state with a Clear button. `style.css`: filter bar + dark `form-select`.

**Why a GET form:** the filters live in the URL, so a filtered view can be bookmarked or shared and the back button works. That's the conventional choice for search/filter pages.

**Testing**
- Unit tests on synthetic articles: each filter alone, invalid params ignored, company-name search via the names map, keyword search in summary, date_from excludes undated articles, combined filters with the correct active count.
- Live page (AAPL + MSFT): 76 of 76 with no filters; ticker=AAPL → 40; sentiment=negative → 20 and every badge on the page is negative; three combined filters → 25 with "3 filters active"; nonsense keyword → 0 with the no-match state; garbage parameters → 200 with no filters active.

**Phase 4 is complete:** company news → sentiment with reasons → extractive summaries + implications → filters.

---

## 2026-11-17 — Phase 5A: Market Overview (indexes, Treasury yields, commodities)

**Before starting:** Logan added `FRED_API_KEY` to `.env` (for 5B). Verified without printing it: 32 lowercase letters/digits, git-ignored, and a live test call returned the latest Fed funds rate (3.88% for October 2026).

**Probing the data first (measured, not assumed)**
- All 17 instruments return quotes from Yahoo via `Ticker.info`: indexes come back as `quoteType` INDEX, commodities as FUTURE. A cold load of all 17 takes about 4.7 s; after that the 15-minute cache serves them instantly.
- Yahoo's CBOE Treasury-yield indexes are in **percent** (^TNX 5.107 = 5.107%). Cross-checked against FRED's official series: DTB3 4.13 / DGS5 4.98 / DGS10 5.15 / DGS30 5.47 (Nov 13) versus Yahoo 4.143 / 4.907 / 5.107 / 5.461 (Nov 17 live), within 0.08 percentage point across two trading days.
- Different exchanges report different quote times (S&P 500 11:38 ET, Russell 2000 11:23 ET; Nikkei last traded 1:45 AM ET), so every row shows its own time.

**What we built**
- `app/services/market_data.py`: `get_market_quote(symbol)` (cache key `mquote:`) accepts INDEX and FUTURE; `_fetch_quote` gained an `allowed_types` parameter. `get_quote` still accepts only stocks/ETFs, so an index can't be added as a holding.
- `app/services/market_overview.py`: instrument list in four groups (U.S. indexes + VIX, global indexes, Treasury yields, commodities), unit-aware formatting (indexes in points; yields in percent with daily change in **basis points**, because a percent change of a yield is easy to misread; commodities in dollars per unit, with the futures contract month when the provider names one), session labels, the **10-year minus 13-week spread** (a calculation; its explanatory note is labeled interpretation), and `index_performance(range)` = percent change since the first close of the period.
- `app/routes/market.py`: `market` blueprint, `/market/` page and `/market/performance.json?range=` (1M, 3M, 6M, 1Y, 5Y), both login-required.
- `app/templates/market/index.html`: provenance banner, U.S. index tiles, three compact tables, yield spread + interpretation box, the performance chart with its period control above it, a table view, and unit footnotes.
- `app/static/js/market_chart.js`: plotly.js line chart. Hookups: blueprint registered, "Markets" nav link, CSS.

**Chart decisions (dataviz guidance + measured checks)**
- Percent change since the start of the period puts indexes at very different levels (S&P ≈ 7,300, Russell ≈ 2,700) on one axis, with no second axis.
- Ran the palette validator (via macOS's built-in JavaScriptCore) against our card background `#121826`. Four line colors passed the adjacent-pair check but failed the every-pair check (orange vs yellow: ΔE 10.6 normal vision, 4.8 deuteranopia). Lines cross freely, so the chart shows **three** indexes with distinct stories (S&P 500 large companies, Nasdaq tech-heavy, Russell 2000 small companies), which pass every check. The Dow keeps its tile.
- Legend always; end labels only when line ends are ≥ 18 px apart and the chart is ≥ 640 px wide (otherwise legend + table carry the names, never nudged labels); end-dots with a ring in the card color; table view built with `textContent`; the old chart stays dimmed while a new period loads; legend clicking disabled (hiding a line would orphan its dot and label).

**Visual testing in headless Chrome (first time we could see a page)**
- Rendered the real page HTML with live chart data and screenshotted desktop, 5Y, and a true 390 px phone view (Chrome won't make a window under ~500 px, so the phone view was rendered inside a 390 px iframe). Found and fixed:
  1. Empty strip on the right of the chart: Plotly stretched the axis to fit data-anchored labels, and also pads 5% wherever there are dot markers. Labels are now anchored to the plot edge, the x range is set to the first/last date, and the end-dots draw over the edge (`cliponaxis: false`).
  2. **Gain/loss colors on table cells were being overridden by Bootstrap** (`.table > :not(caption) > * > *` beats `.mm-gain`). This also affected the Portfolio dashboard's Today and Unrealized P/L columns since 3C, which showed white instead of green/red. Fixed with more specific selectors; before/after dashboard screenshots confirm.
  3. Long tile names wrapped and misaligned the numbers → two-line label height; card notes moved under titles.
  4. Phone: the table's Change column was pushed off-screen → moved next to the name, kept on one line.
- One false alarm: a screenshot showed the wrong period button highlighted. The DOM showed the correct state; the screenshot had frozen Bootstrap's 0.15 s fade. Later screenshots disable transitions.

**Testing**
- Unit rules (bps, $, points, "Data unavailable", direction at display precision); unknown symbol → "Data unavailable"; spread equals 10-yr minus 13-wk; 17/17 instruments live; every chart period returns three series starting at 0% with change matching start/end closes; bad period → 400; logged-out → redirect; quote-type separation both ways; Home, Portfolio, News, Stock, and Add pages still 200.

**Known follow-up:** the Home page still labels Portfolio, News, and Market Intelligence as "Planned" (unchanged since Phase 1B). Fix during Phase 8 polish.

---

## 2026-11-17 — Phase 5B: U.S. economic indicators from FRED

**Before starting:** Logan committed 5A and said "start 5B". No install (uses `requests`, already present).

**About the provider (checked on FRED's own documentation pages)**
- FRED = Federal Reserve Economic Data, run by the Federal Reserve Bank of St. Louis. It republishes official statistics: BLS (prices, jobs), BEA (GDP), Federal Reserve Board (policy rate). Free key.
- **Rate limit: 120 requests per minute** (FRED errors page: "Up to 120 requests per minute are allowed before being served a 429 error code"). We make 7 calls, cached 6 hours.
- **Terms of use require apps to display:** "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis." Shown in the indicators banner.
- Third-party copyrighted series need the owner's permission beyond personal use. Checked all 7 series' notes for "Copyright": none (they're U.S. government data).
- **Security:** FRED only accepts the key as a URL parameter, so a raw network error message (which includes the URL) would contain the key. All errors are replaced with plain messages (`raise FredError(...) from None`) before they can reach logs, the cache, or the page. A test injects a failure whose message contains the key and confirms it appears nowhere.

**What we built**
- `config.py`: `FRED_API_KEY`.
- `app/services/fred_service.py`: fetches observations (3 years) per series through the cache (`fred:<SERIES>`, 6 h); FRED's "." becomes `None` and is never filled in. Six indicator cards: CPI inflation and core inflation (**12-month change calculated from the price index**), unemployment rate (as published), jobs added (**monthly change in PAYEMS**, thousands), Fed funds target range (lower + upper limit, when the current range took effect and what it was before), real GDP growth (as published, annualized). Server-drawn SVG sparklines (2 years; 3 years for GDP; a staircase for the policy rate) that break at missing data, end in a blue dot, and have hover bands with native tooltips ("Sep 2026: 3.7%").
- `app/routes/market.py`: passes `econ=build_indicators()` to the page.
- `app/templates/market/index.html`: "U.S. economic indicators" section with an "Official data" banner, fetch time, the FRED notice, and six cards. Each card shows a one-line definition, the period, whether MarketMind calculated the value, the comparison with the previous period, notes, and the publishing agency with links to the official FRED series pages.
- `style.css`: card and sparkline styles. Comparisons are neutral text, not green/red: whether rising unemployment or inflation is "good" is a judgment the app doesn't make.

**What the data showed**
- FRED has **no October 2025 value** for CPI, core CPI, and the unemployment rate, while payrolls are complete. The pattern (price survey and household survey missing, establishment survey present) matches the October–November 2025 federal government shutdown, when BLS could not collect those surveys. Consequence: October 2026's 12-month inflation can't be calculated, so the card shows September 2026 (the latest calculable month) with a note saying exactly why. FRED's own transformation agrees: its "percent change from year ago" is also missing for October 2026.

**Problems and fixes**
- `TypeError: 'builtin_function_or_method' object is not iterable` in the template: `econ.items` in Jinja finds the dictionary's built-in `.items()` method before the `"items"` key. Renamed the key to `cards`.
- Headless-Chrome screenshot showed "3.75%–4.00%" wrapping next to its sparkline → compact form "3.75–4.00%", kept on one line.

**Testing**
- Calculation rules (month arithmetic across year ends, 12-month change, monthly change, gaps never bridged, formats, sparkline geometry incl. staircase).
- **Cross-checked our arithmetic against FRED's own transformations:** 12-month change for CPIAUCSL and CPILFESL vs `units=pc1` (15 months each) and payroll change vs `units=chg` (17 months): worst difference 0.0000.
- Live: 6/6 cards; cold load 2.3 s, warm 10 ms. Missing key → "Data unavailable: FRED_API_KEY is not set in .env" with the rest of the page intact. Key never in page HTML. Other pages still 200. Desktop and 390 px phone screenshots checked.

---

## 2026-11-17 — Phase 5C: Market developments (topic detection + sector impact)

**Before starting:** Logan committed 5B and said "Start 5c". No install.

**Probing first:** Finnhub general news returned 100 articles (Reuters 74, CNBC 26) covering about 36 hours, all with summaries and none tagged with tickers. A first draft of topic keywords matched only 25 of 100. The misses shaped the final map: "ahead of Nvidia results" (earnings), "Russian drone attack" and "tanker attacks" (geopolitics), "US retail sales increase" (no topic, so "employment" became **Jobs & consumer spending**). A bare "war" would also catch "trade war", so topics can list phrases to ignore.

**What we built**
- `app/services/topic_map.py` (new, **the map we write together**; pure data, meant to be read and edited): 8 topics (interest rates & central banks, inflation, jobs & consumer spending, tariffs & trade, oil & commodities, corporate earnings, technology & AI, geopolitics & conflict). Each has keywords, exclusions, why it matters, what to monitor, and **two opposite scenarios** (e.g. rates falling vs rising), each with direction phrases and the sectors that could see potential positive or negative implications, with example companies. 45 example companies, each filed under its own sector. Direction phrases are generated from subject × verb lists in both word orders (`moves(["oil"], "up")` → "oil rises", "rising oil", …): 3,888 phrases from a few short lists.
- `app/services/market_news.py` (new): normalizes text, compiles each topic's keywords and each scenario's phrases into **one combined regex** (fast), classifies articles (one keyword in the headline, or two different ones in the summary), detects direction by counting articles per scenario (a scenario "leads" with more articles and at least 2× the other; otherwise "mixed" or "none", and both scenarios are shown), spots example companies named in the text, and orders each topic's articles most-on-topic first. Earnings uses "read-through": its sector lines come from the companies named in the coverage.
- `app/services/news_service.py`: one shared `_finnhub_get` helper (same error handling for company and market news; also catches non-JSON replies now) and `get_market_news()` (cached 30 min).
- `app/routes/market.py`: `/market/developments`. `app/templates/market/developments.html` (new): banner separating **Verified facts** from **Interpretation**, topic chips (and which topics have no coverage), one card per topic with facts on the left (headlines, publisher, time, matched keywords, companies named) and a dashed interpretation panel on the right (why it matters, direction + the exact words matched, sector scenarios with example companies linking to their stock pages, opposite scenario collapsed, what to monitor), then the full headline feed with topic tags. `index.html`: Overview / Developments tabs. `style.css`: tabs, chips, panels.

**Problems and fixes**
- "Fed cuts rates" matched nothing: keywords had "the fed" but not "fed", because "fed" is also a verb. Added "fed" plus verb exclusions ("fed into", "fed up", …); spot-checked both directions.
- Sort tie-break ordered equal-coverage topics oldest-first. Fixed with two stable sorts.
- Cards led with the newest story, which put an off-topic "AI exam cheating" story first. Now most-matched-keywords first: e.g. "US to curb China's access to AI chips".
- Screenshot tooling: `sips --cropOffset 0 0` is ignored (it center-crops); offsets of 1 work.

**Testing**
- Map consistency (every sector valid, every example company under its own sector, aliases unique). Nine handwritten headlines: correct topics and directions, "airline" isn't AI, "election results" isn't earnings, "trade war" isn't geopolitics; mixed and no-signal cases.
- Live: 37 of 100 articles matched; six topic cards (geopolitics 12 leaning "tensions rising" 6–0, oil 10 mixed 1–1, tech & AI 9, earnings 6 naming NVDA, rates 4, jobs 1); no coverage for inflation or trade. Page renders, example-company links open stock pages, tabs on both Markets pages, News page unchanged after the refactor ("Showing 40 of 40"), missing key → "Data unavailable". Desktop and phone screenshots checked.

**Known limits (shown on the page):** keyword rules can't read negation ("no rate cut") or context, so every signal lists its matched words; sector effects are general textbook relationships, not predictions.

---

## 2026-11-17 — Phase 5D: Sector impact summary, portfolio exposure, live numbers (Phase 5 complete)

**Before starting:** Logan committed 5C (e3c37dd) and said "Start 5D". No install.

**Data check first:** a holding's sector comes from Yahoo, which uses its own names ("Consumer Cyclical", "Financial Services", "Basic Materials", ...). Fetched Yahoo's sector for all 45 example companies in the topic map: Yahoo uses exactly 11 names, and every company, translated, matches the sector we filed it under. Funds report no sector (SPY: `None`), so they're never guessed.

**What we built**
- `app/services/topic_map.py`: `YAHOO_TO_SECTOR` (Yahoo's names → the 11 sectors) and a `live` list per topic: the numbers to show beside it, e.g. rates → Fed funds target range (FRED) + 10-year Treasury yield (Yahoo); oil → WTI, Brent, gold; geopolitics → VIX, Brent, gold.
- `app/services/portfolio_calc.py`: each holding row keeps Yahoo's `sector` and `quote_type`; new `sector_exposure(summary)` = share of current USD value per sector, largest first. Funds, unpriced holdings, and non-USD holdings are listed separately with the reason. Reusable for Phase 6's diversification check and Phase 7's risk question.
- `app/services/market_news.py`: `sector_impact()` rolls every development up by sector (leading scenarios add ▲/▼ lines; developments without a clear direction mark their sectors "direction unclear") and labels each sector *signals lean positive / negative*, *mixed*, *direction unclear*, or *no current signal*, with the evidence and article counts; `link_holdings()` marks which of your holdings each development touches; `attach_live_numbers()` adds the related numbers (facts, each with its own time or period).
- `app/services/market_overview.py` `instrument_row(symbol)` and `app/services/fred_service.py` `get_indicator(key)`: small public lookups so other pages reuse the cached quotes and indicator cards.
- `app/routes/market.py`: the developments route now builds exposure → impact → holdings links → live numbers.
- `app/templates/market/developments.html` + `style.css`: "Sector impact summary" (labeled interpretation) with a "Your portfolio and these developments" panel (your sectors' weights, label, linked topics, funds explained) and a card per sector with signals; "Related numbers" in each topic's facts column; "Your holdings in these sectors" in each interpretation panel.

**Problems and fixes**
- The jobs topic "leaned strengthening" on **one** article, and that one article labeled Utilities and Real Estate "lean negative" and Financials "lean positive". One story isn't a trend: a direction now needs at least **2 articles** (plus the existing 2× rule). A lone article shows as "Too little to call a direction", and both scenarios are shown. This also improves the 5C cards.
- "(1 articles)" / "1 article(s)" grammar fixed.
- Earnings read-through lines kept the label "(industry of companies named...)" inside the sector name, which would break the rollup; split into a plain `sector` plus a display `qualifier`.

**Testing**
- Exposure with AAPL, MSFT, XOM, JNJ, SPY, SHOP.TO: Technology 45.8% (AAPL, MSFT), Energy 30.6%, Healthcare 10.2%, SPY 13.4% listed as a fund; sector shares + fund share = 100.0% of USD value; SHOP.TO listed as CAD.
- Rollup on controlled developments built from the real map: geopolitics "rising" makes Industrials *mixed* (defense ▲, airlines ▼), Technology *negative*, Energy and Materials *positive*; untouched sectors *no current signal*; holdings linked per development (leading scenario only vs both when unclear).
- One article → "weak"; two → "leans". Live: every topic's related numbers available (e.g. VIX 25.39, Brent $93.40, Fed range 3.75–4.00%, unemployment 4.1% Oct 2026). Page with holdings shows the panel, "You hold" badges, per-card holdings lines; a user without holdings sees an invitation instead. Portfolio, Overview, News, Stock pages unchanged. Desktop screenshots checked.

**Phase 5 is complete:** market overview (indexes, yields, commodities), FRED economic indicators, market developments with topic detection, and sector impact connected to the user's portfolio.

---

## 2026-11-19 — Phase 6A: Research universe + hybrid fundamentals (FMP + Yahoo)

**Before starting:** Logan created a free Financial Modeling Prep account and added `FMP_API_KEY` to `.env` (verified without printing it).

**Checking the provider first**
- FMP's own pages block automated reading, so free-plan limits came from summaries checked in November 2026 (250 requests/day, 500 MB per 30 days, up to 5 annual statements, legacy API for paid customers only) and from real calls.
- The key works in an `apikey` **request header**, so it never appears in a URL. All 8 endpoints we need answered for Apple.
- **Coverage test:** the free plan serves a fixed list of popular stocks. 21 of the 45 topic-map companies were covered; the rest returned HTTP 402 "not available under your current subscription". **None** of 24 Materials, Real Estate, and Utilities companies tried were covered. Yahoo had five years of statements with every needed line for blocked companies (NextEra, Prologis, Linde).
- **Decision (Logan): option 1, hybrid.** FMP where covered, Yahoo otherwise, and MarketMind calculates every ratio itself. CLAUDE.md's tech-stack row updated.

**Cross-checking the two providers before trusting the hybrid**
- Line by line for Apple, Exxon, Coca-Cola, JPMorgan: revenue, net income, equity, current assets/liabilities, operating cash flow, capex, free cash flow **identical**. Operating income differed for Coca-Cola (8%) → stored, never scored. Total debt can differ a few percent (lease obligations counted differently). Banks' revenue and debt are defined completely differently by each provider (JPMorgan revenue $280B vs $182B).

**What we built**
- `data/universe.csv`: 64 companies, 4–9 in each of the 11 sectors (all 45 topic-map companies plus AI networking, data-center power, healthcare, payments, etc.). Name, sector, industry, and reporting currency were pulled from Yahoo, and every row was checked: an equity, priced in USD, statements in USD, in the intended sector.
- `app/services/research_data.py`: `load_universe()` (validates the CSV), `get_fundamentals()` (FMP's three statements, or Yahoo's when FMP returns 402, hits its daily limit, or has no key; one normalized record of 5 annual years; cached 7 days), and `compute_metrics()`: 14 metrics by MarketMind's formulas (revenue growth 1-yr and 3-yr, net income growth, net margin, ROE, debt to equity, current ratio, free cash flow and its margin, profitable years, P/E, P/B, P/S, FCF yield), each with its formula, inputs, and a note when it isn't meaningful (net loss, negative equity, missing market value, non-USD). Banks and brokers (JPM, BAC, GS) use the 5 metrics that are comparable.
- `app/cli.py` + registration in `app/__init__.py`: `flask --app run refresh-fundamentals [TICKERS...]` loads statements into the cache and prints a summary table, the source per company, and the FMP calls used. New concept: Flask CLI commands built with `click`.
- `config.py`: `FMP_API_KEY`.

**Problems and fixes**
- "Profitable years" came out 5 of 5 from FMP but 4 of 4 from Yahoo for Apple (Yahoo lacked a 5th year of net income), so the metric depended on the provider. It now always looks at the latest 4 years.

**Testing**
- Universe: 64 rows, all 11 sectors, every topic-map company present with the same sector.
- Formulas on a handmade company (all 14 metrics exact) plus net loss, negative equity, no market value, non-USD statements, bank, and empty cases.
- **Same company from both providers:** Apple 14 of 14 metrics identical; Coca-Cola 14 of 14 identical except debt to equity (3.65%, lease accounting, disclosed in the metric's note); JPMorgan's 5 bank metrics identical.
- No FMP key → Yahoo for everyone, 0 FMP calls.
- Full run: 64 companies in 81 s, 31 from FMP and 33 from Yahoo, 0 failures, 116 FMP calls (≈205 of 250 used today including the checks). Repeat run: 0 s, 64/64 from cache, 0 FMP calls. Existing pages unchanged.

---

## 2026-11-19 — Phase 6B: Research Confidence Score

**Before starting:** Logan committed 6A (3093a47) and said "Start phase 6b". No install, no new key.

**What we built**
- `app/services/scoring.py` (new). Five categories, each 0–100, weighted 25/20/20/20/15:
  - **Financial health** (statements): debt to equity, current ratio, net margin, free cash flow margin, revenue growth (3-yr average, else 1-yr), profitable years. Banks/brokers: return on equity, net income growth, profitable years.
  - **Industry & market conditions**: the sector's label from Market developments (lean positive 75 · mixed/unclear 50 · lean negative 25; interpretation, so never 0 or 100) and the sector's 3-month price momentum vs the S&P 500 (average of the universe companies in that sector).
  - **News & catalysts**: this week's company news (Finnhub, ≥ 3 articles): sentiment `50 + 50 × (positive − negative) ÷ total` and catalyst events from the Phase 4 implication rules (`50 + 50 × (positive − negative) ÷ catalyst articles`, ≥ 2 needed).
  - **Valuation**: P/E, P/S, and free cash flow yield (banks: P/E, P/B) compared with the **median of the company's peers**, as a ratio (≤ 0.75× earns 100 … above 1.33× earns 0) or, for yields, a gap in percentage points.
  - **Historical performance & risk**: 1-year return vs the S&P 500, annualized volatility, worst drop from a 1-year high (Yahoo daily closes, dividend-adjusted).
- Every rule is a **band table at the top of the file** (`BANDS`, `SIGNAL_POINTS`, `WEIGHTS`, `OUTLOOK`). A category is the average of its sub-scores; **missing data is left out, never counted as zero**; weights rescale over the categories used, and fewer than 3 categories means no overall score. Outlook: ≥ 65 positive, ≥ 45 neutral, else negative. Key risks and strengths are plain sentences generated from the same numbers. The disclaimer ("not the probability of a profit, a price prediction, or a recommendation") is a constant shown with every result.
- `app/cli.py` + registration: `flask --app run research-scores` (ranked table) and `--explain TICKER` (every sub-score with its measured value, points, the exact rule, and context such as the sector median). Fresh Finnhub calls are spaced 1.1 s apart to respect its 60 calls/minute.

**Problems found by reading real breakdowns, and fixes**
- **Percentile ranks were too coarse in small peer groups**: JPMorgan's valuation scored 0 because its P/E was 14.9 vs Goldman's 14.2 with only two other banks. Valuation now compares with the peer *median* (ratio bands), which grades how far from typical a company is: JPMorgan's P/E is 1.18× the other banks' median → 25, and the category notes "only 2 peers, treat as a rough guide".
- **Growth bands were cliff-edged**: a 2.4% profit dip scored 0, the same as a collapse. Small declines (to −3%) now earn 25.
- **A positive event was listed under risks**: NVIDIA's risks said "catalyst events: Product launch …; Analyst downgrade …". Positive and negative events are now kept apart: positive ones under strengths, negative under risks.
- **Sector context mixed directions**: it now reads "negative: Geopolitics & conflict, Interest rates · unclear: Technology & AI, …".
- Checked JPMorgan's 6 "security incident or outage" events: real stories (a vendor data breach, a banking outage, a cyberattack disclosure) plus two loosely tagged industry stories. Rule left as is.

**Testing**
- Unit tests on an invented 7-company world with hand-checkable answers: band edges, every health sub-score, the median comparison (a loss-maker is excluded from peers), the small-bank-group note, news formulas, too-few and unavailable news left out (4 of 5 categories, weights rescaled), outlook cut-offs, and every risk/strength sentence traced to its number.
- Live, all 64 companies: first run 123 s (fresh news spaced for Finnhub), repeat 2 s from cache. 14 Positive · 44 Neutral · 6 Negative; scores 37–75, median 59; all 5 categories used for every company. Sector averages span 50–66, so no sector is favored by construction.

---

## 2026-11-19 — Phase 6C: Research pages + diversification check (Phase 6 complete)

**Before starting:** Logan committed 6B (67683df) and said "Please start phase 6c". No install.

**Design decision: pages read a saved batch.** Scoring all 64 companies needs about 64 news calls and Finnhub allows 60 per minute, so a page can't score on the fly. `flask --app run research-scores` now saves the whole batch ("snapshot"); the pages read it and add live (delayed) prices and news only for what they show. The page states when scores were calculated and warns if the batch is more than a day old.

**What we built**
- `app/services/cache.py`: `put(key, value)` (store something we calculated ourselves) and `peek(key)` (read it back however old it is).
- `app/services/scoring.py`: `score_universe(save=True)`, `save_snapshot()` / `load_snapshot()` (cards stored as plain dicts, without news articles to keep it small), and `explain_opportunity()`: "why identified" sentences built only from the score card (rank among companies you don't hold, strongest categories, top strengths, and the market-coverage topics that name the company). New risk sentence: net income fell 10% or more.
- `app/routes/research.py` (new): `/research/`: companies you **don't hold** with a positive research outlook (≥ 65), highest first, each with live price + time, why it was identified (labeled interpretation), key risks, score + five category meters, and a **concentration check**; plus a filterable table of all 64 (sector, outlook, hide holdings; "You hold" badges). `/research/<ticker>`: full research page.
- **Diversification check** (`concentration_check`): uses `sector_exposure()` from 5D. At or above **25%** of portfolio value in that sector → amber "⚠ Concentration check" warning; below → states the share; none → "you don't hold any {sector} stocks directly" (and only claims "a new sector for your portfolio" when the user holds no funds, because a fund like SPY contains every sector); no holdings → invitation. Funds are always mentioned as possibly hiding more exposure. Facts about the user's portfolio, never advice.
- Templates: `research/index.html`, `research/company.html` (score summary, why / strengths / risks, every category's rules and points like `--explain`, statements table + calculated metrics with formulas on hover, this week's news with sentiment tags, links to the stock chart and market developments), and `research/_macros.html` (outlook badge, category meters, concentration box, live price, disclaimer box, shared by both pages). Disclaimer shown prominently on both. "Research" nav link; styles.

**Problems found in screenshots, and fixes**
- Category names were cut off in the meters ("Industry & market conditio…") → short labels, full name on hover.
- "You don't hold any Healthcare stocks, so this would be a new sector" overclaimed for a user holding SPY → "directly", and the "new sector" claim only without funds.
- On the company page the "why" bullets repeated the strengths listed right below → the company page's "why" keeps rank, strongest areas, and coverage only.
- SLB's net income fell 24.4% but no risk mentioned it → new rule (≥ 10% drop).

**Testing (in-memory database seeded read-only with a copy of the real cache, so no test user touches the real database and no extra API calls are spent)**
- `put`/`peek` round trip; missing batch → None; a 30-hour-old batch flagged stale.
- Concentration levels: heavy (45.8%), some (10%), none, no holdings.
- `/research/` for a user holding AAPL, MSFT, XOM, SPY: 12 opportunities, none held; heavy warning on a Technology company; table 64 rows; filters Energy → 4, hide held → 61, Positive → 14. `/research/SLB`: 5 category tables, statements, metrics, news, concentration; AAPL page marked "You hold"; JPM bank notes; `/research/ZZZZ` → 404; user without holdings → invitation; no saved batch → "not calculated yet"; logged out → login. All older pages still 200. Desktop and 390 px phone screenshots checked.

**Phase 6 is complete:** curated universe, hybrid fundamentals, the Research Confidence Score, and research pages with a diversification check.

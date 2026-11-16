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

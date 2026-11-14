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

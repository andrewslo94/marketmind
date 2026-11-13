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

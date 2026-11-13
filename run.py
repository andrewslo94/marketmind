"""
run.py — starts the MarketMind development server.

Usage (with the virtual environment active):
    python run.py
Then open http://127.0.0.1:5001 in your browser.
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Port 5001 because macOS uses 5000 for AirPlay Receiver.
    # debug=True auto-reloads on code changes and shows detailed errors.
    # It is for local development only — never use it on a public server.
    app.run(debug=True, port=5001)

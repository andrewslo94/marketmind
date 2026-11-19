"""
app/cli.py — terminal commands for maintenance tasks.

Run from the project folder with the virtual environment active:

    flask --app run refresh-fundamentals            # all companies in data/universe.csv
    flask --app run refresh-fundamentals AAPL NEE   # just these
    flask --app run research-scores                 # Research Confidence Score, ranked
    flask --app run research-scores --explain NVDA  # every rule and point for one company

It loads company statements into the cache (Financial Modeling Prep where
the free plan covers the company, Yahoo Finance otherwise) and prints what
it got. Pages only read the cache, so running this before a demo keeps them
fast. Statements are kept for 7 days; running it again sooner costs no
provider calls.

`flask` commands are built with the click library (installed with Flask):
@click.argument turns the words after the command name into a Python tuple.
"""
import time

import click


def _pct(m):
    return "—" if m.value is None else f"{m.value * 100:5.1f}%"


def _ratio(m):
    return "—" if m.value is None else f"{m.value:5.2f}"


def _billions(v):
    return "—" if v is None else f"${v / 1e9:,.1f}B"


def register_cli(app) -> None:
    @app.cli.command("refresh-fundamentals")
    @click.argument("tickers", nargs=-1)
    def refresh_fundamentals(tickers):
        """Load company statements for the research universe into the cache."""
        from app.services import research_data as rd
        from app.services.market_data import get_quote

        wanted = [t.strip().upper() for t in tickers]
        companies = [c for c in rd.load_universe() if not wanted or c.ticker in wanted]
        unknown = sorted(set(wanted) - {c.ticker for c in companies})
        if unknown:
            click.echo(f"Not in data/universe.csv, skipped: {', '.join(unknown)}")

        start_calls, started = rd.fmp_calls_made(), time.time()
        by_source, not_covered, failed = {}, [], []
        click.echo(f"{'Ticker':6} {'Sector':22} {'Source':8} {'FY end':10} {'Revenue':>10} "
                   f"{'Net mgn':>7} {'ROE':>7} {'Debt/Eq':>7} {'Rev gr':>7} {'P/E':>6}")
        for c in companies:
            try:
                result = rd.get_fundamentals(c.ticker)
            except Exception as exc:  # noqa: BLE001 — report and keep going
                failed.append(c.ticker)
                click.echo(f"{c.ticker:6} {c.sector[:22]:22} unavailable: {exc}")
                continue
            record = result.value
            try:
                quote = get_quote(c.ticker).value or {}
            except Exception:  # noqa: BLE001
                quote = {}
            m = rd.compute_metrics(record, quote.get("market_cap"), c.industry)
            source = "FMP" if record["source"].startswith("Financial") else "Yahoo"
            by_source[source] = by_source.get(source, 0) + 1
            if record.get("fmp_note") == "not on FMP's free plan":
                not_covered.append(c.ticker)
            y0 = record["years"][0] if record["years"] else {}
            click.echo(f"{c.ticker:6} {c.sector[:22]:22} {source:8} {y0.get('period_end') or '—':10} "
                       f"{_billions(y0.get('revenue')):>10} {_pct(m['net_margin']):>7} {_pct(m['roe']):>7} "
                       f"{_ratio(m['debt_to_equity']):>7} {_pct(m['revenue_growth']):>7} {_ratio(m['pe']):>6}"
                       + ("  (cached)" if result.from_cache else ""))
            if not result.from_cache:
                time.sleep(0.3)  # be polite to the providers between fresh fetches

        click.echo("")
        click.echo(f"{len(companies)} companies in {time.time() - started:.0f}s: "
                   + ", ".join(f"{n} from {s}" for s, n in sorted(by_source.items()))
                   + (f", {len(failed)} unavailable ({', '.join(failed)})" if failed else ""))
        if not_covered:
            click.echo(f"Not on FMP's free plan, so Yahoo was used: {', '.join(not_covered)}")
        click.echo(f"FMP calls this run: {rd.fmp_calls_made() - start_calls} (free plan: 250 per day)")
        click.echo("Bank metrics show '—' where statements aren't comparable; see research_data.BANK_INDUSTRIES.")


def _score(v):
    return "  —" if v is None else f"{v:3.0f}"


def register_research_commands(app) -> None:
    @app.cli.command("research-scores")
    @click.option("--explain", metavar="TICKER", help="Show every rule and point for one company.")
    @click.option("--top", default=64, show_default=True, help="How many companies to list.")
    def research_scores(explain, top):
        """Calculate the Research Confidence Score for the research universe."""
        from app.services import research_data as rd
        from app.services import scoring

        if explain and not rd.get_company(explain):
            raise click.BadParameter(f"{explain.upper()} is not in data/universe.csv", param_hint="--explain")
        click.echo("Gathering data (cached where possible; fresh news is spaced out to respect Finnhub's 60 calls a minute)...")
        started = time.time()
        cards, ctx = scoring.score_universe(news_pause=1.1, save=True)
        click.echo(f"Scored {len(cards)} companies in {time.time() - started:.0f}s "
                   "and saved them for the Research page.\n")

        if explain:
            card = next(c for c in cards if c.ticker == explain.upper())
            _print_breakdown(card)
        else:
            order = ["health", "industry", "news", "valuation", "performance"]
            click.echo(f"{'#':>2} {'Ticker':6} {'Sector':22} {'Score':>5} {'Outlook':8} "
                       f"{'Health':>6} {'Indus.':>6} {'News':>5} {'Value':>5} {'Perf.':>5} {'Used':>4}")
            for i, card in enumerate(cards[:top], start=1):
                cats = {c.key: c.score for c in card.categories}
                click.echo(f"{i:>2} {card.ticker:6} {card.sector[:22]:22} {_score(card.overall):>5} {card.outlook or '—':8} "
                           + " ".join(f"{_score(cats[k]):>5}" for k in order) + f" {card.categories_used:>3}/5")
            click.echo("\nWeights: health 25% · industry 20% · news 20% · valuation 20% · performance 15%. "
                       "Explain one: flask --app run research-scores --explain NVDA")
        click.echo("\n" + scoring.DISCLAIMER)


def _print_breakdown(card) -> None:
    click.echo(f"{card.ticker} · {card.name} · {card.sector} / {card.industry}")
    click.echo(f"Statements: {card.source}, fiscal year ending {card.fiscal_year_end or '—'}")
    overall = f"{card.overall}/100" if card.overall is not None else "not enough data"
    click.echo(f"Research Confidence Score: {overall} · Outlook: {card.outlook or '—'} · "
               f"{card.categories_used} of 5 categories used\n")
    for cat in card.categories:
        score = f"{cat.score:.0f}" if cat.score is not None else "left out"
        click.echo(f"{cat.name} ({cat.weight}%): {score}")
        for s in cat.subs:
            pts = f"{s.points:>3.0f}" if s.points is not None else "  —"
            line = f"   {s.label:44} {s.display:>26}  {pts}  {s.rule}"
            click.echo(line + (f"  [{s.context}]" if s.context else ""))
        if cat.note:
            click.echo(f"   note: {cat.note}")
    click.echo("\nKey risks:" if card.risks else "\nKey risks: none flagged by the rules")
    for r in card.risks:
        click.echo(f"   - {r}")
    click.echo("Strengths:" if card.strengths else "Strengths: none flagged by the rules")
    for s in card.strengths:
        click.echo(f"   + {s}")

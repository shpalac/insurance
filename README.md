# Insurance — options intelligence (research MVP)

Public, **read-only** quantitative research scanner focused on SPXW/XSP index options. This is a working initial engine for normalized option quote snapshots, **not** a validated profitable system or automated trading bot.

## Implemented

- Deterministic Python 3.11+ scanner; separate **SELL** and **BUY** insurance research rankings.
- European-style, cash-settled single long options and defined-risk two-leg debit/credit spreads.
- Conservative executable bid/ask side selection, per-leg execution costs, exact $100 multiplier.
- Filtered-historical Monte Carlo with EWMA volatility, distribution-based expected payout, expected net P&L, probability of profit, max loss and 95% expected shortfall.
- Hard rejection of stale, frozen, delayed, crossed, shallow or overly wide quotes; separate AM and PM settlement classes.
- SQLite idempotent snapshot persistence, restart-safe dedup primitives, --loop CLI, unit tests and GitHub CI.
- Walk-forward realized-volatility diagnostics explicitly **not** misrepresented as an options backtest.
- Kill switch: every opportunity remains **UNVERIFIED** and the recommendation is **NO TRADE** until full point-in-time validation and model uncertainty intervals exist. No broker order methods are implemented.

## Install

~~~bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
insurance --snapshot /absolute/path/to/snapshot.json --top 5
insurance --snapshot /absolute/path/to/snapshot.json --loop --interval 300
~~~

The scanner consumes JSON snapshots from an external **authorized read-only** market-data adapter. It never silently substitutes option last-trade prices for a current executable bid/ask quote. GitHub runners have no access to your local TWS/Gateway, and the ChatGPT IBKR connection does not grant a GitHub Action broker session. The loop must run on a machine with a functioning data collector and a continuously updated snapshot file. No deployment or persistent runner has been configured in this repository yet.

### Input format

All quotes need independently verified *quote receipt timestamps*, not last-trade timestamps. Dates and timestamps are ISO 8601 with timezones.

~~~json
{
  "as_of": "2026-10-19T15:00:00+00:00",
  "underlyings": {
    "XSP": {"spot": 755.0, "closes": [/* >= 121 chronological daily index closes */]}
  },
  "options": [
    {
      "root": "XSP", "trading_class": "XSP", "expiration": "2026-11-20",
      "settlement": "PM", "right": "P", "strike": 750.0,
      "bid": 8.0, "ask": 8.2, "bid_size": 10, "ask_size": 10,
      "market_data_status": "REALTIME", "quote_time": "2026-10-19T14:59:58+00:00",
      "multiplier": 100
    }
  ]
}
~~~

The above prices are **format examples only, not market observations**; remove JSON comments before parsing. Keep actual snapshots under ignored \`data/snapshots/\` or another private location. Do not commit account or entitlement information to the public repo.

### Research interpretation

For a sell spread: entry credit is **short bid − long ask**. For a buy spread: entry debit is **long ask − short bid**. Expected net P&L under the estimated physical distribution P deducts commissions and adverse execution cushion. These are *illustrative estimates*, not validated EV or a confidence interval. Score components that require statistical validation are deliberately zero. Candidate rankings contain **UNVERIFIED** estimates and *never imply a recommendation*.

SPX regular monthly (AM) and SPXW (PM) are different contracts. XSP is PM-settled. Expiration estimates are in calendar days but return simulations use approximate trading days and omit early-closing and holiday-specific settlement details. Initial implementation rejects non-European/physically settled underlyings; it intentionally does not model exercise/assignment.

## Not yet implemented / blockers

1. Production read-only TWS/IB Gateway collector with proven quote timestamps, pacing, reconnection, session/calendar handling, and broker subscriptions.
2. Independent arbitrage-consistent full risk-neutral Q surface, skew, put-call parity audit, smile/term structure and interest/dividend curves.
3. Robust P model ensemble (GARCH, jump regimes), calibrated IV/RV historical history, uncertainty intervals reflecting parameter and model risk.
4. Point-in-time **options** chain backtester with historical bid/ask, realistic fills/closures, settlement and cash accounting, multiple-testing controls, regime-stress evidence, benchmarks and confidence-bound validation.
5. Production notifications and scored, approved opportunities; portfolio limits, aggregate correlation limits, stress losses, and margin checks.
6. Deployed monitoring service, health endpoints, dashboard, NDX/RUT and multi-expiry spreads/condors/calendars.
7. PAPER or approval-only LIVE mode. No trading permissions will be added without separate explicit authorization.

**Fail-closed policy:** unsupported/incomplete data, unavailable execution prices, unverifiable model uncertainty, or failing risk constraints yield **NO TRADE**. A positive modeled expected value is not sufficient.

Reference contract rules: [Cboe SPX/XSP specifications](https://www.cboe.com/tradable_products/sp_500/spx_weekly_options/specifications). Consult specific contract settlement calendars before trading.

## Captured first scan

The read-only IBKR connector returned SPX/XSP chain identifiers, 251 daily SPX observations, and frozen/delayed option bid/ask observations on October 17, 2026. A sample of the **actual quoted figures** is preserved in `data/observations/2026-10-17-frozen.json` with *null* quote times because the connector returned last-trade timestamps, **not** bid/ask quote timestamps. The scanner rejects these values and emits **NO TRADE**. This does not imply any live edge.

For fresh data, both underlying spot and option quotes require distinct timestamp and data-type validation. Installing a read-only Gateway/TWS collector and a continuously running host remains necessary.

## Local IBKR Gateway collector (optional)

Requires TWS/IB Gateway on your own machine, a market data subscription, and TWS configured **read-only**. The adapter uses `ib_async` with `readonly=True`; it cannot place an order. The ChatGPT IBKR connection does **not** expose a reusable credential or data feed to this repository. The collector is included but **not connected/deployed or integration-tested against your local Gateway**.

~~~bash
python -m pip install -e '.[broker]'
insurance-ibkr --host 127.0.0.1 --port 7497 --loop --interval 300
insurance --snapshot data/snapshots/ibkr.json --loop --interval 300
~~~

Run collector and scanner in separate processes. This collector is deliberately limited to 9:30 a.m.–4:00 p.m. US Eastern on weekdays, without a full holiday calendar: holiday data still fails freshness tests if missing. IBKR delayed/frozen quotes are rejected, including on weekends; an IBKR last-trade timestamp is **not** accepted as a substitute for an executable quote. Future work: prove broker quote timestamps with tick-by-tick bid/ask reception, adopt the exchange calendar and GTH, reduce polling by streaming, test reconnects and broker entitlements.

# LambdaClass research engine — optional compatibility spike

**Status: experimental synthetic-engine smoke, not a historical option-strategy backtest.**
This work is tracked by [issue #90](https://github.com/shpalac/insurance/issues/90).
It does **not** establish positive expected value or trading profitability. The
project's output remains **UNVERIFIED / NO TRADE**, with live orders disabled.

## Choice and licensing

This optional experiment uses the MIT-licensed
[LambdaClass Options Portfolio Backtester](https://github.com/lambdaclass/options_portfolio_backtester).
The normal insurance package keeps its MIT license and its empty mandatory
dependency list. LambdaClass is downloaded only in the separate research CI
workflow, pinned to upstream commit
`afdbacc0b9b9c137edc38d656778f81b84093b2f`.

No LambdaClass implementation code is copied into the scanner. When integrating
upstream code later, preserve its MIT license and copyright attribution.

## What the smoke actually runs

`research/lambdaclass_probe.py` writes two temporary CSVs (synthetic stock
prices and synthetic nine-day option bid/ask quotes) for an imaginary `XYZ`
option. It loads them using LambdaClass's `TiingoData` and
`HistoricalOptionsData`, constructs a **long put** (buy insurance), and runs
its actual `BacktestEngine` with `MarketAtBidAsk` fills and runtime invariants.

The scenario is intentionally extreme and fictional. It uses no broker
credentials, no vendor APIs, and no licensed historical data.

Independent calculations, not copied from the engine's output:

- Initial cash $100,030; 5% option budget $5,001.50.
- At the June 1 rebalance: buy 50 puts at the **ask** $1 each ($5,000);
  buy 950 shares at $100 ($95,000); $30 cash remains.
- Day-one portfolio NAV at the **bid** $0.90 is
  $30 + 950 × $100 + 50 × 100 × $0.90 = **$99,530**.
- Midway, at a fictitious $80 stock price and $5 put bid:
  $30 + 950 × $80 + 50 × 100 × $5 = **$101,030**.
- At the July 1 exit, the $30 put bid yields $150,000. The share value is
  $47,500 and leftover cash $30, for **$197,530** total NAV.
- One purchase and one exit of exactly 50 option contracts are required.
  The engine must match these values within one cent; any mismatch fails CI.

The test uses `NoCosts()` to isolate the price/portfolio arithmetic; it is
**not** an executable trading cost estimate. Realistic broker commissions,
exchange fees, slippage, liquidity caps, settlement conventions, and financing
must be added and stress-tested before a real historical study.

## Run on GitHub Actions

`.github/workflows/lambdaclass-research.yml` runs on relevant PR changes
or a manual dispatch. It builds the Python/Rust upstream package from the
immutable Git revision, runs
`python -m unittest discover -s tests -p 'test_lambdaclass_probe.py' -v`
with `LAMBDACLASS_SMOKE_REQUIRED=1` (so a missing dependency **fails
closed**, not silently skips), runs the probe, and saves its JSON artifact.

The usual insurance CI and scanner are unchanged. Local execution requires
Python 3.12+, a Rust toolchain, `maturin`, and the pinned LambdaClass
dependency. It does not require IBKR credentials.

## Beyond the smoke: what remains for a true backtest

1. Acquire point-in-time, legitimately usable index option bid/ask chains,
   exact SPX/SPXW or XSP contract IDs, settlement conventions and final
   settlement values. The publicly mirrored SPY dataset has uncertain vendor
   provenance and cannot establish SPXW edge.
2. Validate supported multi-leg **credit and debit** spread execution,
   capital and expiry accounting rather than assuming that a single long put
   smoke proves spread correctness.
3. Connect `insurance` research signals as point-in-time, precommitted
   entries without leaking future realized outcomes into the selector.
4. Add conservative commissions, fees, wide-spread scenarios, liquidity
   bounds, margin/financing, and observed expiration settlement.
5. Compare fixed-rule selling, buy-only, model-selected buy/sell and
   no-trade baselines with walk-forward OOS periods, crash windows and
   confidence intervals. Report rejected/missing quotes and trade fill rates.
6. Require independent financial oracles and a risk/settlement audit before
   making anything actionable.

The separate workflow makes it possible to determine whether LambdaClass's
Rust-backed engine actually runs in **our GitHub CI**. Successful synthetic
results must not change the existing `NO TRADE` decision contract.

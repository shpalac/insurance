# Proving an options insurance edge

> **Status: research plan, not a validated strategy or trading system.**
> Today's scanner outputs research rankings only. All candidates remain
> `UNVERIFIED` and the final recommendation is `NO TRADE`.

## The question

Options are not necessarily expensive because implied volatility is high,
nor cheap because their dollar premium is low. An executable price must be
compared with the **appropriately discounted** expected real-world payoff,
net of trading costs, model uncertainty and contract-specific settlement.

For a cash-settled, European-style index option strategy, the conceptual
buy-side valuation is:

```text
Net buy EV = discounted E_P[expiry payout] - executable entry debit - all costs
Net sell EV = executable entry credit - discounted E_P[expiry liability] - all costs
```

In the current prototype the calculation is simplified; it must not be treated
as a production fair value. Contract multipliers, financing, commissions,
slippage and settlement conventions matter.

| Lens | Purpose | Current state |
|:--|:--|:--|
| **P — physical measure** | Distribution of outcomes and actual expiry payouts | Exploratory EWMA + filtered historical simulation |
| **Q — risk-neutral measure** | Distribution and skew embedded in option prices | Not implemented |
| **Historical executability** | Bid/ask, depth, market state and timestamped entry | Partial quote gate; production provenance missing |
| **Evidence for an edge** | Out-of-sample realized net value with uncertainty | Not implemented |

## Promotion gates

Every gate must be independently auditable. A candidate failing any gate
remains exploratory, regardless of positive modeled EV.

1. **Point-in-time data integrity.** Verify underlying and contract bid/ask
   receipt timestamps, entitlements, correct OCC-style contract identity,
   market session, settlement and corporate/event adjustments.
2. **Executable prices and costs.** Price orders at conservative bid/ask,
   explicit per-leg costs and realistically estimated adverse execution;
   capture rejects, partial fills and spread widening in simulation.
3. **P calibration.** Backtest probability forecasts, not only volatility:
   tail quantiles, regime shifts, jump exposure, covered maturities and
   sensitivity to sampling, drift, lookback and model class.
4. **Q sanity checks.** Construct an arbitrage-aware surface using forwards,
   rates, calendar consistency and strike monotonicity; reconcile put/call
   parity and settlement assumptions. This is separate from estimating P.
5. **Out-of-sample option outcomes.** Walk forward over **historical
   point-in-time option quotes**, using only information available before
   entry; realize payoff or modeled exit at a defensible exit quote.
6. **Uncertainty and selection effects.** Quantify model and Monte Carlo
   uncertainty, handle repeated opportunities and correlated outcomes,
   penalize multiple testing/selection, and require a positive conservative
   lower confidence bound on **net** expected value.
7. **Portfolio risk.** Stress crash, gap, illiquidity and regime change;
   evaluate concentration, correlated spreads, drawdown, cash and margin
   needs, portfolio constraints and circuit breakers.
8. **Paper monitoring.** Compare predicted versus observed outcomes and
   track deterioration, false discoveries, execution costs and alerts
   across independent periods before considering any actionable signal.

## Required research output

| Field | Meaning |
|:--|:--|
| Instrument, class, expiry, settlement | Contract identity and payout conventions |
| Strategy and legs | Rights, strikes, direction and cap on nominal spread loss |
| Data provenance and snapshot time | Verified quote receipt and underlying freshness |
| Executable debit or credit | Conservative bid/ask-based entry |
| Modeled expected net P&L | Point estimate under the chosen P model |
| Confidence interval / lower bound | Uncertainty and selection-aware conservative bound |
| Tail loss and worst-case capital | Stress exposure, not just probability of profit |
| Rejection reason | Data, execution, risk or statistical validation failed |
| Research classification | `UNVERIFIED` until all evidence gates pass |

## Acceptance milestones

The implementation exists today for deterministic quote gates, simple strategy
construction, a prototype P sampler, exploratory ranking and negative-control
fixture verification. The remaining gates require new data and independent
tests. See the [README roadmap](../README.md#roadmap) and
[market-data operations](market-data-operations.md).

This project is **not** a profitability claim, signal service or financial
advice. Do not promote hypothetical payoffs to live-performance statistics.

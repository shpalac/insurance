"""Point-in-time volatility-model diagnostic; NOT an option-strategy P&L backtest."""

import math
import statistics

from insurance.core import daily_returns, ewma_sigma


def walk_forward_volatility(closes: list[float], lookback: int = 120) -> dict:
    returns = daily_returns(closes)
    if lookback < 30 or len(returns) < lookback + 20:
        raise ValueError("Insufficient independent out-of-sample observations")
    observations = []
    for i in range(lookback, len(returns)):
        sigma = ewma_sigma(returns[max(0, i - lookback):i], 0.94)
        actual = returns[i]
        observations.append((sigma, actual))
    qlike = statistics.mean(
        math.log(max(sigma * sigma, 1e-12)) + actual * actual / max(sigma * sigma, 1e-12)
        for sigma, actual in observations
    )
    interval = sum(abs(actual) <= 1.96 * sigma for sigma, actual in observations) / len(observations)
    return {
        "status": "VOLATILITY_DIAGNOSTIC_ONLY",
        "out_of_sample_days": len(observations),
        "normal_95pct_coverage": round(interval, 4),
        "qlike": round(qlike, 6),
        "supports_trade_recommendations": False,
        "note": "No historical point-in-time option bid/ask chains or realized strategy fills.",
    }

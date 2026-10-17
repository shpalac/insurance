"""Deterministic payout research. No trading functionality or order API exists."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import math
import random
import statistics
from typing import Any

MULTIPLIER = 100
SUPPORTED_ROOTS = {"SPX", "SPXW", "XSP"}
SUPPORTED_SETTLEMENTS = {"PM", "AM"}


@dataclass(frozen=True)
class Settings:
    min_dte: int = 7
    max_dte: int = 90
    prefer_min_dte: int = 20
    prefer_max_dte: int = 60
    max_quote_age_seconds: int = 30
    min_bid_size: int = 1
    min_ask_size: int = 1
    max_relative_spread: float = 0.25
    min_daily_returns: int = 120
    simulations: int = 2500
    ewma_decay: float = 0.94
    max_spread_width_xsp: float = 10.0
    max_spread_width_spx: float = 100.0
    max_loss_dollars: float = 1000.0
    commission_per_contract: float = 1.50
    extra_slippage_per_leg: float = 0.05
    risk_free_rate: float = 0.04

    def __post_init__(self) -> None:
        if not 0 < self.ewma_decay < 1 or self.simulations < 100:
            raise ValueError("Invalid simulation configuration")
        if not 7 <= self.min_dte <= self.max_dte <= 365:
            raise ValueError("Invalid expiry range")
        if self.max_loss_dollars <= 0:
            raise ValueError("Maximum loss must be positive")


@dataclass(frozen=True)
class Quote:
    root: str
    trading_class: str
    expiration: date
    settlement: str
    right: str
    strike: float
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    quote_time: datetime | None
    market_data_status: str
    multiplier: int = MULTIPLIER

    @classmethod
    def from_dict(cls, item: dict[str, Any]) -> Quote:
        return cls(
            root=str(item["root"]).upper(),
            trading_class=str(item["trading_class"]).upper(),
            expiration=date.fromisoformat(item["expiration"]),
            settlement=str(item["settlement"]).upper(),
            right=str(item["right"]).upper(),
            strike=float(item["strike"]),
            bid=float(item["bid"]),
            ask=float(item["ask"]),
            bid_size=int(item["bid_size"]),
            ask_size=int(item["ask_size"]),
            quote_time=parse_time(item["quote_time"]) if item.get("quote_time") else None,
            market_data_status=str(item["market_data_status"]).upper(),
            multiplier=int(item.get("multiplier", MULTIPLIER)),
        )

    def problems(self, as_of: datetime, config: Settings) -> list[str]:
        problems = []
        dte = (self.expiration - as_of.date()).days
        if self.root not in SUPPORTED_ROOTS or self.trading_class not in SUPPORTED_ROOTS:
            problems.append("UNSUPPORTED_ROOT")
        if self.settlement not in SUPPORTED_SETTLEMENTS:
            problems.append("UNKNOWN_SETTLEMENT")
        if self.trading_class == "SPX" and self.settlement != "AM":
            problems.append("SPX_SETTLEMENT_MISMATCH")
        if self.trading_class in {"SPXW", "XSP"} and self.settlement != "PM":
            problems.append("PM_SETTLEMENT_MISMATCH")
        if self.right not in {"P", "C"} or self.multiplier != MULTIPLIER:
            problems.append("CONTRACT_MISMATCH")
        if not config.min_dte <= dte <= config.max_dte:
            problems.append("DTE_OUT_OF_RANGE")
        if self.market_data_status != "REALTIME":
            problems.append("NOT_REALTIME")
        if self.quote_time is None:
            problems.append("MISSING_QUOTE_TIME")
        else:
            age = (as_of - self.quote_time).total_seconds()
            if not 0 <= age <= config.max_quote_age_seconds:
                problems.append("STALE_OR_FUTURE_QUOTE")
        if not all(math.isfinite(x) for x in (self.strike, self.bid, self.ask)):
            problems.append("NONFINITE_PRICE")
        elif self.strike <= 0 or self.bid < 0 or self.ask <= 0 or self.bid > self.ask:
            problems.append("INVALID_OR_CROSSED_QUOTE")
        elif (self.ask - self.bid) / max(self.ask, 0.01) > config.max_relative_spread:
            problems.append("WIDE_MARKET")
        if self.bid_size < config.min_bid_size or self.ask_size < config.min_ask_size:
            problems.append("INSUFFICIENT_DEPTH")
        return problems


@dataclass(frozen=True)
class Strategy:
    category: str
    name: str
    short: Quote | None
    long: Quote

    @property
    def legs(self) -> tuple[Quote, ...]:
        return (self.long,) if self.short is None else (self.short, self.long)

    def premium(self) -> float:
        if self.short is None:
            return self.long.ask
        if self.category == "SELL":
            return self.short.bid - self.long.ask
        return self.long.ask - self.short.bid

    def payout(self, terminal: float) -> float:
        def intrinsic(q: Quote) -> float:
            return max(0.0, q.strike - terminal) if q.right == "P" else max(0.0, terminal - q.strike)
        if self.short is None:
            return intrinsic(self.long)
        if self.category == "SELL":
            return intrinsic(self.short) - intrinsic(self.long)
        return intrinsic(self.long) - intrinsic(self.short)

    def maximum(self, costs: float) -> tuple[float, float | None]:
        premium = self.premium() * MULTIPLIER
        if self.short is None:
            max_gain = (self.long.strike * MULTIPLIER - premium - costs) if self.long.right == "P" else None
            return premium + costs, max_gain
        width = abs(self.long.strike - self.short.strike) * MULTIPLIER
        if self.category == "SELL":
            return max(0.0, width - premium) + costs, premium - costs
        return premium + costs, width - premium - costs


def parse_time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone-qualified timestamps required")
    return result.astimezone(timezone.utc)


def daily_returns(closes: list[float]) -> list[float]:
    if len(closes) < 2 or any(not math.isfinite(x) or x <= 0 for x in closes):
        raise ValueError("Need valid positive historical closes")
    return [math.log(b / a) for a, b in zip(closes, closes[1:])]


def ewma_sigma(returns: list[float], decay: float) -> float:
    variance = statistics.pvariance(returns)
    for r in returns:
        variance = decay * variance + (1 - decay) * r * r
    return math.sqrt(max(variance, 1e-12))


def terminal_prices(
    spot: float, closes: list[float], dte: int, config: Settings, seed: int
) -> list[float]:
    if not math.isfinite(spot) or spot <= 0:
        raise ValueError("Spot must be positive")
    returns = daily_returns(closes)
    if len(returns) < config.min_daily_returns:
        raise ValueError("INSUFFICIENT_HISTORY")
    sigma = ewma_sigma(returns, config.ewma_decay)
    # Approximate filtered-historical simulation: resample standardized shocks.
    # Does not establish probability calibration or a validated statistical edge.
    innovations = [(r - statistics.mean(returns)) / max(statistics.pstdev(returns), 1e-9) for r in returns]
    rng = random.Random(seed)
    days = max(1, round(dte * 252 / 365))
    return [
        spot * math.exp(sum(rng.choice(innovations) * sigma for _ in range(days)))
        for _ in range(config.simulations)
    ]


def generate_strategies(quotes: list[Quote], config: Settings) -> list[Strategy]:
    output: list[Strategy] = []
    buckets: dict[tuple, list[Quote]] = {}
    for quote in quotes:
        key = (quote.root, quote.trading_class, quote.expiration, quote.settlement, quote.right, quote.multiplier)
        buckets.setdefault(key, []).append(quote)
        output.append(Strategy("BUY", f"Long {quote.right}", None, quote))
    for key, members in buckets.items():
        members.sort(key=lambda q: q.strike)
        max_width = config.max_spread_width_xsp if key[0] == "XSP" else config.max_spread_width_spx
        for i, lower in enumerate(members):
            for higher in members[i + 1:]:
                if higher.strike - lower.strike > max_width:
                    break
                if lower.right == "P":
                    output.extend((
                        Strategy("SELL", "Put credit spread", higher, lower),
                        Strategy("BUY", "Put debit spread", lower, higher),
                    ))
                else:
                    output.extend((
                        Strategy("SELL", "Call credit spread", lower, higher),
                        Strategy("BUY", "Call debit spread", higher, lower),
                    ))
    return output


def compute_candidate(strategy: Strategy, terminals: list[float], config: Settings) -> dict[str, Any] | None:
    premium = strategy.premium()
    if premium <= 0:
        return None
    costs = len(strategy.legs) * (2 * config.commission_per_contract + config.extra_slippage_per_leg * MULTIPLIER)
    max_loss, max_gain = strategy.maximum(costs)
    if max_loss > config.max_loss_dollars or max_loss <= 0:
        return None
    payouts = [strategy.payout(terminal) * MULTIPLIER for terminal in terminals]
    premium_dollars = premium * MULTIPLIER
    profits = [
        (premium_dollars - payout - costs if strategy.category == "SELL"
         else payout - premium_dollars - costs)
        for payout in payouts
    ]
    sorted_profits = sorted(profits)
    expected_profit = statistics.mean(profits)
    expected_payout = statistics.mean(payouts)
    tail_count = max(1, len(profits) // 20)
    expected_shortfall = statistics.mean(sorted_profits[:tail_count])
    gain_to_risk = expected_profit / max_loss
    liquidity = max(0.0, 1.0 - max((q.ask - q.bid) / max(q.ask, 0.01) for q in strategy.legs))
    # Descriptive score only. No evidence of true statistical significance.
    ev_component = 30 * max(0.0, min(1.0, gain_to_risk / 0.2))
    risk_component = 20 * max(0.0, 1.0 + expected_shortfall / max_loss)
    score = round(ev_component + risk_component + 15 * liquidity)
    first = strategy.legs[0]
    return {
        "category": strategy.category,
        "strategy": strategy.name,
        "root": first.root,
        "trading_class": first.trading_class,
        "expiration": first.expiration.isoformat(),
        "dte": None,
        "legs": [
            {"action": ("SELL" if leg == strategy.short else "BUY"), "right": leg.right,
             "strike": leg.strike, "bid": leg.bid, "ask": leg.ask,
             "quote_time": leg.quote_time.isoformat() if leg.quote_time else None}
            for leg in strategy.legs
        ],
        "premium_per_unit": round(premium, 4),
        "expected_payout_usd": round(expected_payout, 2),
        "expected_profit_usd": round(expected_profit, 2),
        "probability_of_profit": round(sum(p > 0 for p in profits) / len(profits), 4),
        "max_loss_usd": round(max_loss, 2),
        "max_gain_usd": round(max_gain, 2) if max_gain is not None else None,
        "expected_shortfall_95_usd": round(expected_shortfall, 2),
        "expected_return_on_risk": round(gain_to_risk, 5),
        "score": score,
        "ev_confidence_lower_bound": None,
        "confidence": "UNVERIFIED",
        "classification": "UNVERIFIED",
        "reason": "No out-of-sample option-price/payout calibration or model-risk CI",
        "entry_limit": None,
    }


def scan_snapshot(snapshot: dict[str, Any], config: Settings | None = None) -> dict[str, Any]:
    config = config or Settings()
    as_of = parse_time(snapshot["as_of"])
    observations = [Quote.from_dict(item) for item in snapshot.get("options", [])]
    rejected: dict[str, int] = {}
    good: list[Quote] = []
    for quote in observations:
        problems = quote.problems(as_of, config)
        if problems:
            for problem in problems:
                rejected[problem] = rejected.get(problem, 0) + 1
        else:
            good.append(quote)
    # Reject index spots without independent fresh, verified market data.
    checked_roots: dict[str, bool] = {}
    def spot_is_fresh(root: str) -> bool:
        if root not in checked_roots:
            data = snapshot.get("underlyings", {}).get(root, {})
            try:
                spot_time = parse_time(data["spot_time"])
                age = (as_of - spot_time).total_seconds()
                checked_roots[root] = (
                    data.get("market_data_status") == "REALTIME"
                    and 0 <= age <= config.max_quote_age_seconds
                    and math.isfinite(float(data["spot"]))
                    and float(data["spot"]) > 0
                )
            except (KeyError, TypeError, ValueError):
                checked_roots[root] = False
        return checked_roots[root]
    eligible = []
    for q in good:
        if spot_is_fresh(q.root):
            eligible.append(q)
        else:
            rejected["INVALID_UNDERLYING_QUOTE"] = rejected.get("INVALID_UNDERLYING_QUOTE", 0) + 1
    good = list({(q.root, q.trading_class, q.expiration, q.right, q.strike): q for q in eligible}.values())
    strategies = generate_strategies(good, config)
    cache: dict[tuple, list[float] | None] = {}
    opportunities: list[dict[str, Any]] = []
    for strategy in strategies:
        q = strategy.legs[0]
        key = (q.root, q.expiration)
        if key not in cache:
            underlying = snapshot.get("underlyings", {}).get(q.root, {})
            try:
                seed = int(hashlib.sha256(f"{q.root}:{q.expiration}".encode()).hexdigest()[:12], 16)
                cache[key] = terminal_prices(
                    float(underlying["spot"]), underlying["closes"],
                    (q.expiration - as_of.date()).days, config, seed
                )
            except (KeyError, TypeError, ValueError) as exc:
                rejected[str(exc)] = rejected.get(str(exc), 0) + 1
                cache[key] = None
        if cache[key] is None:
            continue
        candidate = compute_candidate(strategy, cache[key], config)
        if candidate is not None:
            candidate["dte"] = (q.expiration - as_of.date()).days
            opportunities.append(candidate)
    sells = sorted(
        (x for x in opportunities if x["category"] == "SELL"),
        key=lambda x: (x["expected_profit_usd"], x["score"]), reverse=True
    )
    buys = sorted(
        (x for x in opportunities if x["category"] == "BUY"),
        key=lambda x: (x["expected_profit_usd"], x["score"]), reverse=True
    )
    # Cannot promote a candidate until point-in-time historical option validation exists.
    return {
        "as_of": as_of.isoformat(),
        "model_version": "p-fhs-ewma-0.1-unvalidated",
        "market_data_eligible": len(good),
        "quotes_received": len(observations),
        "rejection_counts": rejected,
        "supported_opportunities": [],
        "sell_insurance": sells,
        "buy_insurance": buys,
        "recommendation": "NO TRADE",
        "note": "All modeled opportunities are UNVERIFIED; rankings are research-only.",
    }

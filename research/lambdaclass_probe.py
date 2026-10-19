"""Optional LambdaClass compatibility probe using fictional data only.

This does not download historical market data, estimate an edge, or create
orders. The production insurance scanner must never import this module.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile


DATES = (
    "2020-06-01", "2020-06-05", "2020-06-08",
    "2020-06-12", "2020-06-19", "2020-06-22",
    "2020-06-26", "2020-07-01", "2020-07-02",
)
SPOTS = (100.0, 95.0, 90.0, 80.0, 70.0, 60.0, 55.0, 50.0, 50.0)
BIDS = (0.90, 1.50, 2.00, 5.00, 11.00, 20.00, 25.00, 30.00, 30.00)
ASKS = (1.00, 1.60, 2.10, 5.20, 11.30, 20.50, 25.50, 31.00, 31.00)

# Independently derived expected values, see docs/research-lambdaclass.md.
EXPECTED = {
    "initial_nav": 100030.00,
    "entry_nav": 99530.00,
    "crash_day_nav": 101030.00,
    "final_nav": 197530.00,
    "entry_put_contracts": 50,
}


def write_fixture(directory: Path) -> tuple[Path, Path]:
    """Write deterministic synthetic prices in LambdaClass provider schemas."""
    directory.mkdir(parents=True, exist_ok=True)
    stocks_path = directory / "fictional_stocks.csv"
    options_path = directory / "fictional_options.csv"

    stock_fields = (
        "symbol", "date", "open", "close", "high", "low", "volume",
        "adjClose", "adjHigh", "adjLow", "adjOpen", "adjVolume",
        "divCash", "splitFactor",
    )
    with stocks_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=stock_fields)
        writer.writeheader()
        for date, price in zip(DATES, SPOTS):
            writer.writerow({
                "symbol": "XYZ", "date": date,
                "open": price, "close": price, "high": price, "low": price,
                "volume": 1000000,
                "adjClose": price, "adjHigh": price, "adjLow": price,
                "adjOpen": price, "adjVolume": 1000000,
                "divCash": 0.0, "splitFactor": 1.0,
            })

    option_fields = (
        "underlying", "underlying_last", "optionroot", "type",
        "expiration", "quotedate", "strike", "last", "bid", "ask",
        "volume", "openinterest", "impliedvol", "delta", "gamma",
        "theta", "vega", "optionalias",
    )
    with options_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=option_fields)
        writer.writeheader()
        for date, price, bid, ask in zip(DATES, SPOTS, BIDS, ASKS):
            writer.writerow({
                "underlying": "XYZ", "underlying_last": price,
                "optionroot": "XYZ200717P00080000", "type": "put",
                "expiration": "2020-07-17", "quotedate": date,
                "strike": 80.0, "last": bid, "bid": bid, "ask": ask,
                "volume": 1000, "openinterest": 1000,
                "impliedvol": 0.50, "delta": -0.10,
                "gamma": 0.01, "theta": -0.05, "vega": 0.10,
                "optionalias": "XYZ200717P00080000",
            })
    return stocks_path, options_path


def run_probe() -> dict:
    """Run the actual upstream engine; raise on missing SDK or wrong accounting."""
    # Lazy imports keep normal insurance scanner installs dependency-free.
    from options_portfolio_backtester import BacktestEngine
    from options_portfolio_backtester.core.types import Direction, OptionType, Stock
    from options_portfolio_backtester.data.providers import HistoricalOptionsData, TiingoData
    from options_portfolio_backtester.execution.cost_model import NoCosts
    from options_portfolio_backtester.execution.fill_model import MarketAtBidAsk
    from options_portfolio_backtester.strategy.strategy import Strategy
    from options_portfolio_backtester.strategy.strategy_leg import StrategyLeg

    with tempfile.TemporaryDirectory(prefix="insurance-fictional-") as temp:
        stocks_file, options_file = write_fixture(Path(temp))
        stocks = TiingoData(str(stocks_file))
        options = HistoricalOptionsData(str(options_file))
        schema = options.schema

        strategy = Strategy(schema)
        leg = StrategyLeg(
            "leg_1", schema, option_type=OptionType.PUT,
            direction=Direction.BUY,
        )
        leg.entry_filter = (
            (schema.underlying == "XYZ")
            & (schema.dte >= 40)
            & (schema.dte <= 60)
        )
        leg.exit_filter = schema.dte <= 20
        strategy.add_leg(leg)
        strategy.add_exit_thresholds(
            profit_pct=float("inf"), loss_pct=float("inf")
        )

        engine = BacktestEngine(
            {"stocks": 1.0, "options": 0.0, "cash": 0.0},
            initial_capital=EXPECTED["initial_nav"],
            cost_model=NoCosts(),
            fill_model=MarketAtBidAsk(),
        )
        engine.stocks = [Stock("XYZ", 1.0)]
        engine.stocks_data = stocks
        engine.options_data = options
        engine.options_strategy = strategy
        engine.options_budget_pct = 0.05
        engine.assert_invariants = True
        engine.run(rebalance_freq=1, rebalance_unit="BMS")

        balance = engine.balance
        actual = {
            "initial_nav": float(balance["total capital"].iloc[0]),
            "entry_nav": float(balance.loc["2020-06-01", "total capital"]),
            "crash_day_nav": float(balance.loc["2020-06-12", "total capital"]),
            "final_nav": float(balance.loc["2020-07-02", "total capital"]),
            "entry_put_contracts": int(balance.loc["2020-06-01", "options qty"]),
        }
        for key, expected in EXPECTED.items():
            if abs(actual[key] - expected) > 0.01:
                raise AssertionError(
                    f"LambdaClass accounting mismatch for {key}: "
                    f"expected {expected}, got {actual[key]}"
                )
        quantities = engine.trade_log["totals"]["qty"].tolist()
        if quantities != [50, 50]:
            raise AssertionError(
                f"Expected exactly one put purchase and sale of 50 contracts: "
                f"got {quantities}"
            )

    return {
        "status": "SYNTHETIC_ENGINE_COMPATIBILITY_ONLY",
        "engine": "lambdaclass/options_portfolio_backtester",
        "observations": len(DATES),
        "bid_ask_fills": "MarketAtBidAsk",
        "independent_expected": EXPECTED,
        "actual": actual,
        "supports_trade_recommendations": False,
        "recommendation": "NO TRADE",
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_probe()
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

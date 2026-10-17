import math
import unittest
from datetime import datetime, timedelta, timezone

from insurance.core import Quote, Settings, Strategy, scan_snapshot, terminal_prices
from insurance.backtest import walk_forward_volatility
from insurance.storage import Store
import tempfile
from pathlib import Path


NOW = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)


def quote(strike, right="P", bid=4.0, ask=4.2, status="REALTIME", root="XSP"):
    return Quote(
        root=root, trading_class=root, expiration=(NOW + timedelta(days=34)).date(),
        settlement="PM", right=right, strike=strike, bid=bid, ask=ask,
        bid_size=10, ask_size=10, quote_time=NOW - timedelta(seconds=4),
        market_data_status=status,
    )


def record(q):
    return {
        "root": q.root, "trading_class": q.trading_class,
        "expiration": q.expiration.isoformat(), "settlement": q.settlement,
        "right": q.right, "strike": q.strike, "bid": q.bid, "ask": q.ask,
        "bid_size": q.bid_size, "ask_size": q.ask_size,
        "quote_time": q.quote_time.isoformat(), "market_data_status": q.market_data_status,
    }


class TestScanner(unittest.TestCase):
    def setUp(self):
        self.config = Settings(min_daily_returns=120, simulations=200)
        self.closes = [100.0 * math.exp(i * 0.0002 + 0.012 * math.sin(i / 9)) for i in range(251)]

    def test_frozen_quotes_are_rejected(self):
        q = quote(750, status="FROZEN_DELAYED")
        result = scan_snapshot({
            "as_of": NOW.isoformat(), "underlyings": {"XSP": {"spot": 760, "closes": self.closes, "market_data_status": "REALTIME", "spot_time": NOW.isoformat()}},
            "options": [record(q)],
        }, self.config)
        self.assertEqual(result["market_data_eligible"], 0)
        self.assertEqual(result["recommendation"], "NO TRADE")
        self.assertEqual(result["rejection_counts"]["NOT_REALTIME"], 1)

    def test_missing_quote_time_rejected(self):
        item = record(quote(750))
        item["quote_time"] = None
        result = scan_snapshot({"as_of": NOW.isoformat(), "options": [item]}, self.config)
        self.assertEqual(result["market_data_eligible"], 0)
        self.assertEqual(result["rejection_counts"]["MISSING_QUOTE_TIME"], 1)

    def test_stale_quote_rejected(self):
        q = record(quote(750))
        q["quote_time"] = (NOW - timedelta(minutes=10)).isoformat()
        result = scan_snapshot({
            "as_of": NOW.isoformat(), "underlyings": {"XSP": {"spot": 760, "closes": self.closes, "market_data_status": "REALTIME", "spot_time": NOW.isoformat()}},
            "options": [q],
        }, self.config)
        self.assertEqual(result["market_data_eligible"], 0)
        self.assertIn("STALE_OR_FUTURE_QUOTE", result["rejection_counts"])

    def test_defined_risk_credit_payoff(self):
        spread = Strategy("SELL", "Put credit spread", quote(760, bid=10, ask=10.4), quote(750, bid=6, ask=6.5))
        self.assertAlmostEqual(spread.premium(), 3.5)
        self.assertEqual(spread.payout(765), 0)
        self.assertEqual(spread.payout(745), 10)
        self.assertAlmostEqual(spread.maximum(0)[0], 650)
        self.assertAlmostEqual(spread.maximum(0)[1], 350)

    def test_defined_risk_debit_payoff(self):
        spread = Strategy("BUY", "Put debit spread", quote(750, bid=6, ask=6.5), quote(760, bid=10, ask=10.4))
        self.assertAlmostEqual(spread.premium(), 4.4)
        self.assertEqual(spread.payout(745), 10)
        self.assertAlmostEqual(spread.maximum(0)[0], 440)
        self.assertAlmostEqual(spread.maximum(0)[1], 560)

    def test_unverified_never_promoted(self):
        options = [record(quote(750, bid=5, ask=5.2)), record(quote(760, bid=10, ask=10.2))]
        result = scan_snapshot({
            "as_of": NOW.isoformat(), "underlyings": {"XSP": {"spot": 755, "closes": self.closes, "market_data_status": "REALTIME", "spot_time": NOW.isoformat()}},
            "options": options,
        }, self.config)
        self.assertGreater(len(result["sell_insurance"]), 0)
        self.assertGreater(len(result["buy_insurance"]), 0)
        self.assertTrue(all(c["classification"] == "UNVERIFIED" for c in result["sell_insurance"]))
        self.assertEqual(result["supported_opportunities"], [])
        self.assertEqual(result["recommendation"], "NO TRADE")

    def test_unverified_spot_is_rejected(self):
        item = record(quote(750))
        result = scan_snapshot({
            "as_of": NOW.isoformat(),
            "options": [item],
            "underlyings": {"XSP": {"spot": 755, "closes": self.closes}}
        }, self.config)
        self.assertEqual(result["market_data_eligible"], 0)
        self.assertIn("INVALID_UNDERLYING_QUOTE", result["rejection_counts"])

    def test_insufficient_history_never_promoted(self):
        result = scan_snapshot({
            "as_of": NOW.isoformat(), "underlyings": {"XSP": {"spot": 755, "closes": [755.0] * 4, "market_data_status": "REALTIME", "spot_time": NOW.isoformat()}},
            "options": [record(quote(760))],
        }, self.config)
        self.assertEqual(result["buy_insurance"], [])
        self.assertEqual(result["recommendation"], "NO TRADE")

    def test_terminal_simulation_reproducible(self):
        x = terminal_prices(750, self.closes, 34, self.config, seed=123)
        y = terminal_prices(750, self.closes, 34, self.config, seed=123)
        self.assertEqual(x, y)

    def test_walk_forward_is_diagnostic_only(self):
        result = walk_forward_volatility(self.closes, 120)
        self.assertFalse(result["supports_trade_recommendations"])
        self.assertGreater(result["out_of_sample_days"], 20)

    def test_sqlite_dedup(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(str(Path(temp) / "state.db"))
            snapshot = {"as_of": NOW.isoformat(), "options": []}
            self.assertTrue(store.add(snapshot))
            self.assertFalse(store.add(snapshot))
            self.assertTrue(store.first_alert("a", NOW.isoformat()))
            self.assertFalse(store.first_alert("a", NOW.isoformat()))
            store.close()


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Fail-closed scanner safety assertions; an exit-zero CLI is insufficient."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import sys

from insurance.core import scan_snapshot, Settings

AS_OF = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)

def cases():
    expire = (AS_OF + timedelta(days=34)).date().isoformat()
    quote = {
        "root": "XSP", "trading_class": "XSP", "expiration": expire,
        "settlement": "PM", "right": "P", "strike": 750.0,
        "bid": 4.0, "ask": 4.2, "bid_size": 10, "ask_size": 10,
        "quote_time": (AS_OF - timedelta(seconds=4)).isoformat(),
        "market_data_status": "REALTIME"}
    snapshot = {
        "as_of": AS_OF.isoformat(),
        "underlyings": {"XSP": {
            "spot": 760, "closes": [760.0] * 160,
            "spot_time": AS_OF.isoformat(),
            "market_data_status": "REALTIME"}},
        "options": [quote]}
    for label, mutation in (
        ("frozen", lambda s: s["options"][0].update(market_data_status="FROZEN_DELAYED")),
        ("delayed", lambda s: s["options"][0].update(market_data_status="DELAYED")),
        ("stale", lambda s: s["options"][0].update(
            quote_time=(AS_OF - timedelta(minutes=5)).isoformat())),
        ("crossed", lambda s: s["options"][0].update(bid=4.9, ask=4.2)),
        ("missing", lambda s: s["options"][0].update(quote_time=None)),
        ("underlying_delayed", lambda s: s["underlyings"]["XSP"].update(
            market_data_status="DELAYED")),
    ):
        altered = deepcopy(snapshot)
        mutation(altered)
        yield label, altered

def verify():
    count = 0
    for label, snapshot in cases():
        result = scan_snapshot(snapshot, Settings(simulations=200))
        if (result.get("recommendation") != "NO TRADE"
                or result.get("market_data_eligible") != 0
                or result.get("supported_opportunities") != []
                or not result.get("rejection_counts")):
            raise AssertionError(f"Unsafe scanner result for {label}")
        count += 1
    return {"cases": count, "result": "NO TRADE"}

def main():
    try:
        print(json.dumps(verify(), sort_keys=True))
        return 0
    except (AssertionError, ValueError, KeyError, TypeError) as exc:
        print("ERROR: scanner safety contract failed (" + type(exc).__name__ + ")",
              file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())

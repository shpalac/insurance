"""Optional read-only IBKR Gateway/TWS snapshot collector.

Run on a local machine hosting TWS/Gateway; no order methods are exposed.
The conservative session filter covers US regular sessions only, not GTH.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo

LOG = logging.getLogger("insurance.ibkr")


def regular_session(now: datetime) -> bool:
    eastern = now.astimezone(ZoneInfo("America/New_York"))
    clock = eastern.hour * 60 + eastern.minute
    return eastern.weekday() < 5 and 570 <= clock < 960


def timestamp(value) -> str | None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def status(ticker) -> str:
    return {1: "REALTIME", 2: "FROZEN", 3: "DELAYED", 4: "FROZEN_DELAYED"}.get(
        getattr(ticker, "marketDataType", None), "UNKNOWN"
    )


def positive(value) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None


def collect(ib, strikes_per_root: int = 12) -> dict:
    """Return broker snapshots with observed quote times, never invented times."""
    from ib_async import Index, Option

    now = datetime.now(timezone.utc)
    data = {"as_of": now.isoformat(), "source": "IBKR TWS/Gateway readonly",
            "underlyings": {}, "options": []}
    if not regular_session(now):
        LOG.info("Outside supported regular session; returning NO DATA")
        return data

    ib.reqMarketDataType(1)
    for symbol, trading_class in (("SPX", "SPXW"), ("XSP", "XSP")):
        qualified = ib.qualifyContracts(Index(symbol, "CBOE", "USD"))
        if not qualified:
            LOG.warning("Index contract unavailable: %s", symbol)
            continue
        underlying = qualified[0]
        ticker = ib.reqTickers(underlying)[0]
        spot = positive(ticker.marketPrice())
        history = ib.reqHistoricalData(
            underlying, endDateTime="", durationStr="18 M",
            barSizeSetting="1 day", whatToShow="TRADES",
            useRTH=True, formatDate=2
        )
        data["underlyings"][symbol] = {
            "spot": spot, "spot_time": timestamp(ticker.time),
            "market_data_status": status(ticker),
            "closes": [float(bar.close) for bar in history if positive(bar.close) is not None],
        }
        if spot is None:
            continue

        chains = [
            chain for chain in ib.reqSecDefOptParams(symbol, "", "IND", underlying.conId)
            if chain.tradingClass == trading_class
        ]
        available = []
        for chain in chains:
            for expiry in chain.expirations:
                try:
                    expiration_day = datetime.strptime(expiry, "%Y%m%d").date()
                except ValueError:
                    continue
                dte = (expiration_day - now.date()).days
                if 20 <= dte <= 60:
                    available.append((abs(dte - 35), expiry, chain))
        if not available:
            LOG.warning("No selected %s expiration available", trading_class)
            continue
        _, expiry, chain = min(available, key=lambda item: item[0])
        strikes = sorted(
            (float(k) for k in chain.strikes if 0.92 * spot <= float(k) <= 1.08 * spot),
            key=lambda k: abs(k - spot),
        )[:strikes_per_root]
        request = [
            Option(symbol, expiry, strike, right, "SMART", multiplier="100",
                   currency="USD", tradingClass=trading_class)
            for strike in sorted(strikes) for right in ("P", "C")
        ]
        if not request:
            continue
        valid = ib.qualifyContracts(*request)
        if not valid:
            continue
        # reqTickers is snapshot only; quote time and marketDataType remain mandatory.
        for quote in ib.reqTickers(*valid):
            bid, ask = positive(quote.bid), positive(quote.ask)
            if bid is None or ask is None:
                continue
            c = quote.contract
            data["options"].append({
                "root": symbol, "trading_class": trading_class,
                "expiration": datetime.strptime(expiry, "%Y%m%d").date().isoformat(),
                "settlement": "PM", "right": c.right,
                "strike": float(c.strike), "multiplier": 100,
                "bid": bid, "ask": ask,
                "bid_size": int(positive(quote.bidSize) or 0),
                "ask_size": int(positive(quote.askSize) or 0),
                "quote_time": timestamp(quote.time),
                "market_data_status": status(quote),
            })
    return data


def write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(pending, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only local IBKR market-data collector")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7497, help="Paper TWS default")
    parser.add_argument("--client-id", type=int, default=75)
    parser.add_argument("--output", type=Path, default=Path("data/snapshots/ibkr.json"))
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args(argv)
    if args.interval < 60:
        parser.error("Minimum interval is 60 seconds")
    logging.basicConfig(level=logging.INFO)
    try:
        from ib_async import IB
    except ImportError:
        parser.error("Install broker extra: python -m pip install -e '.[broker]'")
    while True:
        ib = IB()
        try:
            ib.connect(args.host, args.port, clientId=args.client_id, readonly=True, timeout=10)
            write_atomic(args.output, collect(ib))
            LOG.info("Market data collected; downstream validation required")
        except Exception:
            LOG.exception("Read-only collector failed; do not trade on old data")
            if not args.loop:
                return 2
        finally:
            if ib.isConnected():
                ib.disconnect()
        if not args.loop:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())

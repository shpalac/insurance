"""Local research loop reading read-only option-market snapshots."""

import argparse
import json
import logging
from pathlib import Path
import sys
import time

from insurance.backtest import walk_forward_volatility
from insurance.core import Settings, scan_snapshot
from insurance.storage import Store

LOGGER = logging.getLogger("insurance")


def run_file(path: Path, store: Store, top: int = 5) -> dict:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    store.add(snapshot)
    result = scan_snapshot(snapshot)
    result["sell_insurance"] = result["sell_insurance"][:top]
    result["buy_insurance"] = result["buy_insurance"][:top]
    # Notification delivery is fail-closed: only SUPPORTED (currently none).
    for candidate in result["supported_opportunities"]:
        fingerprint = json.dumps(candidate, sort_keys=True)
        if store.first_alert(fingerprint, result["as_of"]):
            LOGGER.warning("SUPPORTED_OPPORTUNITY %s", fingerprint)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only index options insurance scanner")
    parser.add_argument("--snapshot", type=Path, help="Normalized market data JSON (broker export)")
    parser.add_argument("--database", default="data/private/research.db")
    parser.add_argument("--interval", type=int, default=300, help="Poll seconds in --loop mode")
    parser.add_argument("--loop", action="store_true", help="Poll the input for changed snapshots")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--volatility-diagnostic", action="store_true")
    args = parser.parse_args(argv)
    if not args.snapshot:
        parser.error("--snapshot is required; no live feed is configured")
    if args.interval < 30 or args.top < 1:
        parser.error("--interval must be >=30 and --top >=1")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = Store(args.database)
    previous = None
    try:
        while True:
            try:
                content = args.snapshot.read_bytes()
                import hashlib
                digest = hashlib.sha256(content).hexdigest()
                if digest != previous:
                    previous = digest
                    snapshot = json.loads(content)
                    if args.volatility_diagnostic:
                        diagnostics = {
                            root: walk_forward_volatility(data["closes"])
                            for root, data in snapshot.get("underlyings", {}).items()
                        }
                        print(json.dumps({"volatility_diagnostics": diagnostics}, indent=2))
                    result = run_file(args.snapshot, store, args.top)
                    print(json.dumps(result, indent=2), flush=True)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                LOGGER.error("Scan failed closed: %s", exc)
                if not args.loop:
                    return 2
            if not args.loop:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        LOGGER.info("Research loop stopped")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Reproducible, read-only README demonstration from a recorded quote fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from insurance.core import scan_snapshot

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "data/observations/2026-10-17-frozen.json"


def summarize(snapshot_path: Path) -> dict[str, Any]:
    """Condense the scanner's real result without inventing sample trades."""
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    result = scan_snapshot(snapshot)
    return {
        "as_of": result["as_of"],
        "data": "recorded frozen/delayed fixture; not live",
        "quotes_received": result["quotes_received"],
        "market_data_eligible": result["market_data_eligible"],
        "rejection_counts": result["rejection_counts"],
        "buy_research_candidates": len(result["buy_insurance"]),
        "sell_research_candidates": len(result["sell_insurance"]),
        "statistically_supported_candidates": len(result["supported_opportunities"]),
        "recommendation": result["recommendation"],
    }


def validate_recorded_fixture(summary: dict[str, Any]) -> None:
    """Fail CI if the documented negative-control fixture stops failing closed."""
    expected = {
        "quotes_received": 4,
        "market_data_eligible": 0,
        "rejection_counts": {
            "NOT_REALTIME": 4,
            "MISSING_QUOTE_TIME": 4,
        },
        "buy_research_candidates": 0,
        "sell_research_candidates": 0,
        "statistically_supported_candidates": 0,
        "recommendation": "NO TRADE",
    }
    for name, expected_value in expected.items():
        if summary.get(name) != expected_value:
            raise ValueError(
                f"README demo contract changed: {name} = "
                f"{summary.get(name)!r} (expected {expected_value!r})"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT,
        help="Local, normalized JSON snapshot (defaults to the recorded fixture)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Assert the bundled fixture's fail-closed contract (CI mode)",
    )
    args = parser.parse_args(argv)

    try:
        summary = summarize(args.snapshot)
        if args.check:
            if args.snapshot.resolve() != DEFAULT_SNAPSHOT.resolve():
                parser.error("--check is only supported for the bundled fixture")
            validate_recorded_fixture(summary)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"README demo failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

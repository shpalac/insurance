"""Fictional bid/ask accounting oracle. Never submits orders."""
from __future__ import annotations
from dataclasses import dataclass

INITIAL_CASH = 10_000.0
CONTRACT_MULTIPLIER = 100
FICTIONAL_QUOTES = (
    ("2026-01-05", 1.00, 1.20, 100.0),
    ("2026-01-06", 1.40, 1.60, 101.0),
    ("2026-01-07", 1.80, 2.00, 102.0),
)

@dataclass(frozen=True)
class Snapshot:
    cash: float
    option_mark: float
    nav: float

def expected_accounting() -> tuple[Snapshot, ...]:
    # Long one fictional option: buy at ask; mark at bid; sell at bid.
    first, second, last = FICTIONAL_QUOTES
    cash = INITIAL_CASH - first[2] * CONTRACT_MULTIPLIER
    return (
        Snapshot(cash, first[1] * CONTRACT_MULTIPLIER,
                 cash + first[1] * CONTRACT_MULTIPLIER),
        Snapshot(cash, second[1] * CONTRACT_MULTIPLIER,
                 cash + second[1] * CONTRACT_MULTIPLIER),
        Snapshot(cash + last[1] * CONTRACT_MULTIPLIER, 0.0,
                 cash + last[1] * CONTRACT_MULTIPLIER),
    )

if __name__ == "__main__":
    print(expected_accounting())

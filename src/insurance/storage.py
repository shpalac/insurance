"""Restart-safe append-only observations and deduplication via SQLite."""

import hashlib
import json
import sqlite3
from pathlib import Path


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS observations (digest TEXT PRIMARY KEY, observed_at TEXT NOT NULL, payload TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS notifications (fingerprint TEXT PRIMARY KEY, emitted_at TEXT NOT NULL)")
        self.db.commit()

    def add(self, snapshot: dict) -> bool:
        payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self.db:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO observations VALUES (?, ?, ?)",
                (digest, snapshot["as_of"], payload),
            )
        return cur.rowcount > 0

    def first_alert(self, fingerprint: str, emitted_at: str) -> bool:
        with self.db:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO notifications VALUES (?, ?)",
                (fingerprint, emitted_at),
            )
        return cur.rowcount > 0

    def close(self) -> None:
        self.db.close()

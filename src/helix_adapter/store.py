# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0

"""Receipt stores for HelixSession persistence.

Two implementations:
    InMemoryReceiptStore  — default, no persistence, lost on GC
    SQLiteReceiptStore    — persistent, WAL mode, cross-session audit trail
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List


class ReceiptStore(ABC):
    @abstractmethod
    def save(self, receipt: dict) -> None: ...

    @abstractmethod
    def get_session(self, session_id: str) -> List[dict]: ...

    @abstractmethod
    def list_sessions(self) -> List[str]: ...

    @abstractmethod
    def delete_session(self, session_id: str) -> None: ...

    def export_session(self, session_id: str, fmt: str = "jsonl") -> str:
        receipts = self.get_session(session_id)
        if fmt == "json":
            return json.dumps(receipts, indent=2, default=str)
        return "\n".join(json.dumps(r, default=str) for r in receipts)


class InMemoryReceiptStore(ReceiptStore):
    def __init__(self):
        self._data: dict[str, list[dict]] = {}

    def save(self, receipt: dict) -> None:
        sid = receipt["session_id"]
        self._data.setdefault(sid, []).append(receipt)

    def get_session(self, session_id: str) -> List[dict]:
        return list(self._data.get(session_id, []))

    def list_sessions(self) -> List[str]:
        return list(self._data.keys())

    def delete_session(self, session_id: str) -> None:
        self._data.pop(session_id, None)


class SQLiteReceiptStore(ReceiptStore):
    def __init__(self, path: str | Path = "~/.helix/sessions.db"):
        self._path = Path(path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS receipts (
                    exchange_id   TEXT PRIMARY KEY,
                    session_id    TEXT NOT NULL,
                    turn          INTEGER NOT NULL,
                    timestamp     TEXT NOT NULL,
                    drift_score   REAL,
                    drift_tier    TEXT,
                    hash          TEXT NOT NULL,
                    chain_hash    TEXT NOT NULL,
                    payload       TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON receipts(session_id, turn)")

    def save(self, receipt: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO receipts
                   (exchange_id, session_id, turn, timestamp, drift_score,
                    drift_tier, hash, chain_hash, payload)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    receipt["exchange_id"],
                    receipt["session_id"],
                    receipt["turn"],
                    receipt["timestamp"],
                    receipt.get("drift_score"),
                    receipt.get("drift_tier"),
                    receipt["hash"],
                    receipt["chain_hash"],
                    json.dumps(receipt, default=str),
                ),
            )

    def get_session(self, session_id: str) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM receipts WHERE session_id=? ORDER BY turn ASC",
                (session_id,),
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def list_sessions(self) -> List[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT session_id FROM receipts GROUP BY session_id ORDER BY MIN(timestamp) DESC"
            ).fetchall()
        return [r["session_id"] for r in rows]

    def delete_session(self, session_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM receipts WHERE session_id=?", (session_id,))

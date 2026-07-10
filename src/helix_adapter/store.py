# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0

"""Receipt stores for HelixSession persistence.

Verification (via verify_receipt) is automatically invoked:
- On every save() (disk-writes for SQLite, in-memory too)
- On get_session() loads (once per process lifetime per session, then trusted in memory)
- On export_session() (for network JSON/JSONL exports)

This turns the Tamper-Evident Custody Layer into an active, automated daemon.
At-rest tampering (direct DB edits) is detected on first load after process start.
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from .receipt import verify_receipt


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
        # Automatically verify on export (network JSON-exports) to enforce active tamper-evidence
        for r in receipts:
            if not verify_receipt(r):
                raise ValueError(
                    f"Tamper-evident verification failed during export for receipt {r.get('exchange_id')}"
                )
        if fmt == "json":
            return json.dumps(receipts, indent=2, default=str)
        return "\n".join(json.dumps(r, default=str) for r in receipts)


class InMemoryReceiptStore(ReceiptStore):
    def __init__(self):
        self._data: dict[str, list[dict]] = {}
        self._verified: set[str] = set()

    def save(self, receipt: dict) -> None:
        if not verify_receipt(receipt):
            raise ValueError(
                f"Tamper-evident verification failed for receipt {receipt.get('exchange_id')}"
            )
        sid = receipt["session_id"]
        self._data.setdefault(sid, []).append(receipt)
        # Since this save was verified, mark the session as verified for this process
        self._verified.add(sid)

    def get_session(self, session_id: str) -> List[dict]:
        if session_id not in self._verified:
            receipts = self._data.get(session_id, [])
            for r in receipts:
                if not verify_receipt(r):
                    raise ValueError(
                        f"Tamper-evident verification failed for receipt {r.get('exchange_id')} on load"
                    )
            self._verified.add(session_id)
        return list(self._data.get(session_id, []))

    def list_sessions(self) -> List[str]:
        return list(self._data.keys())

    def delete_session(self, session_id: str) -> None:
        self._data.pop(session_id, None)
        self._verified.discard(session_id)


class SQLiteReceiptStore(ReceiptStore):
    def __init__(self, path: str | Path = "~/.helix/sessions.db"):
        self._path = Path(path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._verified: set[str] = set()
        self._cache: dict[str, list[dict]] = {}  # verified in-memory copy after first load+verify

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
        if not verify_receipt(receipt):
            raise ValueError(
                f"Tamper-evident verification failed for receipt {receipt.get('exchange_id')}"
            )
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
        # Update in-memory cache if this session was already verified in this process
        sid = receipt["session_id"]
        if sid in self._verified:
            self._cache.setdefault(sid, []).append(receipt)

    def get_session(self, session_id: str) -> List[dict]:
        if session_id in self._verified:
            return list(self._cache.get(session_id, []))

        # First load in this process: verify at-rest data
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM receipts WHERE session_id=? ORDER BY turn ASC",
                (session_id,),
            ).fetchall()
        receipts = [json.loads(r["payload"]) for r in rows]

        for r in receipts:
            if not verify_receipt(r):
                raise ValueError(
                    f"Tamper-evident verification failed for receipt {r.get('exchange_id')} on load (at-rest tampering detected?)"
                )

        self._verified.add(session_id)
        self._cache[session_id] = receipts
        return list(receipts)

    def list_sessions(self) -> List[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT session_id FROM receipts GROUP BY session_id ORDER BY MIN(timestamp) DESC"
            ).fetchall()
        return [r["session_id"] for r in rows]

    def delete_session(self, session_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM receipts WHERE session_id=?", (session_id,))
        self._verified.discard(session_id)
        self._cache.pop(session_id, None)

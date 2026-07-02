# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0

"""Shared SQLite key store — no FastAPI dependency.

API keys are never stored in plaintext. The `key` column holds a SHA-256
hash of the presented key; the plaintext is shown to the operator exactly
once at creation time and cannot be recovered afterward.
"""

import hashlib
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(
    os.environ.get("FOUNDRY_KEYS_DB", Path.home() / "helix" / "keys" / "foundry_keys.db")
)


def hash_key(raw_key: str) -> str:
    """Hash a presented API key for storage/lookup.

    Keys are 128-bit random tokens (see foundry_keygen), so a single
    SHA-256 pass provides ample preimage resistance without a slow KDF.
    """
    return hashlib.sha256(raw_key.encode()).hexdigest()


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key        TEXT PRIMARY KEY,
            node_id    TEXT NOT NULL,
            created    TEXT NOT NULL,
            last_used  TEXT,
            revoked    INTEGER NOT NULL DEFAULT 0,
            note       TEXT
        )
    """)
    conn.commit()
    return conn

# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0

"""API key authentication for Helix Foundry.

Key store: ~/helix/keys/foundry_keys.db (SQLite, WAL mode)
Header:    X-API-Key: hx-<hex>

Usage:
    from foundry_auth import require_key
    @app.post("/chat")
    async def chat(req: ChatRequest, key: dict = Depends(require_key)):
        ...
"""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader
from foundry_db import get_conn, hash_key

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_key(x_api_key: str = Depends(_api_key_header)) -> dict:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")

    key_hash = hash_key(x_api_key)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT key, node_id, created, last_used, revoked, note FROM api_keys WHERE key = ?",
            (key_hash,),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=401, detail="Invalid API key")

        if row["revoked"]:
            raise HTTPException(status_code=403, detail="API key revoked")

        conn.execute(
            "UPDATE api_keys SET last_used = ? WHERE key = ?",
            (datetime.now(timezone.utc).isoformat(), key_hash),
        )
        conn.commit()

        # Never return the key material (the stored value is only a hash anyway).
        return {
            "node_id": row["node_id"],
            "note": row["note"],
        }
    finally:
        conn.close()

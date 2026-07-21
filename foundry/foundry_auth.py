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

import logging
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader
from foundry_db import get_conn, hash_key

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_key(request: Request, x_api_key: str = Depends(_api_key_header)) -> dict:
    api_key = x_api_key

    # If X-API-Key not provided, try Authorization: Bearer header
    if not api_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]  # Extract token after "Bearer "

    if not api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header or Authorization: Bearer token required")

    key_hash = hash_key(api_key)
    conn = get_conn()
    try:
        logger.debug(f"Presented key: {api_key[:8]}...")
        logger.debug(f"Hash: {key_hash[:16]}...")

        row = conn.execute(
            "SELECT key, node_id, created, last_used, revoked, note FROM api_keys WHERE key = ?",
            (key_hash,),
        ).fetchone()

        if row:
            logger.debug(f"Found in DB: node_id={row['node_id']}")
        else:
            logger.debug(f"NOT found in DB. Listing all hashes:")
            all_rows = conn.execute("SELECT key, node_id FROM api_keys").fetchall()
            for r in all_rows:
                logger.debug(f"  {r['key'][:16]}... ({r['node_id']})")

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

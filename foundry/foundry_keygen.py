#!/usr/bin/env python3
# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0

"""Foundry API key management CLI.

python3 foundry_keygen.py --node hermes [--note "Hermes inference node"]
python3 foundry_keygen.py --list
python3 foundry_keygen.py --revoke hx-<hex>
"""

import argparse
import secrets
from datetime import datetime, timezone

from foundry_db import get_conn, hash_key


def generate_key() -> str:
    return "hx-" + secrets.token_hex(16)


def cmd_create(node_id: str, note: str) -> None:
    key = generate_key()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO api_keys (key, node_id, created, last_used, revoked, note) VALUES (?, ?, ?, NULL, 0, ?)",
        (hash_key(key), node_id, now, note or ""),
    )
    conn.commit()
    conn.close()
    print(f"Key created for node '{node_id}':")
    print(f"  {key}")
    print("  Store this — only its hash is kept; it cannot be retrieved after this point.")


def cmd_revoke(key: str) -> None:
    conn = get_conn()
    cur = conn.execute("UPDATE api_keys SET revoked = 1 WHERE key = ?", (hash_key(key),))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        print(f"Key not found: {key}")
    else:
        print(f"Revoked: {key}")


def cmd_list() -> None:
    conn = get_conn()
    rows = conn.execute(
        "SELECT key, node_id, created, last_used, revoked, note FROM api_keys ORDER BY created DESC"
    ).fetchall()
    conn.close()

    if not rows:
        print("No keys.")
        return

    print(f"{'KEY HASH':<20}  {'NODE':<16}  {'STATUS':<8}  {'LAST USED':<26}  NOTE")
    print("-" * 90)
    for r in rows:
        status = "revoked" if r["revoked"] else "active"
        last = r["last_used"] or "never"
        # Only the hash is stored; show a short prefix for identification.
        key_disp = (r["key"][:16] + "…") if len(r["key"]) > 16 else r["key"]
        print(f"{key_disp:<20}  {r['node_id']:<16}  {status:<8}  {last:<26}  {r['note'] or ''}")


def main():
    parser = argparse.ArgumentParser(description="Foundry API key manager")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--node", metavar="NODE_ID", help="Create a new key for this node")
    group.add_argument("--revoke", metavar="KEY", help="Revoke an existing key")
    group.add_argument("--list", action="store_true", help="List all keys")
    parser.add_argument("--note", default="", help="Optional note (used with --node)")
    args = parser.parse_args()

    if args.node:
        cmd_create(args.node, args.note)
    elif args.revoke:
        cmd_revoke(args.revoke)
    elif args.list:
        cmd_list()


if __name__ == "__main__":
    main()

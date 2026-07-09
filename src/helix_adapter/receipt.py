# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Receipt generation — cryptographically anchored exchange records."""

import hashlib
import json
import time
import unicodedata


def _nfc(obj):
    """Recursively normalize string values to Unicode NFC form.

    ROUGHED IN for review (2026-07-08), not yet wired into session.py's turn
    hashing — see receipt_hash_bytes() below for the intended call site.

    Why: hashing already sorts keys (json.dumps(..., sort_keys=True)), which
    handles key-order variance, but does nothing about Unicode normalization
    form. Two strings that read as identical text can serialize to different
    bytes if one arrived pre-composed (e.g. "é") and the other
    decomposed (e.g. "e" + combining acute) — different APIs and platforms
    aren't consistent about which form they emit. That would silently change
    a receipt's hash for content a human would call unchanged, which is
    exactly the failure mode a tamper-evidence system should not have.
    Normalizing to NFC before hashing closes that gap without touching the
    public schema or rejecting any value type.
    """
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {k: _nfc(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_nfc(item) for item in obj]
    return obj


def receipt_hash_bytes(receipt: dict) -> bytes:
    """Canonical bytes for hashing a receipt dict: NFC-normalized, key-sorted,
    UTF-8 encoded JSON. Use this instead of a bare json.dumps(...).encode()
    at any receipt-hashing call site (make_receipt below, and session.py's
    turn/chain hashing) so all receipt hashes are normalized consistently.
    """
    return json.dumps(_nfc(receipt), sort_keys=True, default=str).encode("utf-8")


def make_receipt(
    user_message: str,
    assistant_response: str,
    claims: list[dict],
    model: str = "unknown",
    constitutional_prompt: str | None = None,
    drift_score: float = 0.0,
    drift_method: str = "char",
    temperature: float | None = None,
    cedar_status: dict | None = None,
) -> dict:
    """Create a tamper-evident receipt for a constitutional exchange.

    Args:
        user_message: The original user query.
        assistant_response: The model's full response with epistemic markers.
        claims: Extracted {label, text} claim list.
        model: Model identifier (e.g. "deepseek-chat").
        constitutional_prompt: The prompt text used. Optional, useful for audit.
        drift_score: Computed drift for this exchange.
        drift_method: Drift calculation method used.
        temperature: Model temperature used for this exchange.
        cedar_status: Cedar gate state — active/fail_closed/not_configured.

    Returns:
        A dict with all receipt fields and a SHA-256 hash.
    """
    payload = user_message + assistant_response
    receipt = {
        "exchange_id": hashlib.sha256((payload + str(time.time())).encode()).hexdigest()[:16],
        "timestamp": time.time(),
        "model": model,
        "constitutional_prompt": constitutional_prompt,
        "user_message": user_message,
        "assistant_response": assistant_response,
        "claims": claims,
        "drift_score": round(drift_score, 4),
        "drift_method": drift_method,
        "temperature": temperature,
        "cedar": cedar_status or {"active": False, "status": "not_configured", "error": None},
        "hash": "",
    }
    # Self-hash: the receipt seals itself
    receipt_hash = hashlib.sha256(receipt_hash_bytes(receipt)).hexdigest()
    receipt["hash"] = receipt_hash
    return receipt


def receipt_to_json(receipt: dict, indent: int = 2) -> str:
    """Serialize a receipt to pretty-printed JSON."""
    return json.dumps(receipt, indent=indent, default=str)

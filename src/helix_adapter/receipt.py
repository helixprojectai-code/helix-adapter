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
    """Recursively normalize string values to Unicode NFC form."""
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {k: _nfc(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_nfc(item) for item in obj]
    return obj


def _float_to_fixed_str(o: float) -> str:
    """Convert float to fixed-precision string (per RECEIPT CANONICALIZATION SPEC v1.0).
    Uses 10 decimal places and strips trailing zeros for clean representation.
    """
    s = f"{o:.10f}".rstrip("0").rstrip(".")
    return s


def _prepare_for_canonical(obj):
    """Recursively prepare dict for canonical serialization:
    - NFC strings
    - Floats -> fixed-precision strings (no raw floats in output)
    - Other types passed through
    """
    if isinstance(obj, float):
        return _float_to_fixed_str(obj)
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {k: _prepare_for_canonical(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_prepare_for_canonical(item) for item in obj]
    return obj


def canonicalize(receipt: dict) -> bytes:
    """Produce canonical bytes for a receipt per RECEIPT CANONICALIZATION SPEC v1.0.

    Rules applied:
    - JSON keys sorted lexicographically (Unicode code point order)
    - All strings NFC normalized
    - Zero whitespace outside string values (separators=(',', ':'))
    - Floats converted to fixed-precision strings
    - Timestamps must be RFC3339 nanosecond UTC (caller responsibility)
    - Arrays order preserved
    - Nulls explicit
    - UTF-8 encoded, no BOM
    """
    prepared = _prepare_for_canonical(receipt)
    s = json.dumps(
        prepared,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    )
    return s.encode("utf-8")


def receipt_hash_bytes(receipt: dict) -> bytes:
    """Canonical bytes for hashing. Delegates to canonicalize (SPEC v1.0)."""
    return canonicalize(receipt)


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
    ts = time.time()
    # RFC3339 with nanosecond precision (padded)
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)) + f".{int((ts % 1) * 1_000_000_000):09d}Z"
    receipt = {
        "exchange_id": hashlib.sha256((payload + str(ts)).encode()).hexdigest()[:16],
        "timestamp": timestamp,
        "model": model,
        "constitutional_prompt": constitutional_prompt,
        "user_message": user_message,
        "assistant_response": assistant_response,
        "claims": claims,
        "drift_score": round(drift_score, 4),
        "drift_method": drift_method,
        "temperature": temperature,
        "cedar": cedar_status or {"active": False, "status": "not_configured", "error": None},
        "canonical_version": "1.0",
        "hash": "",
    }
    # Self-hash: the receipt seals itself
    receipt_hash = hashlib.sha256(receipt_hash_bytes(receipt)).hexdigest()
    receipt["hash"] = receipt_hash
    return receipt


def receipt_to_json(receipt: dict, indent: int = 2) -> str:
    """Serialize a receipt to pretty-printed JSON."""
    return json.dumps(receipt, indent=indent, default=str)

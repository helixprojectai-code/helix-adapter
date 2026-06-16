# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Receipt generation — cryptographically anchored exchange records."""

import hashlib
import time
import json


def make_receipt(
    user_message: str,
    assistant_response: str,
    claims: list[dict],
    model: str = "unknown",
    constitutional_prompt: str | None = None,
    drift_score: float = 0.0,
) -> dict:
    """Create a tamper-evident receipt for a constitutional exchange.

    Args:
        user_message: The original user query.
        assistant_response: The model's full response with epistemic markers.
        claims: Extracted {label, text} claim list.
        model: Model identifier (e.g. "deepseek-chat").
        constitutional_prompt: The prompt text used. Optional, useful for audit.
        drift_score: Computed drift for this exchange.

    Returns:
        A dict with all receipt fields and a SHA-256 hash.
    """
    payload = user_message + assistant_response
    receipt = {
        "exchange_id": hashlib.sha256(
            (payload + str(time.time())).encode()
        ).hexdigest()[:16],
        "timestamp": time.time(),
        "model": model,
        "constitutional_prompt": constitutional_prompt,
        "user_message": user_message,
        "assistant_response": assistant_response,
        "claims": claims,
        "drift_score": round(drift_score, 4),
        "hash": "",
    }
    # Self-hash: the receipt seals itself
    receipt_hash = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, default=str).encode()
    ).hexdigest()
    receipt["hash"] = receipt_hash
    return receipt


def receipt_to_json(receipt: dict, indent: int = 2) -> str:
    """Serialize a receipt to pretty-printed JSON."""
    return json.dumps(receipt, indent=indent, default=str)

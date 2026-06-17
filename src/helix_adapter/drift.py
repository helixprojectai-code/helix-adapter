# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Drift calculation — measures how well a response adheres to epistemic markers."""

import re
from .markers import MARKER_PATTERN


def estimate_statements(text: str) -> int:
    """Estimate the number of substantive statements in a response.

    Uses sentence boundaries as the primary unit — each sentence
    should carry an epistemic marker if it makes a substantive claim.
    Falls back to paragraph boundaries if no sentence breaks exist.
    """
    if not text:
        return 0
    # Primary: sentence-level
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if len(sentences) >= 2:
        return max(1, len(sentences))
    # Fall back to paragraph boundaries
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 10]
    if len(paragraphs) >= 2:
        return max(1, len(paragraphs))
    # Last resort: single unit
    return 1


def compute_drift(response: str, claims: list[dict]) -> float:
    """Compute drift score for a single exchange.

    Drift = fraction of estimated statements NOT covered by epistemic markers.
    0.000 = perfectly labeled, 1.000 = completely unlabeled.

    Thresholds:
        < 0.10  — green (healthy)
        0.10–0.17 — yellow (warming)
        > 0.17  — red (drift detected)
    """
    if not response:
        return 0.0

    est = estimate_statements(response)
    claim_count = len(claims)

    # Use whichever is larger so we don't penalize dense labeling
    denominator = max(est, claim_count)
    return max(0.0, 1.0 - (claim_count / denominator))


def compute_running_drift(exchanges: list[dict]) -> float:
    """Compute weighted running drift across multiple exchanges.

    Each exchange dict must have 'assistant_response' and 'claims' keys.
    Longer exchanges contribute more to the average.
    """
    total_drift = 0.0
    total_weight = 0

    for ex in exchanges:
        resp = ex.get("assistant_response", "")
        claims = ex.get("claims", [])
        est = estimate_statements(resp)
        d = compute_drift(resp, claims)
        total_drift += d * est
        total_weight += est

    if total_weight == 0:
        return 0.0
    return total_drift / total_weight

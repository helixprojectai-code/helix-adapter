"""Drift calculation — measures how well a response adheres to epistemic markers."""

import re
from .markers import MARKER_PATTERN


def estimate_statements(text: str) -> int:
    """Estimate the number of substantive statements in a response.

    Uses paragraph boundaries (double newlines) as the unit — each
    paragraph is expected to carry one epistemic marker at its start.
    Falls back to sentence boundaries if no paragraph breaks exist.
    """
    if not text:
        return 0
    # Split on paragraph boundaries first
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 10]
    if len(paragraphs) >= 2:
        return max(1, len(paragraphs))
    # Fall back to sentence-level
    sentences = re.split(r'[.!?]\s+', text)
    return max(1, sum(1 for s in sentences if len(s.strip()) > 10))


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

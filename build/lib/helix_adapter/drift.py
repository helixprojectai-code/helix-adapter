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


def compute_drift(response: str, claims: list[dict], method: str = "char") -> float:
    """Compute drift score for a single exchange.

    Drift = fraction of estimated statements NOT covered by epistemic markers.
    0.000 = perfectly labeled, 1.000 = completely unlabeled.

    Args:
        response: The model's full response text.
        claims: Extracted claim list with 'label' keys.
        method: 'char' (default) — character-weighted: longer unlabeled passages
                contribute more. More granular than sentence-level.
                'sentence' — each sentence is one potential claim.
                'paragraph' — each paragraph is one potential claim (legacy).

    Thresholds:
        < 0.10  — green (healthy)
        0.10–0.17 — yellow (warming)
        > 0.17  — red (drift detected)
    """
    if not response:
        return 0.0

    if method == "char":
        return _char_drift_v2(response, claims)
    if method == "paragraph":
        return _paragraph_drift(response, claims)

    # Default: sentence-level
    return _sentence_drift(response, claims)


def _sentence_drift(response: str, claims: list[dict]) -> float:
    """Sentence-level drift: each sentence = one potential claim."""
    est = estimate_statements(response)
    claim_count = len(claims)
    denominator = max(est, claim_count)
    return max(0.0, 1.0 - (claim_count / denominator)) if denominator else 0.0


def _paragraph_drift(response: str, claims: list[dict]) -> float:
    """Paragraph-level drift: each paragraph = one potential claim. Legacy."""
    if not response:
        return 0.0
    paragraphs = [p.strip() for p in response.split("\n\n") if len(p.strip()) > 10]
    if len(paragraphs) < 2:
        paragraphs = [s for s in re.split(r'[.!?]\s+', response) if len(s.strip()) > 10]
    denom = max(len(paragraphs), len(claims))
    return max(0.0, 1.0 - (len(claims) / denom)) if denom else 0.0


def _char_drift_v2(response: str, claims: list[dict]) -> float:
    """Char-weighted drift: fraction of characters in unlabeled sentences.

    Tags each sentence as labeled or unlabeled, sums characters of
    unlabeled sentences, divides by total characters. More granular than
    sentence-level because it weights responses by length — a 500-char
    verbose paragraph after one marker scores higher drift than a 50-char one.
    """
    if not response:
        return 0.0
    total = len(response)
    if total == 0:
        return 0.0
    sentences = re.split(r'(?<=[.!?])\s+', response)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if not sentences:
        return 0.0
    labeled_chars = 0
    for s in sentences:
        if MARKER_PATTERN.search(s):
            labeled_chars += len(s)
    return max(0.0, 1.0 - (labeled_chars / total))


def compute_running_drift(exchanges: list[dict], method: str = "char") -> float:
    """Compute weighted running drift across multiple exchanges.

    Each exchange dict must have 'assistant_response' and 'claims' keys.
    Longer exchanges contribute more to the average.

    Args:
        exchanges: List of exchange dicts with 'assistant_response' and 'claims'.
        method: Drift calculation method to use (passed to compute_drift).
    """
    total_drift = 0.0
    total_weight = 0

    for ex in exchanges:
        resp = ex.get("assistant_response", "")
        claims = ex.get("claims", [])
        est = estimate_statements(resp)
        d = compute_drift(resp, claims, method=method)
        total_drift += d * est
        total_weight += est

    if total_weight == 0:
        return 0.0
    return total_drift / total_weight

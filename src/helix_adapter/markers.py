# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Epistemic marker extraction — parse [FACT], [REASONED], etc. from model output."""

import re

MARKER_PATTERN = re.compile(
    r"\[(FACT|REASONED|HYPOTHESIS|UNCERTAIN|CONCLUSION)\]",
)


def extract_claims(text: str) -> list[dict]:
    """Parse epistemic markers from model output.

    Returns a list of {label, text} dicts, one per marker found.
    Handles both [MARKER] Content and Content [MARKER] placement.
    """
    if not text:
        return []

    markers = [(m.group(1), m.start(), m.end()) for m in MARKER_PATTERN.finditer(text)]
    if not markers:
        return []

    claims = []
    for i, (label, start, end) in enumerate(markers):
        # Grab segment after the marker
        if i + 1 < len(markers):
            segment = text[end:markers[i + 1][1]]
        else:
            segment = text[end:]

        # Also grab text before the first marker (for content [MARKER] style)
        if i == 0:
            before = text[:start].strip()
            if before and not any(m in before for m in ("[FACT]", "[REASONED]", "[HYPOTHESIS]", "[UNCERTAIN]", "[CONCLUSION]")):
                claims.append({"label": label, "text": before[:200]})

        seg = segment.strip().rstrip(".").strip()
        if seg and seg not in ("", "."):
            claims.append({"label": label, "text": seg[:200]})

    # Deduplicate
    seen = set()
    unique = []
    for c in claims:
        key = (c["label"], c["text"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def count_claims(text: str) -> dict[str, int]:
    """Return a dict mapping marker label -> count for the given text."""
    counts = {}
    for m in MARKER_PATTERN.finditer(text):
        label = m.group(1)
        counts[label] = counts.get(label, 0) + 1
    return counts

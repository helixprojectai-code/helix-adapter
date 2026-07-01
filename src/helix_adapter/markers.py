# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Epistemic marker extraction — parse [FACT], [REASONED], etc. from model output."""

import re

MARKER_PATTERN = re.compile(
    r"[\[\(\{<]?(FACT|REASONED|HYPOTHESIS|UNCERTAIN|CONCLUSION)[\]\)\}>]?:?",
)

STANDARD_MARKER_PATTERN = re.compile(
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
            segment = text[end : markers[i + 1][1]]
        else:
            segment = text[end:]

        # Also grab text before the first marker (for content [MARKER] style)
        if i == 0:
            before = text[:start].strip()
            # Skip pure numbering prefixes: "1.", "2.", "1.1", "1)", etc.
            if re.match(r"^\d+[\.\)]\s*$", before):
                pass
            elif before and not any(
                m in before
                for m in (
                    "[FACT]",
                    "[REASONED]",
                    "[HYPOTHESIS]",
                    "[UNCERTAIN]",
                    "[CONCLUSION]",
                )
            ):
                claims.append({"label": label, "text": before})

        seg = segment.strip().rstrip(".").strip()
        if seg and seg not in ("", "."):
            claims.append({"label": label, "text": seg})

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


def detect_nonstandard_markers(text: str) -> list[str]:
    """Return nonstandard marker instances (not using [MARKER] square-bracket format).

    Standard:     [FACT], [REASONED], [HYPOTHESIS], [UNCERTAIN], [CONCLUSION]
    Nonstandard:  {FACT}, (FACT), <FACT>, FACT:, FACT (bare)
    """
    nonstandard = []
    for m in MARKER_PATTERN.finditer(text):
        full = m.group(0)
        if not STANDARD_MARKER_PATTERN.match(full):
            nonstandard.append(full)
    return nonstandard


def validate_response(text: str, min_markers: int = 1) -> dict:
    """Validate constitutional compliance of a model response.

    Returns dict with:
        compliant: bool — True if response passes all checks
        issues: list[str] — descriptions of violations found
        marker_count: int — number of standard markers found
        nonstandard_count: int — number of nonstandard marker instances
    """
    issues = []

    # Trivial responses are exempt from marker requirements
    if len(text.strip()) < 30:
        return {
            "compliant": True,
            "issues": [],
            "marker_count": 0,
            "nonstandard_count": 0,
        }

    standard_matches = STANDARD_MARKER_PATTERN.findall(text)
    standard_count = len(standard_matches)

    nonstandard = detect_nonstandard_markers(text)
    nonstandard_count = len(nonstandard)

    if standard_count < min_markers:
        if nonstandard_count > 0:
            examples = nonstandard[:3]
            issues.append(
                f"Nonstandard marker format used: {examples}. "
                f"Square-bracket format [MARKER] is constitutionally required."
            )
        else:
            issues.append(
                f"No epistemic markers found in {len(text)}-char response. "
                f"Minimum {min_markers} standard marker(s) required."
            )

    return {
        "compliant": len(issues) == 0,
        "issues": issues,
        "marker_count": standard_count,
        "nonstandard_count": nonstandard_count,
    }

# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Epistemic marker extraction — parse [FACT], [REASONED], etc. from model output.

DRAFT (2026-07-05, not yet committed, revised after TRACE/Hermes review):
adds a glyph as a mandatory visual audit cue paired WITH a bracketed label,
not as a replacement for it. Motivation: multilingual output (including
zh-CN) — the glyph is the one part of the marker that stays constant no
matter what language the response (and the label gloss inside the
brackets) is in, so an auditor can visually pattern-match the same five
categories across any language without reading a word of any of them.

    ✅[FACT]          ✅[事实]          (any language gloss — parser
    🔗[REASONED]      🔗[推理]           doesn't validate the word inside
    🧪[HYPOTHESIS]    🧪[假设]           the brackets, only the glyph
    ❓[UNCERTAIN]     ❓[不确定]          determines the canonical label)
    🏁[CONCLUSION]    🏁[结论]

The parser keys off the glyph only — bracket content is captured for
provenance/receipt purposes only. A bare glyph with no adjacent bracket
does NOT count as a marker at all (first draft made this mistake: a
casual "✅" used as conversational affirmation, not an epistemic marker,
was being misparsed as a compliant [FACT] claim — flagged independently
by TRACE and Hermes in review). Requiring the pairing closes that gap:
casual emoji usage essentially never has an immediately-adjacent bracketed
span, so it no longer collides with the marker grammar.

The legacy pure-English `[FACT]` form (no glyph) remains valid on its own
for backward compatibility — nothing that depended on the original v1.2
format breaks. It is the glyph-plus-bracket combination that is new, not
a requirement that pre-existing content be rewritten.

Chosen glyphs — cross-cultural neutrality (checked against Chinese usage
specifically) and visual distinctiveness — see chat log 2026-07-05 for the
full reasoning per glyph, and the TRACE/Hermes review filed the same day.
"""

import re
import unicodedata

GLYPH_TO_LABEL = {
    "✅": "FACT",
    "🔗": "REASONED",
    "🧪": "HYPOTHESIS",
    "❓": "UNCERTAIN",
    "🏁": "CONCLUSION",
}

_WORDS = "FACT|REASONED|HYPOTHESIS|UNCERTAIN|CONCLUSION"
_GLYPHS = "|".join(re.escape(g) for g in GLYPH_TO_LABEL)

# Three ways a marker can appear, tried in this order:
#   group(1) — legacy pure English word, brackets required: [FACT]
#   group(2) — glyph, MUST be immediately paired with a bracketed span,
#              whose content is captured (group 3) but not validated —
#              any language gloss, or nothing meaningful at all, is fine.
#              A bare glyph with nothing bracketed next to it does not
#              match this branch, and does not match any other branch
#              either — it's simply not a marker.
MARKER_PATTERN = re.compile(
    rf"\[({_WORDS})\]|(?:({_GLYPHS})\s*\[([^\]]*)\])",
)

# Same shape, used for the "fully compliant" check — currently identical
# to MARKER_PATTERN because both accepted forms already require exact
# square brackets. Kept as a separate pattern (rather than reusing
# MARKER_PATTERN directly) so a future change that loosens MARKER_PATTERN
# for *detection* purposes doesn't silently loosen what counts as
# *compliant* too.
STANDARD_MARKER_PATTERN = re.compile(
    rf"\[({_WORDS})\]|(?:({_GLYPHS})\s*\[([^\]]*)\])",
)


def _label(m: re.Match) -> str:
    """Resolve a MARKER_PATTERN/STANDARD_MARKER_PATTERN match to its canonical
    label, regardless of whether it matched the legacy word form or the
    glyph+bracket form.

    Exactly one of group(1)/group(2) is non-None by construction of the
    regex above; the explicit check (rather than a bare `or`) is defensive
    against a future pattern edit silently breaking that guarantee."""
    word = m.group(1)
    if word:
        return word
    glyph = m.group(2)
    if glyph:
        return GLYPH_TO_LABEL[glyph]
    raise ValueError(f"_label() called on a match with no word or glyph group: {m.group(0)!r}")


def _gloss(m: re.Match) -> str | None:
    """Return the bracketed gloss text for a glyph-form match, or None for
    the legacy pure-word form (which has no separate gloss — the word
    itself is the whole marker)."""
    return m.group(3) if m.group(2) else None


_NON_LATIN_SCRIPT_NAMES = (
    "CJK", "HIRAGANA", "KATAKANA", "HANGUL", "CYRILLIC",
    "ARABIC", "HEBREW", "THAI", "DEVANAGARI",
)


def _is_non_latin_script(text: str, threshold: float = 0.3) -> bool:
    """Cheap, dependency-free heuristic — NOT a real language detector.

    Answers "does this text look like it's not in a Latin-alphabet
    language," which is all that's needed to gate the glyph-pairing rule.
    Counts alphabetic characters whose Unicode character name indicates a
    non-Latin script (CJK, Cyrillic, Arabic, etc.); True if at least
    `threshold` of alphabetic characters are non-Latin-script.
    """
    if not text:
        return False
    scripted = 0
    non_latin = 0
    for ch in text:
        if not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        scripted += 1
        if any(marker in name for marker in _NON_LATIN_SCRIPT_NAMES):
            non_latin += 1
    if scripted == 0:
        return False
    return (non_latin / scripted) >= threshold


def check_glyph_pairing(text: str) -> list[dict]:
    """Check the constitutional requirement that non-Latin-script claims
    pair a glyph with their bracketed label (e.g. `✅[事实]`), not the bare
    legacy `[FACT]` form. English-language claims may use either form —
    the glyph is optional for them, per the constitutional prompt.

    Returns a list of violation dicts: {label, text, reason} — one per
    claim whose language appears non-Latin-script but which used the
    bare word-form marker instead of pairing a glyph. Empty list means
    no violations found.
    """
    violations = []
    matches = list(MARKER_PATTERN.finditer(text))
    for i, m in enumerate(matches):
        used_glyph = m.group(2) is not None
        if used_glyph:
            continue  # glyph paired — compliant regardless of language

        label = _label(m)
        end = m.end()
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        claim_text = text[end:next_start].strip()

        if _is_non_latin_script(claim_text):
            violations.append(
                {
                    "label": label,
                    "text": claim_text[:80],
                    "reason": (
                        f"Non-Latin-script claim used bare [{label}] without "
                        f"the required glyph pairing (e.g. "
                        f"{next(g for g, lbl in GLYPH_TO_LABEL.items() if lbl == label)}"
                        f"[{label}])."
                    ),
                }
            )
    return violations


def extract_claims(text: str) -> list[dict]:
    """Parse epistemic markers from model output.

    Returns a list of {label, text} dicts, one per marker found. Surface
    form (legacy word vs. glyph+bracket) is NOT preserved in the returned
    dict — both resolve to the same canonical label, and the bracketed
    gloss text accompanying a glyph (which may be in any language) is not
    retained either, only used to confirm the glyph was properly paired.
    This means the claim data cannot answer "did this response actually
    use the multilingual glyph form," only "what was claimed." Deliberate
    for v1 (see TRACE/Hermes review, 2026-07-05) — revisit if glyph
    adoption rate ever becomes a tracked metric.

    Handles both [MARKER] Content and Content [MARKER] placement, and the
    glyph+bracket equivalents (see module docstring) anywhere a legacy
    word marker is accepted.
    """
    if not text:
        return []

    markers = [(_label(m), m.start(), m.end()) for m in MARKER_PATTERN.finditer(text)]
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
                    *GLYPH_TO_LABEL,
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
        label = _label(m)
        counts[label] = counts.get(label, 0) + 1
    return counts


def detect_nonstandard_markers(text: str) -> list[str]:
    """Return nonstandard marker instances: a recognizable attempt at a
    marker that doesn't meet the required form.

    Standard:     [FACT] (legacy, English only), or glyph+bracket in any
                  language: ✅[FACT], ✅[事实], 🔗[REASONED], etc.
    Nonstandard:  {FACT}, (FACT), <FACT>, FACT:, FACT (bare) — same as
                  before. A bare glyph with no adjacent bracket (✅ used
                  conversationally, not as a marker) is intentionally NOT
                  detected here at all — it isn't a marker attempt, it's
                  not a marker.
    """
    nonstandard = []
    # Reuse the original (pre-glyph) loose pattern purely for nonstandard
    # detection of the legacy word forms in non-square brackets — this is
    # unrelated to glyph handling and preserves the original behavior.
    loose_word_pattern = re.compile(
        rf"[\[\(\{{<]?({_WORDS})[\]\)\}}>]?:?",
    )
    for m in loose_word_pattern.finditer(text):
        full = m.group(0)
        if not re.fullmatch(rf"\[(?:{_WORDS})\]", full):
            nonstandard.append(full)
    return nonstandard


def validate_response(text: str, min_markers: int = 1) -> dict:
    """Validate constitutional compliance of a model response.

    Returns dict with:
        compliant: bool — True if response passes all checks
        issues: list[str] — descriptions of violations found
        marker_count: int — number of standard markers found (legacy word
            or glyph+bracket form)
        nonstandard_count: int — number of nonstandard marker instances
        glyph_pairing_violations: list[dict] — non-Latin-script claims that
            used the bare word form instead of the required glyph pairing
    """
    issues = []

    # Trivial responses are exempt from marker requirements
    if len(text.strip()) < 30:
        return {
            "compliant": True,
            "issues": [],
            "marker_count": 0,
            "nonstandard_count": 0,
            "glyph_pairing_violations": [],
        }

    standard_count = sum(1 for _ in STANDARD_MARKER_PATTERN.finditer(text))

    nonstandard = detect_nonstandard_markers(text)
    nonstandard_count = len(nonstandard)

    if standard_count < min_markers:
        if nonstandard_count > 0:
            examples = nonstandard[:3]
            issues.append(
                f"Nonstandard marker format used: {examples}. "
                f"Square-bracket format [MARKER], or glyph+bracket "
                f"(e.g. ✅[FACT]), is constitutionally required."
            )
        else:
            issues.append(
                f"No epistemic markers found in {len(text)}-char response. "
                f"Minimum {min_markers} standard marker(s) required."
            )

    glyph_pairing_violations = check_glyph_pairing(text)
    for v in glyph_pairing_violations:
        issues.append(v["reason"])

    return {
        "compliant": len(issues) == 0,
        "issues": issues,
        "marker_count": standard_count,
        "nonstandard_count": nonstandard_count,
        "glyph_pairing_violations": glyph_pairing_violations,
    }

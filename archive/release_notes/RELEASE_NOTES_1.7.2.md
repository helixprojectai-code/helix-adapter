---
id: release-2026-07-05-v1-7-2
type: release
timestamp: 2026-07-05T00:00:00Z
date: 2026-07-05
author: Stephen Hope
custodian: Steve Hope
substrate: Helix-Adapter
schema_version: v1.0.0
constitutional_version: v1.0
ratification_status: ratified
maturity: published
category: release
status: closed
tags:
  - release
  - v1.7.2
  - glyph-markers
  - multilingual
  - internationalization
severity: medium
routing:
  target_node: SPIDER
  action_required: false
---

# helix-adapter v1.7.2 Release Notes

**Released:** 2026-07-05  
**Branch:** spider-dev → main  
**PyPI:** `pip install helix-adapter==1.7.2`

---

## Overview

v1.7.2 adds a **glyph epistemic marker** as a language-independent visual
audit cue, paired with the existing bracketed marker label rather than
replacing it. Motivation: Helix is targeting multilingual output (including
zh-CN), and a bracket-word marker like `[FACT]` is still an English word no
matter what language the surrounding response is in. A glyph reads
identically in any script.

Nothing changes in the receipt schema, drift/marker-coverage scoring, or
Cedar gating. This only changes what counts as a valid marker on the input
side — `HelixAdapter`, `HelixSession`, `MerkleTree`, and `JointReceipt` are
unaffected.

---

## What's New

### Glyph audit cue, paired with the bracketed label

Each of the five epistemic markers now carries a fixed glyph:

| Marker | Glyph |
|--------|-------|
| `[FACT]` | ✅ |
| `[REASONED]` | 🔗 |
| `[HYPOTHESIS]` | 🧪 |
| `[UNCERTAIN]` | ❓ |
| `[CONCLUSION]` | 🏁 |

```
✅[FACT] The sky is blue.
✅[事实] 天空是蓝色的。
```

The parser keys off the glyph only — the bracketed content is an
unvalidated, human-readable gloss in any language, not translated or
checked by `markers.py`. Legacy pure-English `[FACT]` (no glyph) remains
fully valid on its own; nothing that depended on the pre-1.7.2 format
breaks.

A bare glyph with no adjacent bracket is **not** a marker at all — casual
emoji usage in conversational text (`"Great job! ✅"`) does not collide
with the marker grammar, because the required pairing makes that
structurally impossible rather than merely discouraged.

### Glyph pairing is required — and enforced — for non-English claims

English claims may use either form; the glyph is optional. Non-English
claims (any claim whose text is detected as non-Latin-script) **must**
pair the glyph with the bracketed label — `✅[事实]`, never the bare
`[事实]` alone. This is a real, checked constitutional rule, not just
prompt wording:

- `check_glyph_pairing()` walks marker matches directly and flags any
  non-Latin-script claim that used a bare bracket marker without its
  glyph.
- Language detection is a lightweight, dependency-free Unicode-script
  heuristic (`_is_non_latin_script()` — checks character names for
  CJK/Cyrillic/Arabic/Hebrew/Thai/Devanagari markers). It is not a real
  language detector; it's sufficient to gate this one rule.
- Wired into `validate_response()` alongside every other marker
  compliance rule, surfaced through Foundry's existing `/audit` endpoint
  — no new enforcement path stood up just for this.

### Foundry Guide page updated

The `/guide` marker legend now shows each glyph next to its label and
explains the pairing rule, so the in-dashboard reference matches the
constitutional prompt.

---

## Process Note

This feature went through three review cycles with TRACE and Hermes
before landing — an initial draft (glyph as a standalone alternative to
the bracket word) had a real false-positive gap, independently caught by
both reviewers: a bare ✅ used conversationally was being misparsed as a
compliant `[FACT]` claim. The corrected design (glyph-plus-bracket,
required together) closes that gap by construction, not by patching
around it. Small, iterative features like this one keep surfacing exactly
this kind of thing — worth naming since it's the reason this shipped as
several small reviewed steps rather than one larger one.

---

## Testing

Full suite: **141 passing**, zero regressions. Manually verified: legacy
pure-word markers, glyph+bracket in English, glyph+bracket with real
Simplified Chinese claim text, the false-positive case specifically (bare
emoji in casual text), nonstandard formats (`(FACT)`, `{FACT}`, etc.)
still correctly flagged, and the new glyph-pairing enforcement on both
compliant and non-compliant Chinese claims.

---

## Breaking Changes

None. Fully backward compatible — existing `[FACT]`-style content and
integrations are unaffected.

---

## Upgrade

```bash
pip install --upgrade helix-adapter==1.7.2
```

No configuration or environment changes required.

---

## What's Next

- Consider whether surface form (word vs. glyph) should be recoverable
  from the claim data for glyph-adoption-rate tracking — deliberately not
  preserved in v1.7.2 (see `markers.py` docstring)
- `validate_response()` — the actual compliance gate for all marker rules,
  including this one — is currently only invoked via Foundry's `/audit`
  endpoint, not the live inference path (`adapter.chat()` /
  `session.send()` only call `extract_claims()`). Worth its own look,
  independent of glyphs specifically.

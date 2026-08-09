---
id: release-2026-07-06-v1-7-3
type: release
timestamp: 2026-07-06T00:00:00Z
date: 2026-07-06
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
  - v1.7.3
  - cedar-routing
  - documentation
  - bug-fixes
severity: medium
routing:
  target_node: SPIDER
  action_required: false
---

# helix-adapter v1.7.3 Release Notes

**Released:** 2026-07-06  
**Branch:** spider-dev → main  
**PyPI:** `pip install helix-adapter==1.7.3`

---

## Overview

v1.7.3 is a **Cedar routing and documentation-accuracy release**. The
headline fix makes Foundry's Cedar model-routing policies actually
reachable end-to-end — three of five were either dead code or pointed at
a nonexistent model before this release. The rest of the release closes
gaps found during a docs/terminology audit: the constitutional prompt
itself still had the γ/drift conflation the 1.7.1 cleanup was supposed to
remove, and the dev-onboarding deck had fabricated content that didn't
match anything actually implemented.

No changes to `HelixAdapter`, `MerkleTree`, or the receipt schema.
`HelixSession`'s behavior is unaffected except for the prompt wording fix
below (which changes prompt *text*, not the adapter's logic).

---

## What's Fixed

### Cedar routing — all 5 policies now reachable (previously 2 of 5)

`RoutedChatRequest` and `SessionStartRequest` conflated two different
context fields under one name: `action_type` (Cedar's adversarial/
structured-output routing trigger — `bash`/`execute`/`api_call`/`shell`
or `write_file`/`edit_file`/`apply_patch`/`summarize`) was being fed from
`req.action`, which only ever holds a completely different vocabulary
(`analyze`/`search`/`write_file`/`summarize`/...) used by the static
routing fallback. Since the two vocabularies never overlapped, the
adversarial-pool policy could never fire through the actual API — it
passed unit tests that built context dicts by hand, but was dead code in
production.

Fixed by adding a genuine, separate, optional `action_type` field to both
request models. `cedar_route()` also now drops `None`-valued context
fields before evaluation, so an omitted `action_type` reads as genuinely
absent to Cedar's `context has X` checks, rather than the literal string
`"None"` (the evaluator's `str(v)` fallback for non-primitive types).

All 5 `routing.cedar` policies verified **live** against the running
qwen-intl deployment — not just unit-tested — via temporary, immediately
revoked debug API keys.

### Sovereign pool: qwen-long → qwen-flash

The `sovereign` pool (EU/multilingual locale routing) pointed at
`qwen-long`, which doesn't exist on this DashScope International account
(confirmed via the live model list — 148 models, no `qwen-long`). Tried
`qwen-mt-plus` as a thematically better fit, but it's a translation-only
endpoint that rejects `system`-role messages outright — incompatible
with Helix's adapter, which always injects the constitutional prompt as
a system message. Landed on `qwen-flash`, a general chat-completions
model, verified with a real system+user message pair (not just a bare
user message) before wiring it in.

### Constitutional prompt: γ/drift conflation removed from the prompt itself

The 1.7.1 terminology cleanup touched docs and the Foundry dashboard's
display logic but never touched `prompt.py`'s actual content. Found via
a website audit (the widget page renders the raw constitutional prompt):
rules 4.5 and 7 still used γ and "drift" in contexts that are actually
about marker coverage, not the constitutional convergence tolerance
γ=0.17. This is the prompt every model reads on every turn, so the
conflation was live in production, not just a docs inconsistency.

- "NO SELF-REPORTED DRIFT" / "γ-drift flags" → "NO SELF-REPORTED MARKER
  COVERAGE" / "marker-coverage flags"
- "drift risk (γ)" → "marker-coverage risk"
- "extra scrutiny on γ reporting is required" → "extra scrutiny on
  labeling discipline is required" (also resolves an internal
  contradiction — the model is told not to self-report coverage at all,
  so telling it to scrutinize its own "γ reporting" didn't make sense)

Wording only, no behavioral/logic change.

### PyPI author metadata

`pyproject.toml`'s `authors` entry combined name+email, which PEP 621
collapses into a single `Author-email` field, leaving PyPI's displayed
"Author" field blank. Split into `authors` (name only) and `maintainers`
(name+email) so both fields populate. Verified via local sdist build.
Takes effect on this release — PyPI's already-published 1.7.2 metadata
is immutable and unaffected.

---

## What's New

### RFC 0004: Cedar Model Routing

Foundry's `routing.cedar` model-pool-selection policy layer had almost no
dedicated documentation — a one-line mention in `foundry/README.md` and
nothing distinguishing it from RFC 0003's action-authorization Cedar
Gate, despite being an architecturally separate system (same policy
engine, different question: which model handles this request, vs. is
this action allowed to execute). RFC 0004 documents the schema, all 5
routing policies, the `action`/`action_type` distinction, and the
deliberate fail-open (routing) vs. fail-closed (Cedar Gate) difference.

### Dev onboarding deck: PDF → HTML

The PDF dev-onboarding deck had two content issues found on review: a
fabricated "Drift Telemetry" taxonomy (four categories with invented
automated actions — HALT/REMEDIATE/RESTATE/FLAG — that don't correspond
to anything implemented, later expanded in a subsequent draft to seven
categories using real commits as false corroborating evidence), and a
marker table on one slide missing `[CONCLUSION]` while a different slide
in the same deck had the correct five-marker table. The new HTML version
fixes both: the fabricated telemetry section is gone, replaced with the
actual implemented marker-coverage metric, and the marker table is
complete everywhere. One additional gap found and fixed during review —
the Four Invariants slide was only showing three of four tiles.

---

## Testing

Full suite: **141 passing**, zero regressions. Cedar routing fixes
verified live (not just unit-tested) against the running qwen-intl
deployment for all 5 policies plus the no-context static-default
fallback. Prompt terminology fix verified via live redeploy — the widget
page's rendered constitutional prompt confirmed to show the corrected
text in production.

ruff + black clean on `src/ foundry/`.

---

## Breaking Changes

None. Fully backward compatible.

---

## Upgrade

```bash
pip install --upgrade helix-adapter==1.7.3
```

No configuration or environment changes required. If you deploy Foundry
with a custom `routing.cedar`/`models.json`, double check any policy that
relies on `action_type` — it now reads from a genuinely separate request
field rather than mirroring `action`.

---

## What's Next

- Whether routing decisions should carry richer audit context (which
  specific policy matched, not just the resulting pool) into the
  receipt — raised in review, not yet implemented.
- The `sovereign` pool's original brief (deep regulatory-text analysis,
  full-corpus Merkle auditing) implies a long-context model requirement
  that `qwen-flash` doesn't meet. Revisit pending budget/credit
  availability and confirmation of whether DashScope offers an actual
  long-context successor to `qwen-long`.
- Website doc alignment is ongoing — repo and prompt content are now
  consistent; continue watching for any remaining stale terminology on
  the live site as it's found.

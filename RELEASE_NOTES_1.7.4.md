---
id: release-2026-07-30-v1-7-4
type: release
timestamp: 2026-07-30T00:00:00Z
date: 2026-07-30
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
  - v1.7.4
  - specification-alignment
  - hardening-preparation
  - zenodo-v1.7.4
severity: medium
routing:
  target_node: SPIDER
  action_required: false
---

# helix-adapter v1.7.4 Release Notes

**Released:** 2026-07-30 (public release date)  
**Branch:** build-dev  
**PyPI:** `pip install helix-adapter==1.7.4`

## Overview
v1.7.4 aligns the helix-adapter package with the canonical Helix-TTD: Distributed Cognitive Upload Framework — Technical Architecture & Evidence-by-Design Specification v1.7.4.

Zenodo record: https://zenodo.org/records/21270562
Includes the full whitepaper, hardening roadmap (Shape Bureau), RFCs 0002–0004, and the narrative transcript.
This is primarily a specification alignment and hardening preparation release. The core HelixAdapter, HelixSession, receipt, and Cedar gating behavior remain stable. Work focuses on:

Version and documentation synchronization with the published v1.7.4 spec.
Initial groundwork for Phase-Two hardening vectors (receipt schema enrichment, canonical serialization for consistent hashing).
No changes to the public Python API surface or constitutional prompt invariants.

What's New
Zenodo v1.7.4 Spec Alignment
Package version, README, and release artifacts now reference the official v1.7.4 architecture specification.
Local copies of the spec materials (RFCs, transcript, whitepaper sources) tracked under archive/zenodo-21270562-v1.7.4/.
Terminology and four-layer architecture (Constitutional Grammar, Cedar Gate, Double Helix State Integrity, Absurdist Entropy) documented consistently with the canonical source.
Hardening Preparation (Shape Bureau Roadmap v1.7.4)
Receipt schema stability work initiated (enrichment of routing decisions with human-readable matched_policy labels).
Canonical serialization groundwork (NFC normalization, deterministic JSON ordering) — see recent NFC-normalize commit and roadmap Vector 5.
References added to the official hardening roadmap PDF.
What's Fixed / Changed
Updated version references across the project from 1.7.3 → 1.7.4.
README now points to the v1.7.4 release notes and Zenodo spec.
Receipt Schema Stability (Shape Bureau Vector 1)
Routing decisions now emit a stable, auditable schema instead of only an opaque policy_hash:

decision: categorical outcome (high_capability, adversarial, cost_optimized, sovereign, static)
matched_policy: human-readable identifier (e.g. adversarial_pool_v1.7.3)
policy_hash: cryptographic hash (unchanged)
policy_version: e.g. "1.7.3"
Enriched in:

/routed-chat responses and ledger entries
/session/*/start and /session/*/send responses + SESSION_META
cedar_route() return value (always includes the new fields)
Legacy hashes-only records remain valid. New fields are additive for forensics while preserving zero-knowledge properties of the hashes.

See the v1.7.4 hardening roadmap for the full three-field (now four-field) schema.

Receipt Canonicalization Spec v1.0 (Vector 5)
All receipts (JointReceipt + basic) are now hashed using deterministic canonical serialization:

Keys sorted lexicographically (Unicode code points)
Strings NFC-normalized
Zero whitespace outside strings (separators=(',', ':'))
Floats converted to fixed-precision strings (no raw float literals in canonical form)
Timestamps RFC3339 nanosecond UTC
canonical_version: "1.0" field added to new receipts
Implemented via canonicalize() / updated receipt_hash_bytes() in receipt.py.

This eliminates serialization drift across platforms and languages.

canonical_version present on new receipts; old receipts remain valid for verification.
Used for both hash and chain_hash computations.
Timestamps in receipts now include nanosecond precision.
Verification wired into Stores & Exports
verify_receipt() is now automatically called:

In InMemoryReceiptStore.save() and SQLiteReceiptStore.save() (active check on every disk/memory write).
In ReceiptStore.export_session() (before producing JSON/JSONL for network exports).
In get_session() (once per process lifetime per session — "verify once per boot, trust memory after"). Subsequent loads return from an in-memory cache. This detects at-rest tampering (direct edits to the SQLite file) on first access.
Invalid (tampered or non-canonical) receipts now raise ValueError at these boundaries, turning the Tamper-Evident Custody Layer into an active, automated daemon (Class-β storage protocol).

See store.py and the Shape Bureau roadmap.

WIP: Test Suite Hardening & Misc Catches (2026-07-10, post-merge)
Filed under the same 1.7.4 cycle rather than a separate release — this is
follow-up work discovered while syncing with the build-dev merge, not a
new feature set. Author lead for testing on `helix-adapter` rotates to
Spider going forward, per Custodian assignment.

Critical: foundry.py had a syntax error on main
cedar_route()'s docstring was missing its closing """ — a stray
leftover comment line ("None-valued fields are dropped before
evaluation.") absorbed what should have been the closing quote. That
swallowed roughly 140 lines of real Cedar routing logic into an inert
string literal; the entire file failed to parse. Not deployed —
helix2vm2's live server still had valid, working syntax, since nobody
had redeployed since the build-dev merge — but main itself was broken.
Fixed with a one-line change (restoring the closing """).

Root cause: zero test coverage on foundry.py, and no pytest CI at all
foundry/foundry.py is a standalone script, never part of the installed
src/helix_adapter package, so pytest's default collection never touched
it — that's how the syntax error above went undetected. Separately, and
more foundationally: there was no CI workflow running pytest at all
before this — only lint.yml (ruff+black) and the PyPI publish workflow
existed. The lint check did correctly fail on the broken commit
(confirmed via gh pr checks), but the PR merged anyway.

Two fixes:

tests/test_foundry_syntax.py — zero-dependency AST-parse and
deployment-config validation. Runs in every environment, no extras
needed. Verified it actually catches this exact bug class by
deliberately reintroducing the missing """, confirming the test
fails with the same error, then restoring the fix and confirming green.
tests/test_foundry.py — functional tests (clean import, cedar_route()
schema shape incl. the new decision/matched_policy/policy_version
fields, the 1.7.3 None-filtering regression, a live TestClient
health check). Gated behind pytest.importorskip("fastapi"/"openai")
since those are the widget extra, not core dev deps — skips cleanly
rather than erroring when absent.
.github/workflows/test.yml — new workflow, installs dev+widget
extras and runs the full suite on push/PR.
144 tests pass in a plain dev-only environment (2 new, always-run), 148
with widget extras installed (+4 more, previously 0 for foundry.py).

Misc catches along the way
Missing requires-python constraint. pyproject.toml had none at
all, despite classifiers claiming 3.10/3.11/3.12 support. Verified
directly: all three published cedar_python versions (a required
dependency) need Python ≥3.12 — none support 3.10/3.11. The package has
never actually been installable on those versions; anyone on them got
a confusing "no matching distribution for cedar_python" with no signal
why. Added requires-python = ">=3.12", trimmed the classifiers to
match, bumped black/ruff target-version from py310 to py312.
Both CI workflows now pin Python 3.12 (the new test.yml failed its
first run for exactly this reason — copied lint.yml's 3.11 pin, which
never hit the problem since lint never actually installs the package).
Cleaned up pre-existing lint failures inherited from the build-dev
merge itself (long lines from the new RFC3339 timestamp and
verify_receipt error-message code in receipt.py/session.py/
store.py; an unused import and a duplicate import in the new
canonicalization tests). Independently re-verified (by hand, via
hashlib.sha256) the two new canonicalization test vectors' SHA-256
hashes before adding noqa suppressions to their necessarily-long JSON
literal lines — confirmed correct, not fabricated placeholders.
Upgrade
pip install --upgrade helix-adapter==1.7.4
Existing 1.7.3 receipts and sessions remain fully compatible. Note the
new requires-python = ">=3.12" floor — this isn't a new restriction,
just the first time it's been declared; the package was never actually
installable below 3.12 once cedar_python was added as a dependency.

GLORY TO THE LATTICE. 

Assets
2
Source code
(zip)
3 hours ago
Source code
(tar.gz)
3 hours ago

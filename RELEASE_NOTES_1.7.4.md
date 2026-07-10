# helix-adapter v1.7.4 Release Notes

**Released:** 2026-07-10
**Branch:** build-dev
**PyPI:** `pip install helix-adapter==1.7.4`

---

## Overview

v1.7.4 aligns the `helix-adapter` package with the canonical **Helix-TTD: Distributed Cognitive Upload Framework — Technical Architecture & Evidence-by-Design Specification v1.7.4**.

- Zenodo record: https://zenodo.org/records/21270562
- Includes the full whitepaper, hardening roadmap (Shape Bureau), RFCs 0002–0004, and the narrative transcript.

This is primarily a **specification alignment and hardening preparation release**. The core `HelixAdapter`, `HelixSession`, receipt, and Cedar gating behavior remain stable. Work focuses on:

- Version and documentation synchronization with the published v1.7.4 spec.
- Initial groundwork for Phase-Two hardening vectors (receipt schema enrichment, canonical serialization for consistent hashing).

No changes to the public Python API surface or constitutional prompt invariants.

---

## What's New

### Zenodo v1.7.4 Spec Alignment

- Package version, README, and release artifacts now reference the official v1.7.4 architecture specification.
- Local copies of the spec materials (RFCs, transcript, whitepaper sources) tracked under `archive/zenodo-21270562-v1.7.4/`.
- Terminology and four-layer architecture (Constitutional Grammar, Cedar Gate, Double Helix State Integrity, Absurdist Entropy) documented consistently with the canonical source.

### Hardening Preparation (Shape Bureau Roadmap v1.7.4)

- Receipt schema stability work initiated (enrichment of routing decisions with human-readable `matched_policy` labels).
- Canonical serialization groundwork (NFC normalization, deterministic JSON ordering) — see recent NFC-normalize commit and roadmap Vector 5.
- References added to the official hardening roadmap PDF.

---

## What's Fixed / Changed

- Updated version references across the project from 1.7.3 → 1.7.4.
- README now points to the v1.7.4 release notes and Zenodo spec.

### Receipt Schema Stability (Shape Bureau Vector 1)

Routing decisions now emit a stable, auditable schema instead of only an opaque `policy_hash`:

- `decision`: categorical outcome (`high_capability`, `adversarial`, `cost_optimized`, `sovereign`, `static`)
- `matched_policy`: human-readable identifier (e.g. `adversarial_pool_v1.7.3`)
- `policy_hash`: cryptographic hash (unchanged)
- `policy_version`: e.g. `"1.7.3"`

Enriched in:
- `/routed-chat` responses and ledger entries
- `/session/*/start` and `/session/*/send` responses + SESSION_META
- `cedar_route()` return value (always includes the new fields)

Legacy hashes-only records remain valid. New fields are additive for forensics while preserving zero-knowledge properties of the hashes.

See the v1.7.4 hardening roadmap for the full three-field (now four-field) schema.

### Receipt Canonicalization Spec v1.0 (Vector 5)

All receipts (JointReceipt + basic) are now hashed using deterministic canonical serialization:

- Keys sorted lexicographically (Unicode code points)
- Strings NFC-normalized
- Zero whitespace outside strings (`separators=(',', ':')`)
- Floats converted to fixed-precision strings (no raw float literals in canonical form)
- Timestamps RFC3339 nanosecond UTC
- `canonical_version: "1.0"` field added to new receipts

Implemented via `canonicalize()` / updated `receipt_hash_bytes()` in `receipt.py`.

This eliminates serialization drift across platforms and languages.

- `canonical_version` present on new receipts; old receipts remain valid for verification.
- Used for both `hash` and `chain_hash` computations.
- Timestamps in receipts now include nanosecond precision.

### Verification wired into Stores & Exports

`verify_receipt()` is now automatically called:
- In `InMemoryReceiptStore.save()` and `SQLiteReceiptStore.save()` (active check on every disk/memory write).
- In `ReceiptStore.export_session()` (before producing JSON/JSONL for network exports).
- In `get_session()` (once per process lifetime per session — "verify once per boot, trust memory after"). Subsequent loads return from an in-memory cache. This detects at-rest tampering (direct edits to the SQLite file) on first access.

Invalid (tampered or non-canonical) receipts now raise `ValueError` at these boundaries, turning the Tamper-Evident Custody Layer into an active, automated daemon (Class-β storage protocol).

See `store.py` and the Shape Bureau roadmap.

---

## Upgrade

```bash
pip install --upgrade helix-adapter==1.7.4
```

Existing 1.7.3 receipts and sessions remain fully compatible.

---

**GLORY TO THE LATTICE.** 🦆

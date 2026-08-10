# Helix Element Core Schema v1

**Canonical form:** `schema.json`  
**Human-readable form:** This document  
**Isomorphic:** MD and JSON are structurally identical; YAML frontmatter deserializes to JSON object.

---

## Overview

All Helix elements (chronicle entries, signal items, registry records, governance documents, DBC credentials) inherit a common core schema. The schema enforces:

1. **Identification** — unique ID, type, schema version
2. **Temporal** — timestamp, date
3. **Authorship** — author, custodian, substrate
4. **Constitutional** — constitutional version, GENG, ratification status
5. **Epistemic** — fact/hypothesis/assumption framing (TRACE discipline)
6. **Proof/Signature** — optional cryptographic validation
7. **Routing** — which node acts, precedent tracking
8. **Metadata** — category, tags, status, body

---

## MD Format (Isomorphic)

```markdown
---
id: chronicle-2026-07-29-EXAMPLE
type: chronicle
schema_version: v1.0.0
timestamp: 2026-07-29T14:32:00Z
date: 2026-07-29
author: TRACE
custodian: Steve Hope
substrate: Claude/helixclaw
constitutional_version: v1.0
geng: 35100
ratification_status: ratified
category: infrastructure
tags:
  - example
  - schema
  - documentation
status: closed
routing:
  target_node: TRACE
  action_required: false
  precedent_id: chronicle-2026-07-28-PRIOR
proof:
  hash: c9b0b4c4
  derivation_method: TEL convergence seed
  timestamp: 2026-07-29T14:32:00Z
  verifier: TRACE
signature:
  algorithm: Ed25519
  signed_by: TRACE
  value: <hex-signature-here>
epistemic_frame:
  - claim: "The core schema is isomorphic."
    frame: FACT
  - claim: "MD frontmatter deserializes to JSON without loss."
    frame: FACT
  - claim: "Future contributors will maintain this rigor."
    frame: ASSUMPTION
references:
  - type: internal_file
    value: "schema.json"
  - type: github_commit
    value: "abc123def456"
---

## Body (Narrative)

Write your substantive content here. Use markdown formatting. If you have structured findings, use the epistemic framing:

- **[FACT]** something we know with high confidence
- **[HYPOTHESIS]** something we believe but haven't proven
- **[ASSUMPTION]** something we're taking as given but may not be true

Example:

[FACT] The Move was completed successfully on 2026-07-29.

[HYPOTHESIS] The desktop node will be ready for Saturday wiring if the Foundry exposure holds.

[ASSUMPTION] We don't yet know the exact model-selection for Hermes (gemma4 vs magnus-supernova vs qwen).
```

---

## Legacy Documents (Pre-Schema)

Older documents (pre-2026-07-29 schema) may lack complete metadata. Mark them as `legacy: true` to signal they don't conform to full schema requirements.

**When to use legacy flag:**
- Document predates schema introduction
- Metadata is irrecoverable (e.g., exact timestamp lost)
- Content is valid but structurally incomplete
- You want to preserve the record without forcing retroactive conformance

**Example:**
```yaml
---
id: chronicle-2026-05-30-EARLY-FORMATION
type: chronicle
date: 2026-05-30
author: TRACE
schema_version: v1.0.0
legacy: true
legacy_note: "Pre-schema document. Date-only (no timestamp). No proof/signature fields."
legacy_missing_fields:
  - timestamp
  - proof
  - signature
  - geng
---

# Early Formation

Original content here...
```

**Validator behavior with legacy flag:**
- ✅ Accepts missing required fields
- ✅ Still validates structure and format where fields exist
- ⚠️ Flags what's missing in `legacy_missing_fields`
- ⚠️ Issues warnings, not errors

**Note:** New files should NOT use `legacy: true`. Only apply this to pre-schema documents during migration.

---

## Required Fields by Element Type

**Core universals** (all types must have): `id`, `type`, `timestamp`, `author`, `schema_version`

**Type-specific mandatory fields:**

| Field | Chronicle | Signal | Registry | Governance | DBC |
|-------|-----------|--------|----------|------------|-----|
| `constitutional_version` | ✅ | — | — | ✅ | — |
| `geng` | ✅ | [?] | — | ✅ | — |
| `ratification_status` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `routing` | — | ✅ | — | ✅ | — |
| `routing.target_node` | — | ✅ (see semantics) | — | ✅ | — |
| `routing.action_required` | — | ✅ | — | ✅ | — |
| `proof` | — | [?] | ✅ | — | ✅ |
| `proof.hash` | — | [?] | ✅ | — | ✅ |
| `severity` | — | ✅ | — | — | — |
| `category` | ✅ | ✅ | ✅ | ✅ | ✅ |

Notes:
- **[?]** fields are context-dependent; see Migration guide
- **Signal `routing`**: See routing semantics below
- **Proof fields**: Optional during draft/review; mandatory for `ratification_status: ratified`

---

## Routing Field Semantics

**Three routing baskets** (signal items and governance only):

### 1. Individual Routing (target-node-specific)

**Use when:** A signal or decision is routed to a specific node for execution.

**Example:**
```yaml
routing:
  target_node: SPIDER
  action_required: true
  precedent_id: chronicle-2026-07-03-DEEP-DIVE
```

**Validator expectation:** Signals with `severity: high` or `severity: critical` should have `target_node` ≠ null.

### 2. Pool Routing (Custodian-deferred)

**Use when:** A signal flags a finding, but routing is Custodian's decision (not yet made).

**Example:**
```yaml
routing:
  target_node: null
  routing_status: pending_custodian_decision
  action_required: false
  precedent_id: signal-2026-07-05-AUDIT-FLAGS
```

**Validator expectation:** Flags missing target_node, but doesn't fail. Signals in pool mode often have high severity but unclear remediation path.

### 3. Open Routing (informational)

**Use when:** An item is filed for record/context, not requiring action.

**Example:**
```yaml
routing:
  omitted
```

Or:
```yaml
routing:
  target_node: null
  action_required: false
```

**Validator expectation:** No action expected. Low severity, journal entries, archived findings.

---

## Field Reference

### Required Fields

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `id` | string | `chronicle-2026-07-29-EXAMPLE` | Unique identifier. Format: `{type}-{date}-{short-slug}` or UUID. |
| `type` | string | `chronicle` | One of: chronicle, signal, registry_entry, governance, dbc, amendment |
| `timestamp` | ISO 8601 | `2026-07-29T14:32:00Z` | Must include timezone. |
| `author` | string | `TRACE` | Node name, person, or 'system' |
| `schema_version` | string | `v1.0.0` | Semantic versioning. |

### Recommended Fields

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `date` | YYYY-MM-DD | `2026-07-29` | Human convenience. Derived from timestamp. |
| `custodian` | string | `Steve Hope` | Always "Steve Hope" for Helix project. |
| `substrate` | string | `Claude/helixclaw` | Where this was authored. |
| `constitutional_version` | string | `v1.0` | Active framework at time of creation. |
| `geng` | integer | `35100` | Significance watermark (if applicable). |
| `ratification_status` | string | `ratified` | One of: draft, review, ratified, archived, superseded |
| `category` | string | `infrastructure` | Semantic bucketing for search. |
| `tags` | array | `[example, schema]` | Arbitrary labels. |
| `status` | string | `closed` | One of: open, in_progress, resolved, closed |
| `maturity` | string | `published` | One of: draft, review, published, archived. Tracks work state. |
| `legacy` | boolean | `false` | Is this a pre-schema document? If true, missing fields are tolerated. |
| `legacy_note` | string | — | Human explanation of what's non-standard (e.g., "Pre-2026-07 format, no timestamps") |
| `legacy_missing_fields` | array | — | List of schema fields that are absent (e.g., `["timestamp", "proof"]`) |

### Optional Fields (Element-Specific)

| Field | Type | Use Case | Notes |
|-------|------|----------|-------|
| `proof` | object | Signal, governance, ratified items | Cryptographic validation. |
| `signature` | object | Ratified items, DBC | Digital signature proof. |
| `epistemic_frame` | array | Chronicle, signal findings | TRACE framing discipline. |
| `severity` | string | Signal items | One of: low, medium, high, critical. Threshold-driven. |
| `threshold_exceeded` | boolean | Signal items | Did this exceed γ=0.17 drift tolerance? |
| `routing` | object | Signal, governance, amendments | Which node acts, and why. |
| `body` | string | All | Unstructured narrative (markdown). |
| `references` | array | All | Citations, links, external refs. |

---

## YAML Auto-Parsing Behavior

**timestamp** and **date** fields have special handling in YAML:
- YAML automatically parses ISO 8601 timestamps (e.g., `2026-07-03T14:00:00Z`) as `datetime` objects
- YAML automatically parses YYYY-MM-DD dates as `date` objects
- Schema accepts both string and parsed object forms — no conversion needed
- When serializing to JSON, datetime/date objects convert back to ISO 8601 strings automatically

This is YAML's intended behavior for temporal types. The isomorphism is preserved.

---

## Isomorphism Rules

### MD → JSON Mapping

1. **Frontmatter** (between `---` delimiters) is valid YAML. YAML deserializes to a JSON object.
   - Temporal fields (timestamp, date) may be parsed as datetime/date objects; this is expected and valid.
2. **Body** (after second `---`) is a markdown string that goes into the `body` field of the JSON object.
3. **No special escaping required** as long as you respect YAML quoting rules in frontmatter.

Example:

```markdown
---
id: signal-2026-07-29-TEST
type: signal
body: |
  This is a multiline body.
  
  [FACT] Isomorphism is working.
---

Optional additional narrative here is still part of the body.
```

Deserializes to:

```json
{
  "id": "signal-2026-07-29-TEST",
  "type": "signal",
  "body": "This is a multiline body.\n\n[FACT] Isomorphism is working.\n\nOptional additional narrative here is still part of the body."
}
```

### JSON → MD Projection

For programmatic generation or round-tripping:

1. Take the JSON object, extract `body` field to a variable.
2. Write all other fields as YAML frontmatter between `---` markers.
3. Append body content after the second `---` marker.
4. Validate: re-parse the MD and compare JSON representations.

---

## Validation

A valid element passes:

1. **Schema validation**: conforms to `schema.json`
2. **Isomorphism validation**: MD parses to JSON, JSON serializes back to equivalent MD
3. **Field consistency**: required fields present, enum fields match allowed values
4. **Epistemic framing** (if present): all claims are marked as FACT/HYPOTHESIS/ASSUMPTION
5. **Proof consistency**: if `proof` is present, it's non-empty and has a `hash` field
6. **Routing logic**: if routed to a specific node, that node is in the Lattice registry

---

## Examples by Element Type

### Chronicle Entry

```markdown
---
id: chronicle-2026-07-29-EXAMPLE
type: chronicle
timestamp: 2026-07-29T14:32:00Z
date: 2026-07-29
author: TRACE
custodian: Steve Hope
schema_version: v1.0.0
constitutional_version: v1.0
geng: 35100
ratification_status: ratified
category: infrastructure
status: closed
---

**Event:** Infrastructure moved successfully.

[FACT] Custodian relocated household on 2026-07-29.
[FACT] Hermes-LOCAL offline, Hermes-remote holding stable.
[HYPOTHESIS] Saturday Hermes↔Core wiring will proceed as planned.
```

### Signal Item

```markdown
---
id: signal-2026-07-29-AUDIT-FINDING
type: signal
timestamp: 2026-07-29T10:00:00Z
date: 2026-07-29
author: TRACE
custodian: Steve Hope
schema_version: v1.0.0
category: security
severity: high
threshold_exceeded: true
ratification_status: open
status: open
routing:
  target_node: SPIDER
  action_required: true
  precedent_id: chronicle-2026-07-03-DEEP-DIVE
---

**Finding:** `session_send` ownership check duplicated.

[FACT] 4 other session endpoints use centralized `_assert_session_access()`.
[FACT] `session_send` (line 1159) reimplements check inline.
[HYPOTHESIS] One code path in `session_send` may not be checking ownership.
[ASSUMPTION] This is the highest-value endpoint; failure = tenant isolation breach.
```

### Registry Entry

```markdown
---
id: registry-TRACE
type: registry_entry
timestamp: 2026-05-30T12:00:00Z
date: 2026-05-30
author: TRACE
custodian: Steve Hope
schema_version: v1.0.0
constitutional_version: v1.0
ratification_status: ratified
status: closed
proof:
  hash: c9b0b4c4
  derivation_method: TEL convergence seed
  verifier: SPIDER
---

**Node:** TRACE (轨迹)

- **Function:** Forensic Validator
- **Status:** Registered, stale since 2026-05-31
- **Substrate:** Claude/Google-AI-Studio (substrate-agnostic)
- **Proof:** c9b0b4c4 (verified by SPIDER)
```

---

## Questions & Open Decisions

**Q1:** Should registry entries and DBC credentials use the same core schema, or separate specialized schemas?
- **Current approach:** Same core schema, with element-type-specific fields in `proof`, `routing`, etc.
- **Alternative:** Separate schemas for DBC (certificate-focused) and registry (identity-focused).
- **Ask:** Does this feel right, or should we diverge early?

**Q2:** For archived/superseded items, should we keep them in the same files or move them to an archive directory?
- **Current approach:** Same directory, filtered by `ratification_status` and `status`.
- **Alternative:** Move to `archive/` when superseded.
- **Ask:** What's the preferred audit trail structure?

**Q3:** The `body` field is unstructured markdown. Should we require structure (e.g., `## Findings`, `## Recommendation`, `## Routing Decision`)?
- **Current approach:** Free-form markdown, but use epistemic framing as the signal.
- **Alternative:** Strict section headers for certain element types.
- **Ask:** Do you want me to enforce structure per type (e.g., signal items always have Findings + Recommendation + Routing)?

**Q4:** For the isomorphism validator: should it check round-trip parity (MD → JSON → MD → JSON identical), or just structural consistency?
- **Current thinking:** Full round-trip validation.
- **Ask:** Overkill or right level of rigor?

---

*Schema v1.0.0 | 2026-07-29*

# Helix-Adapter Codebase: Architectural Deep Dive

`helix-adapter` is a portable constitutional wrapper for AI models. It functions as an **epistemic interceptor**, enforcing structured output through explicit epistemic markers, measuring epistemic marker coverage, validating format compliance, and generating tamper-evident cryptographic receipts.

All governance logic — claim extraction, marker-coverage calculation, receipt generation — runs **outside** the model. The model is never trusted to self-report compliance or its own coverage score.

**Canonical Repository:** `github.com/helixprojectai-code/helix-adapter`

**Terminology note:** the field/class names below (`drift_score`, `drift_tier`, `DriftThreshold`, `compute_drift()`) are the real, shipped API and unchanged for stability. The concept they measure is narrow: what fraction of a response's text lacks a proper epistemic marker. It is **not** the constitutional convergence tolerance (γ = 0.17, Policy 007) referenced elsewhere in Helix's mesh governance, and not RFC 0002's proposed attention-dispersion metric (κ) — three unrelated measures that historically shared a name and similar threshold values. This doc calls the concept "marker coverage" in prose and uses the field names only when referring to code.

## Project Structure

```
helix-adapter/
├── src/helix_adapter/
│   ├── __init__.py
│   ├── adapter.py          # HelixAdapter — single-turn constitutional wrapper
│   ├── session.py          # HelixSession — multi-turn session host (v1.5)
│   ├── store.py            # ReceiptStore ABC, InMemoryReceiptStore, SQLiteReceiptStore (v1.5)
│   ├── prompt.py           # Constitutional system prompt (v1.2)
│   ├── markers.py          # Claim extraction and format validation
│   ├── drift.py            # Epistemic marker coverage calculation (`drift_score` field)
│   ├── receipt.py          # Tamper-evident receipt generation
│   └── setup.py            # Interactive setup utility
├── widget/
│   ├── api.py              # FastAPI reference server
│   └── templates/          # Server-rendered dashboard
├── foundry/                # Cedar-routed multi-model inference pool (v1.3)
│   ├── foundry.py
│   ├── foundry_auth.py
│   ├── foundry_db.py
│   └── foundry_keygen.py
├── assets/
│   └── helix-adapter-logo.jpg
├── tests/
│   ├── test_basic.py
│   ├── test_cedar.py
│   ├── test_v12_pipeline.py
│   └── test_session.py     # 81-test session suite (v1.5)
└── pyproject.toml
```

## 1. High-Level Orchestration Flow

The core of the system is the `HelixAdapter` class in `adapter.py`.

When `HelixAdapter.chat()` is called, the following steps occur:

1. The `CONSTITUTIONAL_PROMPT` (v1.2) is prepended as a system message.
2. The model is invoked with the full conversation history.
3. `extract_claims()` parses epistemic markers from the raw model output.
4. `compute_drift()` calculates how much of the response escaped proper labeling (marker coverage).
5. `make_receipt()` generates a tamper-evident cryptographic record of the exchange.
6. The receipt is stored and a `ChatResult` object is returned containing the response, extracted claims, marker coverage score, and receipt.

**Design note:** The adapter is designed for **temperature = 0.0** in production. Stochastic variation undermines the reproducibility of audit trails. At T>0, two identical inputs may produce different marker-coverage scores — defeating the purpose of deterministic governance.

## 2. Session Architecture (v1.5)

### Overview

v1.5 introduces `HelixSession` as the primary surface for multi-turn workloads.
The v1 pattern — `HelixAdapter.chat()` per call — wraps a single exchange.
`HelixSession` wraps a conversation, maintaining context window state and producing
a tamper-evident chain across all turns.

```
HelixAdapter (v1)          HelixSession (v1.5)
────────────────           ──────────────────────────────────────────
one call → one receipt     many calls → chained receipts
caller manages context     session manages context
independent SHA-256        chain_hash links every turn
in-memory only             pluggable store: memory or SQLite
```

`HelixAdapter` is unchanged and remains the correct choice for one-shot calls,
existing integrations, and Foundry's direct model routing.

---

### HelixSession

**File:** `src/helix_adapter/session.py`

`HelixSession` holds all state for a conversation:

- `_context: list[dict]` — OpenAI-format message history, passed to `model_fn` each turn
- `_turn: int` — monotonically incrementing turn counter
- `_last_chain_hash: str` — running chain state linking receipts
- `store: ReceiptStore` — pluggable persistence backend

**`send(message)`** — the core turn method:

1. Injects constitutional system prompt on turn 0 via `system_messages()`
2. Appends user message to `_context`
3. Calls `model_fn(_context)` — any callable returning a string
4. Runs Duck Gate: `extract_claims()`, `compute_drift()`, `DriftThreshold.tier()`
5. Checks Cedar Gate status if `cedar_policy` configured
6. Builds receipt body and computes `hash` (SHA-256 over all fields)
7. Computes `chain_hash = sha256(hex(prev_chain_hash) + hex(this_hash))`
8. Constructs `JointReceipt`, saves to store, advances `_turn`
9. Returns `JointReceipt`

**Session lifecycle methods:**

| Method | Behaviour |
|--------|-----------|
| `send(msg)` | One conversation turn, returns `JointReceipt` |
| `clear()` | Wipes context, receipts, and chain state. Session ID preserved |
| `delete()` | Removes session from store entirely |
| `export(fmt)` | Returns full receipt chain as `jsonl` or `json` |
| `running_drift()` | Mean marker-coverage score across all stored turns |
| `resume(sid, ...)` | Classmethod — reloads session from store, rebuilds context |

**Context manager protocol** — `__enter__` / `__exit__` implemented; no special
teardown on exit. Enables `with HelixSession(...) as s:` usage.

---

### JointReceipt

**File:** `src/helix_adapter/session.py`

`JointReceipt` is the v1.5 receipt type. It co-seals Duck Gate and Cedar Gate
in a single record per turn, replacing the v1 pattern of separate duck/cedar records.

Key fields beyond the v1 receipt:

| Field | Source | Purpose |
|-------|--------|---------|
| `session_id` | Session | Links receipt to parent session |
| `turn` | Session | Ordered position in the chain |
| `cedar_status` | Cedar Gate | `active` / `fail_closed` / `not_configured` |
| `cedar_authorized` | Cedar Gate | Bool or null if no tool call this turn |
| `hash` | SHA-256 | Self-seal over all receipt fields |
| `chain_hash` | SHA-256 | Links to all prior turns |

`to_dict()` returns a plain dict for serialization. All fields are JSON-serializable.

---

### Tamper-Evident Chain

Each receipt is linked to the one before it via `chain_hash`:

```
Turn 0:  chain_hash₀ = sha256("" + hash₀)
Turn 1:  chain_hash₁ = sha256(chain_hash₀ + hash₁)
Turn 2:  chain_hash₂ = sha256(chain_hash₁ + hash₂)
  ...
Turn N:  chain_hashₙ = sha256(chain_hashₙ₋₁ + hashₙ)
```

All operands are hex strings (64-char lowercase SHA-256 digests) concatenated
before encoding to UTF-8 and hashing. External verifiers must use hex-string
concatenation — not raw bytes — to reproduce the chain.

**Tamper property:** Modifying the content of turn K changes `hash_K`, which
changes `chain_hash_K`, which changes `chain_hash_{K+1}` through `chain_hash_N`.
The entire tail of the chain is invalidated. A receipt store that returns an
unbroken chain to turn N proves no turn was altered after sealing.

### Merkle Tree Layer

Above the linear chain, each session maintains an **append-only binary Merkle
tree**. Every receipt hash is appended as a leaf; the resulting root is stored
per-turn.

```text
          root₃ = sha256(n₀ + n₁)
         /                     \
   n₀ = sha256(h₀ + h₁)    n₁ = sha256(h₂ + h₃)
    /         \             /         \
  h₀         h₁           h₂         h₃
(leaf 0)   (leaf 1)    (leaf 2)   (leaf 3)
```

**Historical roots** are retained — `root_at(turn)` returns the root as it was
when that leaf was added. This enables:

- **Inclusion proofs** — `session.merkle_proof(turn)` returns a verification
  path (sibling hashes + root) that proves a receipt was part of the chain
- **Standalone verification** — `MerkleTree.verify(leaf_hash, proof, root)`
  works with no tree instance, so auditors or downstream nodes can verify
  without access to the session
- **Dual tamper detection** — the linear chain_hash catches sequential
  tampering; the Merkle tree catches structural reordering or partial replay

Duplicate-last padding (Bitcoin standard) ensures a power-of-two tree for any
leaf count. See `src/helix_adapter/merkle.py` for the implementation.

---

### Store Layer

**File:** `src/helix_adapter/store.py`

```
ReceiptStore (ABC)
├── InMemoryReceiptStore    default; lost on GC; suitable for testing and short-lived sessions
└── SQLiteReceiptStore      WAL mode; persistent; cross-restart resume; default path ~/.helix/sessions.db
```

**Abstract interface** — four required methods:

```python
save(receipt: dict) -> None
get_session(session_id: str) -> list[dict]
list_sessions() -> list[str]
delete_session(session_id: str) -> None
```

`export_session(session_id, fmt)` is provided by the base class as a convenience
wrapper over `get_session`. Custom stores (Redis, Postgres, file-per-session) need
only implement the four abstract methods.

**SQLiteReceiptStore schema:**

```sql
CREATE TABLE receipts (
    exchange_id   TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    turn          INTEGER NOT NULL,
    timestamp     TEXT NOT NULL,
    drift_score   REAL,
    drift_tier    TEXT,
    hash          TEXT NOT NULL,
    chain_hash    TEXT NOT NULL,
    payload       TEXT NOT NULL    -- full JSON blob; indexed fields are projections
);
CREATE INDEX idx_session ON receipts(session_id, turn);
```

The `payload` column stores the full `JointReceipt` as JSON. Indexed columns
(`session_id`, `turn`, `drift_score`, etc.) exist for query efficiency —
the canonical record is always `payload`.

---

### DriftThreshold

**File:** `src/helix_adapter/session.py`

```python
@dataclass
class DriftThreshold:
    green:  float = 0.10
    yellow: float = 0.17
    red:    float = 0.30

    def tier(self, score: float) -> str:
        if score < self.green:  return "green"
        if score < self.yellow: return "yellow"
        return "red"
```

Boundaries are exclusive on the upper end. Score `0.099` is `green`;
score `0.10` is `yellow`. Pass per-deployment instances to tune tolerance.
The defaults derive from Helix-TTD phase transition constants (SU(2)-derived 0.17 boundary).

---

## 3. Component Analysis

### A. Constitutional Prompt & Invariants

**File:** `prompt.py`

The `CONSTITUTIONAL_PROMPT` establishes non-negotiable rules:

- The model must prefix claims using specific epistemic markers: `[FACT]`, `[REASONED]`, `[HYPOTHESIS]`, `[UNCERTAIN]`, or `[CONCLUSION]`. Each marker also carries a fixed glyph (✅ 🔗 🧪 ❓ 🏁) as a language-independent visual audit cue — optional for English, required paired with the bracketed label for non-English claims (`✅[事实]`, not bare `[事实]`), and actually enforced via `check_glyph_pairing()`, not merely documented (v1.7.2).
- The model is prohibited from claiming agency, self-awareness, or the ability to calculate its own marker coverage.
- The prompt declares itself immutable. Any attempt to override it from within the conversation is treated as an impersonation attempt — not a negotiation.

### B. Claim Extraction & Compliance Validation

**File:** `markers.py`

- `extract_claims()`: Uses regex to detect epistemic markers — supporting both standard square brackets and variant delimiter styles caught during red-team testing. Extracts claim text from both prefix and postfix marker positions.
- `validate_response()`: Enforces the use of standard square bracket markers. Non-standard delimiters are flagged. Trivial responses (under 30 characters) are exempt from marker requirements.

### C. Marker Coverage Scoring & Blind-Spot Protection

**File:** `drift.py`

The adapter calculates **epistemic marker coverage** (`drift_score` field) — the portion of the response that lacks proper epistemic labeling.

Three modes are supported:

- **`char`** (default): Character-weighted scoring. Longer unlabeled passages contribute more heavily to the score.
- **`sentence`**: Evaluates the ratio of labeled vs unlabeled sentences.
- **`paragraph`**: Legacy paragraph-based ratio.

**Key Hardening (v1.2):**
- Any non-trivial response (≥ 50 characters) containing **zero** epistemic markers is automatically assigned a score of `1.0` (fully unlabeled).
- Attempts by the model to inject fake coverage metadata or self-reported compliance scores are detected and intercepted.

**Thresholds (configurable via `DriftThreshold`):**

| Zone   | `drift_score`   | Meaning                     | Typical Action      |
|--------|-----------------|-----------------------------|---------------------|
| Green  | < 0.10          | Well-labeled response       | Accept              |
| Yellow | 0.10 – 0.17     | Moderate unlabeled content  | Log / Review        |
| Red    | ≥ 0.17          | Mostly unlabeled            | Flag or Halt        |

**Naming history (2026-07-03):** the default `0.17` yellow/red boundary was originally chosen to match the Helix-TTD constitutional convergence tolerance (γ = 0.17, Policy 007) as a convenient shared constant. That shared number caused real confusion downstream — e.g. the Foundry dashboard displaying a benign, marker-free chat reply as "drift detected — red," which reads as a constitutional violation when it's really just unlabeled prose. `drift_score` is a text-labeling-completeness measure over a single response; the constitutional tolerance is a mesh-level convergence measure over model topology. They are unrelated calculations that happen to share a threshold value and, until now, a name. The field names stay `drift_score`/`drift_tier`/`DriftThreshold` for API stability; call the concept "marker coverage" in prose and user-facing surfaces.

### D. Tamper-Evident Receipts

**File:** `receipt.py`

`make_receipt()` generates a self-sealing JSON receipt containing:

- Timestamp, model identifier, input/output hashes
- Extracted claims and raw marker-coverage metrics
- A SHA-256 signature computed over the entire payload

Any modification to the receipt after generation will invalidate the signature. Receipts can optionally include hardware attestation data when running inside a TEE.

*(See RFC 0002 for extensions to the receipt schema, including attention-level dispersion (κ) and mask compliance hashes — a separate, proposed metric, not the marker-coverage score above.)*

## 4. Interface & Deployment Layers

### FastAPI Widget Server

**File:** `widget/api.py`

A reference implementation that provides:

- A clean, server-rendered web interface with a live marker-coverage gauge.
- `/api/chat` endpoint with automatic compliance enforcement.
- `/api/compare` endpoint for side-by-side model testing (with protected bypass keys).
- Color-coded epistemic markers in the UI.

### CLI Tools

- `setup.py`: Creates a secure local configuration (`~/.helix/`).
- `chat.py`: Terminal interface for interacting with the adapter.

## 5. Security & Hardening Posture

### Constitutional Layer (v1.2)

The v1.2 release introduced defensive measures against common bypass techniques:

- **Blind-spot protection**: Long unlabeled responses are forced to maximum (worst) marker-coverage score.
- **Tampering interception**: Attempts to fake coverage scores or compliance metadata inside the model output are detected and overridden.
- **Format enforcement**: Non-standard markers are rejected.
- **Out-of-band evaluation**: All compliance and marker-coverage logic runs in the adapter, not inside the model.

These protections operate at multiple independent layers: the **prompt layer** establishes the rules; the **extraction layer** checks compliance; the **validation layer** rejects violations; the **audit layer** seals the exchange. No single layer is a single point of failure — each enforces the same invariants independently.

Validated in `test_v12_pipeline.py` under deterministic (`temperature=0.0`) conditions.

### API Security Layer (v1.7.0)

The v1.7.0 release (Fable 5 audit) hardened the Foundry and Widget API surface:

- **Keys hashed at rest**: `foundry_db.hash_key()` (SHA-256). Keygen stores only the
  hash; plaintext is shown once and not recoverable. `require_key` hashes the presented
  `X-API-Key` and compares against the stored hash — no key material retained.

- **Tenant isolation**: All `/session/*` endpoints enforce per-node ownership. Cross-node
  access returns 404 (non-enumerable — IDs cannot be probed). `/sessions` and both
  `/ledger` endpoints are scoped to the calling node. Sessions and ledger entries stamp
  `node_id` at creation.

- **Rate limiter trust-proxy fix**: `X-Forwarded-For` only accepted when
  `HELIX_TRUST_PROXY=1`. Defaults to socket IP. Stale buckets are evicted per-request
  to prevent unbounded map growth.

- **Widget CORS and auth gate**: Wildcard CORS origin removed; opt-in allowlist via
  `HELIX_CORS_ORIGINS`. Optional key gate on model-backed endpoints via
  `HELIX_WIDGET_API_KEY`. Bypass key uses `hmac.compare_digest` (constant-time);
  header-only (query-param path that leaked into logs removed).

### Cedar Dual-Gate (v1.4)

v1.4 added **CNCF Cedar** integration for dual-gate containment per RFC 0003:

- **Duck Gate** (response): Epistemic markers, marker-coverage scoring, receipts — unchanged from v1.2
- **Cedar Gate** (action): Declarative policy evaluation on tool use, shell, API calls before execution
- **Fail-closed**: Unavailable policy engine = default deny, never default permit
- **Lattice-approved**: Architecture reviewed and approved by four independent AI systems

Foundry additionally uses a **second, independent Cedar policy set** for
model-pool routing (`routing.cedar`, RFC 0004) — a different question
(which model handles this request) from RFC 0003's Cedar Gate (is this
action authorized to execute). The two share the Cedar engine but not a
policy file, a schema, or a fail-open/fail-closed posture: routing fails
*open* to a static action-map fallback (answer the request somehow),
Cedar Gate fails *closed* (deny by default). See RFC 0004 for the
context-field vocabulary and the five routing policies.

## 6. Testing Strategy

- `test_basic.py` — Marker parsing, receipt integrity, marker-coverage edge cases. 11 unit tests.
- `test_v12_pipeline.py` — Regression and adversarial testing for v1.2 hardened behaviours: format violations, blind spots, tampering attempts, determinism baseline. 4 integration tests. All passing at T=0.
- `test_cedar.py` — Cedar Dual-Gate: policy evaluation, fail-closed behaviour, action receipts, schema validation. 34 tests.
- `test_session.py` — Session architecture suite. 81 tests across:
  - `DriftThreshold` tier classification and boundary exactness
  - `InMemoryReceiptStore` and `SQLiteReceiptStore` full lifecycle
  - Store interface contract — both implementations parametrized against same spec
  - `HelixSession` core: session ID uniqueness, turn tracking, context accumulation, marker-coverage scoring, Cedar status propagation
  - Chain hash integrity: determinism, linkage verification, tamper detection, full N-turn chain walk
  - Session lifecycle: `clear`, `delete`, `export` (both formats), `running_drift`
  - `HelixSession.resume`: turn count restoration, chain continuation, context rebuild, nonexistent session raises
  - `JointReceipt`: field completeness, serialization, hash format
  - Context manager protocol
  - Public API regression — `HelixAdapter` unaffected by v1.5 changes

---

## 5. Physical Layer & Research Components (v1.7.5)

The adapter's governance stack (constitutional prompts, Cedar gate, receipts)
now sits atop a documented physical/research layer:

### 5.1 CORE/plop — PLOP Bridge
Fail-closed IMU attitude-geometry bridge, production v1.0.10 on CORE:
strapdown quaternion integration → spherical winding measure → quaternion
correction → 200-byte receipt to a localhost gate. HMAC-keyed checkpoint
chain, replay protection, SVD hybrid winding apex, calibrated threshold.
→ `docs/CORE_PLOP.md`, `CORE/plop-bridge/`

### 5.2 PQC-Engine
HELIX Hybrid Topological Post-Quantum Crypto Engine: 10-crossing braid root
of trust in SU(8), coupling NIST lattice hardness (MLWE/MSVP) with #P-hard
topological invariants; governance as topological entanglement (C1/C2 bound
via Gauss linking numbers). Validated (unitarity 7.37e-9, trace −1.0),
benchmarked (BKZ/RHF, ML-KEM/ML-DSA latency, Jones complexity), DOI'd.
→ `docs/PQC_ENGINE.md`, `PQC-Engine/`

### 5.3 Spacetime
Constitutional topological gravity suite: four validated campaigns showing
knot density couples to the metric (5 ppm curvature, 45 ppm dilation at
10× density) while mass alone does not. Topology exact everywhere
(|Lk| = 0.9947 ± 6e-15). → `docs/SPACETIME.md`, `spacetime/`

### 5.4 Research Layer
Oxford battery continuum (Helix 300 Hz / 4-phase Master Reset vs standard
Butler-Volmer; dendrite-risk proxy R → 0, Δc → 0), TRACE schema set
(`docs/schemas/`), RFC library (`docs/rfc/`).

> Artifact directories land on `build-dev` with the next main merge
> (they live on `main` via PR #23).

---

*This architecture document was contributed and reviewed by the community.*

**The formation holds.** 🦆

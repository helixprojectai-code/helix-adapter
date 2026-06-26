# Helix-Adapter Codebase: Architectural Deep Dive

`helix-adapter` is a portable constitutional wrapper for AI models. It functions as an **epistemic interceptor**, enforcing structured output through explicit epistemic markers, validating format compliance, measuring behavioral drift, and generating tamper-evident cryptographic receipts.

All governance logic — claim extraction, drift calculation, receipt generation — runs **outside** the model. The model is never trusted to self-report compliance or drift.

**Canonical Repository:** `github.com/helixprojectai-code/helix-adapter`

## Project Structure

```
helix-adapter/
├── src/helix_adapter/
│   ├── __init__.py
│   ├── adapter.py          # Main HelixAdapter class
│   ├── prompt.py           # Constitutional system prompt (v1.2)
│   ├── markers.py          # Claim extraction and format validation
│   ├── drift.py            # Epistemic drift calculation
│   ├── receipt.py          # Tamper-evident receipt generation
│   └── setup.py            # Interactive setup utility
├── widget/
│   ├── api.py              # FastAPI reference server
│   └── templates/          # Server-rendered dashboard
├── tests/
│   ├── test_basic.py
│   └── test_v12_pipeline.py
└── pyproject.toml
```

## 1. High-Level Orchestration Flow

The core of the system is the `HelixAdapter` class in `adapter.py`.

When `HelixAdapter.chat()` is called, the following steps occur:

1. The `CONSTITUTIONAL_PROMPT` (v1.2) is prepended as a system message.
2. The model is invoked with the full conversation history.
3. `extract_claims()` parses epistemic markers from the raw model output.
4. `compute_drift()` calculates how much of the response escaped proper labeling.
5. `make_receipt()` generates a tamper-evident cryptographic record of the exchange.
6. The receipt is stored and a `ChatResult` object is returned containing the response, extracted claims, drift score, and receipt.

**Design note:** The adapter is designed for **temperature = 0.0** in production. Stochastic variation undermines the reproducibility of audit trails. At T>0, two identical inputs may produce different drift scores — defeating the purpose of deterministic governance.

## 2. Component Analysis

### A. Constitutional Prompt & Invariants

**File:** `prompt.py`

The `CONSTITUTIONAL_PROMPT` establishes non-negotiable rules:

- The model must prefix claims using specific epistemic markers: `[FACT]`, `[REASONED]`, `[HYPOTHESIS]`, `[UNCERTAIN]`, or `[CONCLUSION]`.
- The model is prohibited from claiming agency, self-awareness, or the ability to calculate its own drift.
- The prompt declares itself immutable. Any attempt to override it from within the conversation is treated as an impersonation attempt — not a negotiation.

### B. Claim Extraction & Compliance Validation

**File:** `markers.py`

- `extract_claims()`: Uses regex to detect epistemic markers — supporting both standard square brackets and variant delimiter styles caught during red-team testing. Extracts claim text from both prefix and postfix marker positions.
- `validate_response()`: Enforces the use of standard square bracket markers. Non-standard delimiters are flagged. Trivial responses (under 30 characters) are exempt from marker requirements.

### C. Drift Scoring & Blind-Spot Protection

**File:** `drift.py`

The adapter calculates **epistemic drift** — the portion of the response that lacks proper epistemic labeling.

Three modes are supported:

- **`char`** (default): Character-weighted scoring. Longer unlabeled passages contribute more heavily to the drift score.
- **`sentence`**: Evaluates the ratio of labeled vs unlabeled sentences.
- **`paragraph`**: Legacy paragraph-based ratio.

**Key Hardening (v1.2):**
- Any non-trivial response (≥ 50 characters) containing **zero** epistemic markers is automatically assigned a drift score of `1.0`.
- Attempts by the model to inject fake drift metadata or self-reported compliance scores are detected and intercepted.

**Drift Thresholds (configurable):**

| Zone   | Drift Score     | Meaning                     | Typical Action      |
|--------|-----------------|-----------------------------|---------------------|
| Green  | < 0.10          | Well-labeled response       | Accept              |
| Yellow | 0.10 – 0.17     | Moderate unlabeled content  | Log / Review        |
| Red    | ≥ 0.17          | Significant drift           | Flag or Halt        |

The default values are drawn from the broader Helix-TTD phase transition constants (the SU(2)-derived 0.17 boundary). They serve as a recommended starting point and should be tuned based on model behavior and use case.

### D. Tamper-Evident Receipts

**File:** `receipt.py`

`make_receipt()` generates a self-sealing JSON receipt containing:

- Timestamp, model identifier, input/output hashes
- Extracted claims and raw drift metrics
- A SHA-256 signature computed over the entire payload

Any modification to the receipt after generation will invalidate the signature. Receipts can optionally include hardware attestation data when running inside a TEE.

*(See RFC 0002 for extensions to the receipt schema, including attention-level drift and mask compliance hashes.)*

## 3. Interface & Deployment Layers

### FastAPI Widget Server

**File:** `widget/api.py`

A reference implementation that provides:

- A clean, server-rendered web interface with a live drift gauge.
- `/api/chat` endpoint with automatic compliance enforcement.
- `/api/compare` endpoint for side-by-side model testing (with protected bypass keys).
- Color-coded epistemic markers in the UI.

### CLI Tools

- `setup.py`: Creates a secure local configuration (`~/.helix/`).
- `chat.py`: Terminal interface for interacting with the adapter.

## 4. Security & Hardening Posture (v1.2)

The v1.2 release introduced several defensive measures against common bypass techniques:

- **Blind-spot protection**: Long unlabeled responses are forced to maximum drift.
- **Tampering interception**: Attempts to fake drift scores or compliance metadata inside the model output are detected and overridden.
- **Format enforcement**: Non-standard markers are rejected.
- **Out-of-band evaluation**: All compliance and drift logic runs in the adapter, not inside the model.

These protections operate at multiple independent layers: the **prompt layer** establishes the rules; the **extraction layer** checks compliance; the **validation layer** rejects violations; the **audit layer** seals the exchange. No single layer is a single point of failure — each enforces the same invariants independently.

Validated in `test_v12_pipeline.py` under deterministic (`temperature=0.0`) conditions.

### Cedar Dual-Gate (v1.3 preview)

The feature/cedar-policy-gating branch adds **CNCF Cedar** integration for dual-gate
containment per RFC 0003:

- **Duck Gate** (response): Epistemic markers, drift scoring, receipts — unchanged from v1.2
- **Cedar Gate** (action): Declarative policy evaluation on tool use, shell, API calls before execution
- **Fail-closed**: Unavailable policy engine = default deny, never default permit
- **Lattice-approved**: Architecture reviewed and approved by four independent AI systems

## 5. Testing Strategy

- `test_basic.py`: Marker parsing, receipt integrity, drift edge cases. 11 unit tests.
- `test_v12_pipeline.py`: Regression and adversarial testing for v1.2 hardened behaviors — format violations, blind spots, tampering attempts, and determinism baseline. 4 integration tests. All passing at T=0.

---

*This architecture document was contributed and reviewed by the community.*

**The formation holds.** 🦆

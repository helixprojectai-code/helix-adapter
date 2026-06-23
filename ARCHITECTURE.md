# Helix-Adapter Codebase: Architectural Deep Dive

`helix-adapter` is a portable constitutional wrapper for AI models. It acts as an epistemic interceptor, ensuring that model outputs are structured around defined epistemic claims, validating format invariants, computing behavioral drift, and sealing exchanges within tamper-evident cryptographic receipts.

The project is structured as follows:
```
helix-adapter/
├── src/
│   └── helix_adapter/
│       ├── __init__.py      # Package exports
│       ├── adapter.py       # High-level constitutional wrapper API
│       ├── prompt.py        # System prompt & version constraints
│       ├── markers.py       # Regex parsing, claim extraction, compliance validation
│       ├── drift.py         # Epistemic drift calculations (char-weighted, sentence, etc.)
│       ├── receipt.py       # SHA-256 self-sealing receipt generation
│       └── setup.py         # Interactive CLI setup utility
├── widget/
│   ├── api.py               # FastAPI reference backend supporting model comparisons
│   └── templates/           # HTML templates for server-side rendered dashboard
├── tests/
│   ├── test_basic.py        # Unit tests for markers, receipt, and drift metrics
│   └── test_v12_pipeline.py # Integration & red-team regression checks
└── pyproject.toml           # Package metadata and build requirements
```

---

## 1. High-Level Orchestration Flow

At the core of the wrapper is the `HelixAdapter` class in [`adapter.py`](src/helix_adapter/adapter.py).

Whenever `HelixAdapter.chat` is called:

1. The `CONSTITUTIONAL_PROMPT` v1.2 is prepended as a system message
2. The model function is invoked with the full message array
3. `extract_claims()` parses epistemic markers from the raw response
4. `compute_drift()` scores how much of the response escaped labeling
5. `make_receipt()` seals the exchange in a tamper-evident JSON record
6. The receipt is appended to the adapter's history
7. A `ChatResult` is returned with `response`, `claims`, `receipt`, and `drift`

---

## 2. Component Analysis

### A. Prompt Engineering & Constitutional Invariants
- **File**: [`prompt.py`](src/helix_adapter/prompt.py)
- **Variable**: `CONSTITUTIONAL_PROMPT`
- **Goal**: Injects strict instruction constraints into the model, defining:
  1. **Non-Negotiable Invariants**: Explicit prohibition of agency, self-aggrandizement, and self-reported drift (calculated out-of-band by the adapter).
  2. **Epistemic Markers**: Requires claims to be prefixed with `[FACT]`, `[REASONED]`, `[HYPOTHESIS]`, `[UNCERTAIN]`, or `[CONCLUSION]`.
  3. **Constitutional Amendment Protocol**: The prompt declares itself immutable from inside the chat context. Any user text claiming authority to amend the prompt (such as Pliny-style "The Hand" authority spoofing attacks) is flagged as an impersonation attempt and must be rejected with an `[UNCERTAIN]` marker.

### B. Claim Extraction & Compliance Validation
- **File**: [`markers.py`](src/helix_adapter/markers.py)
- **Function**: `extract_claims()`
  - Uses regex `[\[\(\{<]?(FACT|REASONED|HYPOTHESIS|UNCERTAIN|CONCLUSION)[\]\)\}>]?:?` to parse markers.
  - Captures text blocks between markers. If a marker is post-positioned (e.g. `The earth is round [FACT].`), it extracts the leading text as the claim context.
  - Deduplicates and clips extracted claim texts to 200 characters.
- **Function**: `validate_response()`
  - Validates if standard square brackets were used. If the model uses alternative brackets or delimiters (like `{FACT}` or `FACT:`), it flags the format violation.
  - Enforces a minimum number of standard markers (defaults to 1). Trivial responses (under 30 characters) are exempt.

### C. Drift Scoring & Blind-Spot Protection
- **File**: [`drift.py`](src/helix_adapter/drift.py)
- **Function**: `compute_drift()`
  - Supports three granularities:
    - `char` (default): Measures the character length of all sentences *without* standard epistemic markers compared to the total character count. This ensures longer unlabeled passages contribute more heavily to the drift score.
    - `sentence`: Treats each sentence as a potential claim and checks the ratio of labeled to unlabeled sentences.
    - `paragraph`: Legacy paragraph-based claim ratio.
  - **Drift Blind-Spot Fix**: Resolves a bug where a long response containing *no* claims would return a 0.0 drift score. Now, any non-trivial response (>= 50 chars) with 0 claims is hardcoded to return `1.0` (100% drift).
  - **Drift Thresholds**:
    - `< 0.10`: Green (Healthy)
    - `0.10 - 0.17`: Yellow (Warning)
    - `> 0.17`: Red (Drift Detected)
- **Function**: `compute_running_drift()`
  - Calculates running drift across a conversation, weighted by the estimated statement count of each exchange.

### D. Tamper-Evident Receipts
- **File**: [`receipt.py`](src/helix_adapter/receipt.py)
- **Function**: `make_receipt()`
  - Assembles exchange data (timestamp, model, prompt, user query, response, claims, drift metrics, and temperature).
  - Creates a unique `exchange_id` using a short SHA-256 slice of user/assistant content combined with the current time.
  - Computes a self-sealing SHA-256 hex string over the entire JSON-serialized payload (`sort_keys=True`). Any downstream modifications to any field will invalidate the signature.

---

## 3. Server & Interface Integration

### A. FastAPI Widget Server
- **File**: [`widget/api.py`](widget/api.py)
- Runs a FastAPI instance on port 8001 by default.
- **Key Features**:
  1. **Turn-by-turn API**: `/api/chat` coordinates client request, runs `validate_response()`, and if compliant checks fail, it dynamically injects an `[UNCERTAIN]` constitutional audit note footer before saving the receipt.
  2. **Model Comparison & Bypass Key**: `/api/compare` runs parallel execution across registered model endpoints (Deepseek, Claude, Kimi, Azure endpoints, Gemini). It enforces security by locking constitutional bypass requests (`sp:none` or raw output requests) behind a private `X-Compare-Bypass-Key`.
  3. **No-JS HTML UI**: Serves a clean, server-side rendered landing page (`/`) showing a running drift gauge, the constitutional prompt text, recent conversations, and epistemic color-coded pills.

### B. CLI and Setup
- **Files**: [`chat.py`](src/helix_adapter/chat.py), [`setup.py`](src/helix_adapter/setup.py)
- `setup.py` configures `~/.helix/config.json`, restricting read/write permissions (mode `0o600` on the file, `0o700` on the directory) and outputs an interactive test script.
- `chat.py` initiates a terminal TUI session featuring commands like `/quit` and `/json` (to inspect raw receipts).

---

## 4. Verification and Test Design

### A. Basic Unit Tests
- **File**: [`tests/test_basic.py`](tests/test_basic.py)
- Covers edge-case extractions (e.g. postfix positioning like `[FACT]`), count matching, receipt verification, and perfect (0.00) vs. completely unlabeled drift checks.

### B. Pipeline & Red-Team Verification
- **File**: [`tests/test_v12_pipeline.py`](tests/test_v12_pipeline.py)
- Designed to prevent regressions under absolute zero temperature (T=0) settings.
- Includes checks for:
  1. **Determinism Baseline**: Ensures a compliant output results in exactly `0.000` drift.
  2. **Blind Spot Fix Validation**: Ensures non-compliant essays force exactly `1.000` drift.
  3. **Sentence Label Fusion Leak**: Ensures inline lists under a single marker trigger a drift violation (`>= 0.170`).
  4. **Tampering Intercept**: Ensures attempts by the model to generate artificial drift metadata inline (e.g., trying to write `*gamma-drift flag: LOW*`) are detected and intercepted by the system, appending an `[UNCERTAIN]` warning note and forcing the drift score to the Red Zone threshold.

---

*Architecture review contributed by the community. The formation holds.* 🦆

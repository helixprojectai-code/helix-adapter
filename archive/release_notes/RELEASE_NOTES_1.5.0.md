# helix-adapter v1.5.0 Release Notes

**Released:** 2026-06-29
**Branch:** spider-dev → main
**PyPI:** `pip install helix-adapter==1.5.0`

---

## What's New

### HelixSession — Multi-Turn Constitutional Sessions

The headline feature of v1.5. `HelixSession` is the new primary surface for
conversational workloads. Where `HelixAdapter` wraps a single call, `HelixSession`
wraps the full conversation — managing context window state, chaining receipts across
turns, and tracking running drift throughout the session.

```python
from helix_adapter import HelixSession, SQLiteReceiptStore

session = HelixSession(
    model_fn=call_model,
    model_name="deepseek-4-pro",
    store=SQLiteReceiptStore(),
)

r1 = session.send("What is quantum entanglement?")
r2 = session.send("How does that relate to Bell's theorem?")

print(r2.drift_tier)      # "green"
print(r2.chain_hash)      # tamper-evident link to r1
print(session.running_drift())  # mean drift across session
```

Full session lifecycle: `send`, `clear`, `delete`, `export`, `resume`. Context manager
supported.

---

### Tamper-Evident Receipt Chain

Every turn in a session produces a `JointReceipt` that is cryptographically linked
to all prior turns via `chain_hash`:

```
chain_hashₙ = sha256(hex(chain_hashₙ₋₁) + hex(hashₙ))
```

Modifying any prior receipt breaks the chain from that point forward. This is the
audit property required for enterprise compliance — not just a bag of independent
hashes, but a chain where history cannot be silently rewritten.

---

### JointReceipt — Co-Sealed Duck + Cedar Gate

In v1.4, Cedar and Duck Gate produced separate records per exchange. In v1.5 they are
co-sealed in a single `JointReceipt` per turn, covering both response governance
(drift, claims) and action governance (Cedar decision, policy hash) in one sealed record.

---

### Pluggable Receipt Stores

Two store implementations ship out of the box:

- **`InMemoryReceiptStore`** — default, no dependencies, suitable for testing and
  short-lived sessions
- **`SQLiteReceiptStore`** — WAL-mode persistent store, auto-creates `~/.helix/sessions.db`.
  Sessions survive process restarts and can be resumed with full context

Custom stores implement the four-method `ReceiptStore` ABC.

---

### Session Resume

Sessions persisted in `SQLiteReceiptStore` can be resumed across restarts, with the
full conversation context window rebuilt from stored receipts:

```python
session = HelixSession.resume(
    session_id="hsess-a3f2b1c0d9e8",
    model_fn=call_model,
    store=store,
)
receipt = session.send("Where were we?")
```

---

### Configurable Drift Thresholds

`DriftThreshold` is now a first-class configurable dataclass. Pass per-deployment
instances to tune tolerance — stricter for adversarial testing, looser for creative
workloads:

```python
from helix_adapter import DriftThreshold, HelixSession

session = HelixSession(
    model_fn=call_model,
    drift_threshold=DriftThreshold(green=0.05, yellow=0.10, red=0.15),
)
```

---

### cedar_python Now a Core Dependency

`cedar_python` has been promoted from an optional extra to a core dependency.
`pip install helix-adapter` now includes Cedar automatically — no separate
`pip install helix-adapter[cedar]` required.

---

## Documentation

- **`QUICKSTART.md`** (new) — dedicated FastAPI walkthrough. Complete working API,
  session lifecycle endpoints, auth, resume across restarts, DeepSeek / Claude / Ollama
  backend swap examples, systemd unit, receipt schema reference.
- **`README.md`** — rewritten as a standard project landing page with architecture
  flow diagram, both `HelixAdapter` and `HelixSession` usage, drift tables, CLI,
  receipt format, Cedar, Foundry.
- **`ARCHITECTURE.md`** — new Session Architecture section covering `HelixSession`,
  `JointReceipt`, chain derivation, store layer, and `DriftThreshold`.

---

## Testing

81 new tests in `tests/test_session.py`, reviewed and smoke-tested by the Hermes node
against a live DeepSeek 4 Pro payload. Full suite: 130 tests passing.

Coverage: `DriftThreshold` boundaries, both store implementations and shared interface
contract, `HelixSession` core behaviour, chain hash integrity and tamper detection,
session lifecycle, `resume`, `JointReceipt` structure, context manager, public API
regression.

---

## Breaking Changes

None. `HelixAdapter` is unchanged. All existing integrations continue to work without
modification.

---

## Migration

No migration required. To adopt `HelixSession` in existing code:

```python
# Before (v1.4)
adapter = HelixAdapter(model_fn=call_model, model_name="gpt-4o")
result = adapter.chat(message)

# After (v1.5) — for multi-turn workloads
session = HelixSession(model_fn=call_model, model_name="gpt-4o")
receipt = session.send(message)
# receipt.assistant_response == result.response
# receipt.drift_score == result.drift
```

Both patterns work. Use `HelixAdapter` for one-shot calls, `HelixSession` for conversations.

---

## What's Next

- Session context window management (truncation strategy for long conversations)
- `HelixSession` integration into Helix Foundry routing layer
- Merkle-style session integrity verification endpoint
- PyPI release under Helix AI Innovations org

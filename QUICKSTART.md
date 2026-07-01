# helix-adapter FastAPI Quickstart

Stand up a constitutional multi-turn chat API in minutes.

## Install

```bash
pip install "helix-adapter[widget]"
```

The `widget` extra pulls in `fastapi`, `uvicorn`, and the OpenAI client. Core `helix-adapter` only needs `cedar_python`.

---

## Minimal API — HelixSession + FastAPI

```python
# api.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from helix_adapter import HelixSession, SQLiteReceiptStore

app = FastAPI(title="Helix Constitutional API")
client = OpenAI()  # or any OpenAI-compatible client

def call_model(messages: list[dict]) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.7,
    )
    return resp.choices[0].message.content

store = SQLiteReceiptStore()          # persists to ~/.helix/sessions.db
sessions: dict[str, HelixSession] = {}

class ChatRequest(BaseModel):
    session_id: str
    message: str

@app.post("/session/new")
def new_session():
    s = HelixSession(model_fn=call_model, model_name="gpt-4o", store=store)
    sessions[s.id] = s
    return {"session_id": s.id}

@app.post("/chat")
def chat(req: ChatRequest):
    s = sessions.get(req.session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    receipt = s.send(req.message)
    return {
        "response": receipt.assistant_response,
        "turn": receipt.turn,
        "drift_score": receipt.drift_score,
        "drift_tier": receipt.drift_tier,
        "claims": receipt.claims,
        "chain_hash": receipt.chain_hash,
    }

@app.get("/session/{session_id}/export")
def export_session(session_id: str, fmt: str = "jsonl"):
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return {"data": s.export(fmt=fmt)}

@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    s = sessions.pop(session_id, None)
    if s:
        s.delete()
    return {"deleted": session_id}
```

```bash
uvicorn api:app --port 8001 --reload
```

---

## Try It

```bash
# Create a session
curl -X POST http://localhost:8001/session/new
# {"session_id": "hsess-a3f2b1c0d9e8"}

# Send a message
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "hsess-a3f2b1c0d9e8", "message": "What is quantum entanglement?"}'

# {"response": "[FACT] Quantum entanglement is...", "turn": 0,
#  "drift_score": 0.0041, "drift_tier": "green", "claims": [...],
#  "chain_hash": "e3b0c44298fc..."}

# Follow-up — context is preserved
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "hsess-a3f2b1c0d9e8", "message": "How does that relate to Bell'\''s theorem?"}'

# Export full receipt chain
curl http://localhost:8001/session/hsess-a3f2b1c0d9e8/export
```

---

## Resume a Session Across Restarts

Sessions stored in `SQLiteReceiptStore` survive process restarts:

```python
from helix_adapter import HelixSession, SQLiteReceiptStore

store = SQLiteReceiptStore(path="~/.helix/sessions.db")

# Restore a session from a prior run — context window rebuilt from receipts
session = HelixSession.resume(
    session_id="hsess-a3f2b1c0d9e8",
    model_fn=call_model,
    store=store,
    model_name="gpt-4o",
)

receipt = session.send("Where were we?")
```

---

## Session Management Endpoints

Add these to your API for a complete session lifecycle:

```python
@app.get("/sessions")
def list_sessions():
    return {"sessions": store.list_sessions()}

@app.post("/session/{session_id}/clear")
def clear_session(session_id: str):
    """Wipe history, keep session ID active."""
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    s.clear()
    return {"cleared": session_id}

@app.post("/session/resume")
def resume_session(session_id: str):
    """Load a persisted session back into memory."""
    if session_id in sessions:
        return {"session_id": session_id, "status": "already_loaded"}
    s = HelixSession.resume(session_id, model_fn=call_model, store=store)
    sessions[s.id] = s
    return {"session_id": s.id, "turn": s.turn}

@app.get("/session/{session_id}/drift")
def session_drift(session_id: str):
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return {"running_drift": s.running_drift(), "drift_tier": "see thresholds"}
```

---

## API Key Auth

Protect your endpoints with the Foundry key system:

```python
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

API_KEYS = {"hx-your-key-here"}   # or load from foundry_db

key_header = APIKeyHeader(name="X-API-Key")

def require_key(key: str = Depends(key_header)):
    if key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid key")
    return key

@app.post("/chat")
def chat(req: ChatRequest, _: str = Depends(require_key)):
    ...
```

Or use the Foundry key store directly (requires the full Foundry install):

```python
# foundry/ ships with helix-adapter — add it to path first
import sys
sys.path.insert(0, "foundry")
from foundry_auth import require_key
```

---

## DeepSeek / Claude / Ollama

Swap `call_model` for any OpenAI-compatible backend — everything else stays the same.

**DeepSeek:**
```python
from openai import OpenAI
client = OpenAI(api_key="sk-...", base_url="https://api.deepseek.com/v1")

def call_model(messages):
    return client.chat.completions.create(
        model="deepseek-chat", messages=messages
    ).choices[0].message.content
```

**Anthropic Claude:**
```python
import anthropic
claude = anthropic.Anthropic()

def call_model(messages):
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    turns = [m for m in messages if m["role"] != "system"]
    resp = claude.messages.create(
        model="claude-sonnet-4-6", max_tokens=2048,
        system=system, messages=turns
    )
    return resp.content[0].text
```

**Ollama (local):**
```python
from openai import OpenAI
client = OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")

def call_model(messages):
    return client.chat.completions.create(
        model="llama3.2", messages=messages
    ).choices[0].message.content
```

---

## Systemd Service

```ini
# /etc/systemd/system/helix-api.service
[Unit]
Description=Helix Constitutional API
After=network.target

[Service]
User=steve
WorkingDirectory=/opt/helix-api
ExecStart=/opt/helix-api/.venv/bin/uvicorn api:app --host 127.0.0.1 --port 8001
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now helix-api
```

---

## Receipt Schema

Every `session.send()` call returns a `JointReceipt`:

| Field | Type | Description |
|-------|------|-------------|
| `exchange_id` | str | SHA-256 prefix, unique per turn |
| `session_id` | str | Parent session identifier |
| `turn` | int | Zero-indexed turn counter |
| `timestamp` | str | ISO 8601 UTC |
| `model` | str | Model name passed at session creation |
| `user_message` | str | Original user input |
| `assistant_response` | str | Full model response |
| `claims` | list | Extracted `[MARKER] text` pairs |
| `drift_score` | float | 0.0 = fully labeled, 1.0 = no markers |
| `drift_tier` | str | `green` / `yellow` / `red` |
| `cedar_status` | str | `active` / `fail_closed` / `not_configured` |
| `hash` | str | SHA-256 over all receipt fields |
| `chain_hash` | str | SHA-256 of `hex(prev_chain_hash) + hex(this_hash)` — hex string concatenation |

The `chain_hash` links every turn in a session into a tamper-evident chain —
modifying any prior receipt breaks all subsequent hashes.

## Merkle Tree Integrity

Each receipt chain is also backed by an append-only Merkle tree. Every
`session.send()` appends the receipt hash as a leaf and stores the resulting
root. This enables:

- **Historical roots** — prove what the tree looked like at any prior turn
- **Inclusion proofs** — verify any receipt is part of its session at a given
  root (`session.merkle_proof(turn)`)
- **Dual verification** — chain_hash detects linear tampering; Merkle detects
  structural reordering

```python
# After sending a few turns
session.send("What is quantum computing?")
session.send("How does it relate to Bell's theorem?")

# Get the current Merkle root
print(session.merkle_root)           # hex digest

# Get an inclusion proof for turn 0
proof = session.merkle_proof(0)      # {turn, leaf_hash, proof, root, leaf_count}

# Verify independently (no tree instance needed)
from helix_adapter import MerkleTree
assert MerkleTree.verify(
    proof["leaf_hash"],
    proof["proof"],
    proof["root"],
)
```

See `MerkleTree` in the API reference below — it is exported from
`helix_adapter` and can be used standalone.

---

## Drift Thresholds

| Score | Tier | Meaning |
|-------|------|---------|
| 0.00 – <0.10 | `green` | Healthy — claims are properly labeled |
| 0.10 – <0.17 | `yellow` | Warning — some statements lack markers |
| 0.17+ | `red` | Drift — significant unlabeled content |

Boundaries are exclusive on the upper end (`score < threshold`), matching `DriftThreshold.tier()`.

Override per deployment:

```python
from helix_adapter import DriftThreshold, HelixSession

strict = DriftThreshold(green=0.05, yellow=0.10, red=0.15)
session = HelixSession(model_fn=call_model, drift_threshold=strict)
```

---

## Next Steps

- **Cedar policy gating** — see the Cedar section in [README.md](README.md)
- **Helix Foundry** — Cedar-routed multi-model inference pool, ships in `foundry/`
- **Live demo** — [helixaiinnovations.ca/chat/](https://helixaiinnovations.ca/chat/)

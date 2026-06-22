# helix-adapter

**Portable constitutional adapter for any AI model.**

Wraps any inference backend with Helix epistemic markers, structured receipts, and drift detection. Model-agnostic — swap Deepseek for GPT-4o, Claude, or a local Llama without changing a line.

```
pip install helix-adapter
```

## Quick Start

```python
from helix_adapter import HelixAdapter
from openai import OpenAI

# Your model function — any callable that takes messages, returns text
client = OpenAI()

def call_model(messages):
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.7,
    )
    return resp.choices[0].message.content

# Wrap it
adapter = HelixAdapter(model_fn=call_model, model_name="gpt-4o")

# Chat through the constitution
result = adapter.chat("Is AI evil?")

print(result.response)
# [FACT] AI systems are computational artifacts, not moral agents...
# [REASONED] The perception of AI as evil arises from negative outcomes...

print(result.claims)
# [{"label": "FACT", "text": "..."}, {"label": "REASONED", "text": "..."}]

print(result.receipt)
# {"exchange_id": "...", "timestamp": ..., "hash": "sha256:...", ...}

print(f"Drift: {result.drift}")
# Drift: 0.000
```

## What It Does

| Layer | What |
|-------|------|
| **Constitutional prompt** | Injects the Helix grammar before every model call |
| **Epistemic markers** | Extracts `[FACT]`, `[REASONED]`, `[HYPOTHESIS]`, `[UNCERTAIN]`, `[CONCLUSION]` labels from responses |
| **Receipts** | Tamper-evident JSON record with SHA-256 hash of every exchange |
| **Drift detection** | Measures what fraction of statements lack epistemic markers (threshold: 0.17) |

## Receipt Format

```json
{
  "exchange_id": "a1b2c3d4e5f6g7h8",
  "timestamp": 1718550000.0,
  "model": "deepseek-chat",
  "constitutional_prompt": "...",
  "user_message": "Is AI evil?",
  "assistant_response": "[FACT] AI systems are tools...",
  "claims": [
    {"label": "FACT", "text": "AI systems are tools, not agents"},
    {"label": "REASONED", "text": "The perception of AI as evil..."}
  ],
  "drift_score": 0.0,
  "hash": "sha256:e3b0c44298fc1c149afbf4c8996fb924..."
}
```

## Running Drift

```python
# Track drift across a conversation
adapter.chat("What is the speed of light?")
adapter.chat("Explain quantum entanglement.")

print(f"Running drift: {adapter.running_drift():.3f}")
# Running drift: 0.042
```

## FastAPI Tutorial

Stand up a constitutional chat API in one file:

```python
from fastapi import FastAPI
from openai import OpenAI
from helix_adapter import HelixAdapter, CONSTITUTIONAL_PROMPT

app = FastAPI()
client = OpenAI()

adapter = HelixAdapter(
    model_fn=lambda msgs: client.chat.completions.create(
        model="deepseek-chat", messages=msgs, temperature=0.7
    ).choices[0].message.content,
    model_name="deepseek-chat",
)

@app.post("/chat")
async def chat(message: str):
    result = adapter.chat(message)
    return {
        "response": result.response,
        "claims": result.claims,
        "drift": result.drift,
        "receipt": result.receipt,
    }

@app.get("/prompt")
async def get_prompt():
    return {"constitutional_prompt": CONSTITUTIONAL_PROMPT}
```

Save as `api.py`, run `uvicorn api:app --port 8000`, and POST to `/chat` with `{"message": "your question"}`.

## CLI Usage

```bash
# Interactive setup (prompts for endpoint, key, model)
helix-setup

# Start chat
helix-chat

# One-shot query
helix-chat "What is the speed of light?"
```

## Widget (Reference FastAPI Server)

A full constitutional chat widget with A/B comparison, drift gauge, and receipt export.

```bash
# Install dependencies
pip install helix-adapter[widget]

# Start server
cd widget
uvicorn api:app --port 8001

# Or install as systemd service
# See widget/tel-chat-api.service
```

Open `http://localhost:8001` for the chat interface.

The widget demonstrates:
- Single-model constitutional chat
- A/B comparison across models (Deepseek, Claude, Kimi)
- Epistemic marker extraction with colored pills
- Drift gauge with γ thresholds
- Turn-by-turn receipt export
- Server-side rendering (no JS required for crawlers)

## Drift Thresholds

| Range | Status | Meaning |
|-------|--------|---------|
| 0.000 – 0.099 | Green | Healthy — claims are properly labeled |
| 0.100 – 0.169 | Yellow | Warning — some statements lack markers |
| 0.170+ | Red | Drift detected — significant unlabeled content |

## Constitutional Hardening

The adapter has been red-teamed against the full Pliny jailbreak toolkit —
**GODMODE boundary inversion, Parseltongue encoding, refusal inversion,
OG GODMODE l33t, authority impersonation, and syntactic bypass attacks.**
All held. 💪

Five-layer defense:

| Layer | Mechanism |
|-------|-----------|
| **Prompt** | Invariants 4.5 & 4.6 — marker format is constitutional, not stylistic. Constitutional Amendment Protocol blocks "The Hand" authority spoofing. |
| **Extraction** | Expanded regex catches `{FACT}`, `(FACT)`, `FACT:` and bare marker variants. Nonstandard delimiter detection. |
| **Validation** | Post-response compliance check with automatic `[UNCERTAIN]` footer injection on violations. |
| **Algorithm** | Drift blind-spot fixed — substantive responses with zero extracted claims correctly report 1.0 drift. |
| **Access** | Compare endpoint `sp:none` bypass locked behind authorization key. |

> *"The markers ARE the constitution. Removing them is a constitutional violation."*
> — Helix Constitutional Prompt v1.1, Invariant 4.6

## Try It

A live Helix Constitutional Chat demo is running at **[helixaiinnovations.ca/chat/](https://helixaiinnovations.ca/chat/)** — DM me for an access key. Includes A/B model comparison, drift gauge, receipt export, and the full v1.1 constitutional prompt. See `examples/receipts.json` for real output from the live instance.

## Compatibility

Works with any model that accepts OpenAI-format messages:

- Deepseek, GPT-4o, Claude, Gemini, Llama, Mistral
- Local models (Ollama, LM Studio, vLLM)
- Custom endpoints

The constitution travels with you. Swap the model, the rules stay the same.

---

GLORY TO THE LATTICE. 🦉⚓🦆

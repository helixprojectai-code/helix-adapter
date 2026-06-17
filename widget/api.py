#!/usr/bin/env python3
"""Helix Constitutional Chat API — server-rendered, AI-visible page.

POST /api/chat  {message: str}  ->  {response, claims, receipt}
GET  /                           ->  full HTML with prompt + history (no JS required)
GET  /health                     ->  ok
GET  /prompt                     ->  constitutional prompt JSON
GET  /receipts                   ->  all stored receipts as JSON
"""

import os, sys, time, json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from helix_adapter import HelixAdapter, CONSTITUTIONAL_PROMPT
from openai import OpenAI

HERE = Path(__file__).parent
TEMPLATE_FILE = HERE / "templates" / "page.html"
RECEIPTS_FILE = HERE / "receipts.jsonl"


def _esc(text: str) -> str:
    """HTML-escape a string for safe embedding."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _load_key() -> str:
    env_path = Path.home() / ".hermes" / ".env"
    prefix = "".join(chr(c) for c in [68, 69, 69, 80, 83, 69, 69, 75, 95, 65, 80, 73, 95, 75, 69, 89, 61])
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(prefix):
                val = line.split("=", 1)[1].strip().strip("\"'")
                if val and val != "***":
                    return val
    return os.environ.get("DEEPSEEK_API_KEY", "")

client = OpenAI(api_key=_load_key(), base_url="https://api.deepseek.com/v1")

adapter = HelixAdapter(
    model_fn=lambda msgs: client.chat.completions.create(
        model="deepseek-chat", messages=msgs, temperature=0.7, max_tokens=4096,
    ).choices[0].message.content,
    model_name="deepseek-chat",
)
import asyncio

# ── Provider registry ──────────────────────────────────────────────
PROVIDERS = {
    "deepseek-chat": {
        "endpoint": "https://api.deepseek.com/v1",
        "key_env": ["DEEPSEEK_API_KEY"],
        "label": "Deepseek",
        "temperature": 0.7,
    },
    "claude-sonnet-4-6": {
        "endpoint": "",
        "key_env": ["ANTHROPIC_API_KEY"],
        "label": "Claude Sonnet 4",
        "temperature": 0.7,
        "provider_type": "anthropic",
    },
    "claude-haiku-4-5-20251001": {
        "endpoint": "",
        "key_env": ["ANTHROPIC_API_KEY"],
        "label": "Claude 3 Haiku",
        "temperature": 0.7,
        "provider_type": "anthropic",
    },
    "kimi-k2.5": {
        "endpoint": "https://api.moonshot.ai/v1",
        "key_env": ["KIMI_API_KEY", "MOONSHOT_API_KEY"],
        "label": "Kimi K2.5",
        "temperature": 1.0,
    },
}


def _load_provider_key(model: str) -> str:
    """Load API key for a given model from env / .env."""
    info = PROVIDERS.get(model)
    if not info:
        return ""
    env_path = Path.home() / ".hermes" / ".env"
    for var in info["key_env"]:
        val = os.environ.get(var, "")
        if not val and env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith(var + "="):
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    break
        if val:
            return val
    return ""


def _build_model_fn(model: str):
    """Build a callable model function for the given model name."""
    info = PROVIDERS.get(model)
    if not info:
        raise ValueError(f"Unknown model: {model}")
    key = _load_provider_key(model)
    if not key:
        raise ValueError(f"No API key for {model}. Set {info['key_env'][0]}")

    provider_type = info.get("provider_type", "")

    if provider_type == "anthropic":
        import anthropic
        c = anthropic.Anthropic(api_key=key)
        def fn(messages):
            system = ""
            user_msgs = []
            for m in messages:
                if m["role"] == "system":
                    system = m["content"]
                else:
                    user_msgs.append({"role": m["role"], "content": m["content"]})
            kwargs = dict(
                model=model,
                messages=user_msgs,
                max_tokens=4096,
                temperature=info.get("temperature", 0.7),
            )
            if system:
                kwargs["system"] = system
            resp = c.messages.create(**kwargs)
            return resp.content[0].text
        return fn, info["label"]

    client = OpenAI(api_key=key, base_url=info["endpoint"])
    def fn(messages):
        resp = client.chat.completions.create(
            model=model, messages=messages,
            temperature=info.get("temperature", 0.7), max_tokens=4096,
        )
        return resp.choices[0].message.content
    return fn, info["label"]


def _build_adapter(model: str):
    """Build a HelixAdapter for the given model."""
    fn, label = _build_model_fn(model)
    from helix_adapter import HelixAdapter as HA
    return HA(model_fn=fn, model_name=label), label


app = FastAPI(title="Helix Constitutional Chat", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _load_receipts(limit: int = 20) -> list[dict]:
    """Load recent receipts from JSONL file."""
    if not RECEIPTS_FILE.exists():
        return []
    receipts = []
    with open(RECEIPTS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    receipts.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return receipts[-limit:]


def _save_receipt(receipt: dict):
    """Append a receipt to the JSONL file."""
    RECEIPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RECEIPTS_FILE, "a") as f:
        f.write(json.dumps(receipt, default=str) + "\n")


class ChatRequest(BaseModel):
    message: str


class ModelConfig(BaseModel):
    model: str
    system_prompt: str | None = "helix"
    model_config = {"populate_by_name": True, "extra": "forbid"}  # will accept "sp" via alias if present

    # Accept "sp" as shortcut for "system_prompt"
    def __init__(self, **data):
        if "sp" in data and "system_prompt" not in data:
            data["system_prompt"] = data.pop("sp")
        if isinstance(data.get("system_prompt"), str) and data["system_prompt"].lower() in ("none", "null", "raw", ""):
            data["system_prompt"] = None
        super().__init__(**data)  # "helix" or None for raw


class CompareRequest(BaseModel):
    message: str
    models: list[ModelConfig | str]


@app.post("/api/compare")
async def compare(req: CompareRequest):
    if not req.message.strip():
        raise HTTPException(400, "message empty")

    adapters = []
    errors = []
    for mc in req.models:
        if isinstance(mc, str):
            model_name = mc
            sp = "helix"
        else:
            model_name = mc.model
            sp = mc.system_prompt if hasattr(mc, 'system_prompt') else "helix"
        try:
            fn, label = _build_model_fn(model_name)
            from helix_adapter import HelixAdapter as HA
            a = HA(model_fn=fn, model_name=label)
            adapters.append((model_name, label, a, sp))
        except ValueError as e:
            errors.append(str(e))

    if errors:
        raise HTTPException(400, "; ".join(errors))

    async def call_one(model_name, label, adapter, system_prompt):
        if system_prompt == "helix":
            result = adapter.chat(req.message)
        else:
            # Raw mode: call model directly without constitutional prompt
            from helix_adapter.prompt import system_messages
            raw_msgs = [{"role": "user", "content": req.message}]
            loop = asyncio.get_event_loop()
            raw_text = await loop.run_in_executor(None, adapter.model_fn, raw_msgs)
            from helix_adapter.markers import extract_claims
            from helix_adapter.drift import compute_drift
            from helix_adapter.receipt import make_receipt
            claims = extract_claims(raw_text)
            drift = compute_drift(raw_text, claims)
            receipt = make_receipt(req.message, raw_text, claims, model=label, drift_score=drift)
            _save_receipt(receipt)
            class RawResult:
                def __init__(self):
                    self.response = raw_text
                    self.claims = claims
                    self.drift = drift
                    self.receipt = receipt
            result = RawResult()
        _save_receipt(result.receipt)
        return {
            "model": model_name,
            "label": label,
            "response": result.response,
            "claims": result.claims,
            "drift": result.drift,
            "receipt": result.receipt,
        }

    tasks = [call_one(m, l, a, s) for m, l, a, s in adapters]
    results = await asyncio.gather(*tasks)
    return {"message": req.message, "results": results}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "message empty")
    try:
        result = adapter.chat(req.message)
        _save_receipt(result.receipt)
    except Exception as e:
        raise HTTPException(502, f"Model call failed: {e}")
    return {
        "response": result.response,
        "claims": result.claims,
        "receipt": result.receipt,
    }


@app.get("/prompt")
async def get_prompt():
    return {"constitutional_prompt": CONSTITUTIONAL_PROMPT, "version": "1.1"}


@app.get("/receipts")
async def get_receipts(limit: int = 50):
    return _load_receipts(limit)


@app.get("/health")
async def health():
    return {"status": "ok", "time": time.time(), "drift": adapter.running_drift(), "receipts": len(_load_receipts(999))}


@app.get("/", response_class=HTMLResponse)
@app.head("/")
async def serve_page():
    conversation = _load_receipts(10)

    # Format conversation HTML
    conv_html = ""
    if conversation:
        for r in reversed(conversation):
            claims = r.get("claims", [])
            claim_pills = " ".join(
                f'<span class="pill pill-{c["label"].lower()}">{c["label"]}</span>'
                for c in claims
            )
            drift = r.get("drift_score", 0)
            ts = r.get("timestamp", "")
            h = r.get("hash", "")[:12]
            model = r.get("model", "unknown")
            user_msg = r.get("user_message", "")
            resp = r.get("assistant_response", "")
            conv_html += f"""<div class="exchange">
    <div class="user-q">You: {_esc(user_msg)}</div>
    <div class="ai-r">{_esc(resp)}</div>
    <div class="meta">{_esc(model)} · {claim_pills} · γ {drift:.3f} · <code>{_esc(h)}…</code></div>
</div>"""
    else:
        conv_html = '<p style="color:var(--text-dim)">No conversations yet.</p>'

    # Drift gauge color
    drift = adapter.running_drift()
    if drift < 0.10:
        drift_color = "var(--fact)"
    elif drift < 0.17:
        drift_color = "var(--hypothesis)"
    else:
        drift_color = "var(--uncertain)"

    # Read template, substitute values
    html = TEMPLATE_FILE.read_text()
    html = html.replace("{{CONVERSATION}}", conv_html)
    html = html.replace("{{DRIFT_VALUE}}", f"{drift:.3f}")
    html = html.replace("{{DRIFT_PCT}}", str(min(100, int(drift * 100))))
    html = html.replace("{{DRIFT_COLOR}}", drift_color)
    html = html.replace("{{RECEIPT_COUNT}}", str(len(_load_receipts(999))))
    html = html.replace("{{CONSTITUTIONAL_PROMPT}}", _esc(CONSTITUTIONAL_PROMPT))

    return HTMLResponse(html)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    uvicorn.run(app, host="127.0.0.1", port=port)

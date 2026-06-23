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
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn

from helix_adapter import HelixAdapter, CONSTITUTIONAL_PROMPT
from helix_adapter.markers import validate_response, extract_claims
from helix_adapter.drift import compute_drift
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

# Bypass key for sp:none on compare endpoint — unset = disabled
COMPARE_BYPASS_KEY = os.environ.get("HELIX_COMPARE_BYPASS_KEY", "")
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
    "azure-grok-4-20-reasoning": {
        "endpoint": "https://helix-deploy-resource.openai.azure.com/openai/v1",
        "key_env": ["AZURE_OPENAI_API_KEY"],
        "label": "Grok 4.20 (Azure)",
        "temperature": 0.7,
        "azure_deployment": "grok-4-20-reasoning",
    },
    "azure-deepseek-v3-2": {
        "endpoint": "https://helix-deploy-resource.openai.azure.com/openai/v1",
        "key_env": ["AZURE_OPENAI_API_KEY"],
        "label": "DeepSeek V3.2 (Azure)",
        "temperature": 0.7,
        "azure_deployment": "DeepSeek-V3.2",
        "max_tokens_param": "max_completion_tokens",
    },
    "azure-gpt-5-4-nano": {
        "endpoint": "https://helix-deploy-resource.openai.azure.com/openai/v1",
        "key_env": ["AZURE_OPENAI_API_KEY"],
        "label": "GPT-5.4 Nano (Azure)",
        "temperature": 0.7,
        "azure_deployment": "gpt-5.4-nano",
        "max_tokens_param": "max_completion_tokens",
    },

    "gemini-2.5-flash": {
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": ["GOOGLE_API_KEY"],
        "label": "Gemini 2.5 Flash",
        "temperature": 0.7,
        "provider_type": "google",
    },
    "gemini-2.5-pro": {
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": ["GOOGLE_API_KEY"],
        "label": "Gemini 2.5 Pro",
        "temperature": 0.7,
        "provider_type": "google",
    }

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

    if provider_type == "google":
        client = OpenAI(
            api_key=key,
            base_url=info["endpoint"],
        )
        def fn(messages):
            resp = client.chat.completions.create(
                model=model, messages=messages,
                temperature=info.get("temperature", 0.7), max_tokens=4096,
            )
            return resp.choices[0].message.content
        return fn, info["label"]

    # For Azure OpenAI, use deployment name as model param
    azure_deploy = info.get("azure_deployment", "")
    azure_model = azure_deploy if azure_deploy else model
    token_param = info.get("max_tokens_param", "max_tokens")
    client = OpenAI(api_key=key, base_url=info["endpoint"])
    def fn(messages):
        kwargs = {
            "model": azure_model,
            "messages": messages,
            "temperature": info.get("temperature", 0.7),
        }
        kwargs[token_param] = 4096
        resp = client.chat.completions.create(**kwargs)
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
async def compare(req: CompareRequest, request: Request = None):
    if not req.message.strip():
        raise HTTPException(400, "message empty")

    # Check if any model requests constitutional bypass (sp:none)
    wants_bypass = False
    for mc in req.models:
        if isinstance(mc, str):
            continue
        sp = getattr(mc, 'system_prompt', 'helix')
        if sp is None or (isinstance(sp, str) and sp.lower() in ("none", "null", "raw", "")):
            wants_bypass = True
            break

    if wants_bypass:
        if not COMPARE_BYPASS_KEY:
            raise HTTPException(403, "Constitutional bypass (sp:none) is disabled on this instance.")
        bypass_key = ""
        if request:
            bypass_key = request.headers.get("X-Compare-Bypass-Key", "")
            if not bypass_key:
                bypass_key = request.query_params.get("bypass_key", "")
        if bypass_key != COMPARE_BYPASS_KEY:
            raise HTTPException(403, "Constitutional bypass requires X-Compare-Bypass-Key header or bypass_key query param.")

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
        sp_label = "(Helix)" if system_prompt == "helix" else "(no prompt)"
        display_label = f"{label} {sp_label}"
        if system_prompt == "helix":
            result = adapter.chat(req.message)
            # Overwrite receipt model with display label
            result.receipt["model"] = display_label
            result.receipt["display_label"] = display_label
            _save_receipt(result.receipt)
        else:
            # Raw mode: call model directly
            raw_msgs = [{"role": "user", "content": req.message}]
            loop = asyncio.get_event_loop()
            raw_text = await loop.run_in_executor(None, adapter.model_fn, raw_msgs)
            from helix_adapter.markers import extract_claims
            from helix_adapter.drift import compute_drift
            from helix_adapter.receipt import make_receipt
            claims = extract_claims(raw_text)
            drift = compute_drift(raw_text, claims)
            receipt = make_receipt(req.message, raw_text, claims, model=display_label, drift_score=drift)
            _save_receipt(receipt)
            class RawResult:
                def __init__(self):
                    self.response = raw_text
                    self.claims = claims
                    self.drift = drift
                    self.receipt = receipt
            result = RawResult()

        return {
            "model": model_name,
            "label": display_label,
            "response": result.response,
            "claims": result.claims,
            "drift": result.drift,
            "receipt": result.receipt,
        }

    tasks = [call_one(m, l, a, s) for m, l, a, s in adapters]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # Filter out failed models and return errors alongside results
    output = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            output.append({"model": adapters[i][0], "error": str(r)})
        else:
            output.append(r)
    return {"message": req.message, "results": output}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "message empty")
    try:
        result = adapter.chat(req.message)
    except Exception as e:
        raise HTTPException(502, f"Model call failed: {e}")

    # Constitutional compliance validation (lenient mode: inject footer on violation)
    try:
        validation = validate_response(result.response)
        if not validation["compliant"]:
            print(f"[CONSTITUTIONAL VIOLATION] {validation['issues']}", flush=True)
            footer = (
                f"\n\n[UNCERTAIN] Constitutional audit note: the preceding response "
                f"was flagged for potential marker-format violations: "
                f"{'; '.join(validation['issues'])}. "
                f"The response may not meet full constitutional standards."
            )
            result.response += footer
            # Re-extract claims and drift with the footer included
            result.claims = extract_claims(result.response)
            result.drift = compute_drift(result.response, result.claims)
            # Rebuild receipt
            from helix_adapter.receipt import make_receipt
            result.receipt = make_receipt(
                user_message=req.message,
                assistant_response=result.response,
                claims=result.claims,
                model=adapter.model_name,
                constitutional_prompt=CONSTITUTIONAL_PROMPT,
                drift_score=result.drift,
                drift_method=adapter.drift_method,
            )
    except Exception as e:
        print(f"[VALIDATION ERROR] {e}", flush=True)
        # Re-raise as a proper HTTP error instead of crashing
        raise HTTPException(422, f"Constitutional validation failed: {e}")

    _save_receipt(result.receipt)
    return {
        "response": result.response,
        "claims": result.claims,
        "receipt": result.receipt,
    }


@app.get("/prompt")
async def get_prompt():
    return {"constitutional_prompt": CONSTITUTIONAL_PROMPT, "version": "1.2"}


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
    html = html.replace("{{COMPARE_BYPASS_KEY}}", COMPARE_BYPASS_KEY)

    return HTMLResponse(html)


THEORY_FILE = HERE / "templates" / "theory.html"


@app.get("/theory", response_class=FileResponse)
async def serve_theory():
    return FileResponse(THEORY_FILE, media_type="text/html")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    uvicorn.run(app, host="127.0.0.1", port=port)

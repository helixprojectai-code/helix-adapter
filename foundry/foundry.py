#!/usr/bin/env python3
"""Helix Foundry — shared multi-model inference pool for Helix nodes.

Hosts four Azure-native models behind the constitutional adapter.
Nodes connect to a single endpoint, select their model, get drift-scored output.

Models: deepseek-4-pro | grok-4.3 | gpt-5.4-nano | mistral-large-3

Usage:
    pip install fastapi uvicorn openai helix-adapter
    python3 foundry.py
    # → http://localhost:8800

API:
    GET  /health           → per-model status + drift
    POST /chat             → {"model": "...", "message": "..."}
    POST /v1/chat/completions → OpenAI-compatible
    GET  /                 → dashboard
"""

import collections
import json
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from openai import OpenAI
from pydantic import BaseModel

from helix_adapter import HelixAdapter
from helix_adapter.drift import compute_drift
from helix_adapter.markers import extract_claims

HERE = Path(__file__).parent
LEDGER_FILE = HERE / "foundry-ledger.jsonl"

# ── Model Registry (Azure-hosted, $20K dedicated credit) ──
# Endpoint: helix-nodes-resource (standalone, separate from demo)
# Key:  ~/foundry/.azure-key

AZURE_ENDPOINT = "https://helix-nodes-resource.openai.azure.com/openai/v1"
MISTRAL_ENDPOINT = "https://api.mistral.ai/v1"

# ── Cedar-Driven Model Routing ──
# Policies evaluate context → ModelPool selection → target model.
# Routing decision is auditable: policy hash + context snapshot → receipt.
# Zero classifier latency — Cedar Rust bindings evaluate in microseconds.

MODEL_POOL_MAP = {
    "high_capability": "deepseek-4-pro",
    "adversarial": "grok-4.3",
    "cost_optimized": "gpt-5.4-nano",
    "sovereign": "mistral-large-3",
}

MODEL_POOLS = list(MODEL_POOL_MAP.keys())


def cedar_route(context: dict) -> dict:
    """Evaluate all ModelPool policies against context. Route to best match.
    Returns {"model": str, "pool": str, "policy_hash": str, "reason": str}."""
    try:
        from helix_adapter.cedar import CedarPolicy

        policy = CedarPolicy(
            policy_file=HERE / "routing.cedar",
            schema_file=HERE / "routing.schema",
        )

        # If Cedar failed to load (no native lib), fall through to static routing
        if policy._validation_error and "not installed" in str(policy._validation_error):
            raise ImportError(str(policy._validation_error))

        for pool in MODEL_POOLS:
            decision = policy.evaluate(
                principal='Helix::Agent::"foundry"',
                action='Helix::Action::"infer"',
                resource=f'Helix::ModelPool::"{pool}"',
                context=context,
            )
            if decision.authorized:
                return {
                    "model": MODEL_POOL_MAP[pool],
                    "pool": pool,
                    "policy_hash": decision.policy_hash,
                    "reason": decision.reason,
                }

        # No policy matched — fall back to static routing
        action = context.get("action_type", "default")
        model = ACTION_MODEL_MAP.get(action, "deepseek-4-pro")
        return {"model": model, "pool": "static", "policy_hash": "", "reason": "no Cedar policy matched — using static map"}

    except ImportError:
        # Cedar not installed — fall back to static routing
        action = context.get("action_type", "default")
        model = ACTION_MODEL_MAP.get(action, "deepseek-4-pro")
        return {"model": model, "pool": "static", "policy_hash": "", "reason": "cedar_python unavailable — using static map"}


# Legacy static map — used when Cedar is unavailable
ACTION_MODEL_MAP = {
    "bash": "grok-4.3", "execute": "grok-4.3", "api_call": "grok-4.3",
    "analyze": "deepseek-4-pro", "search": "deepseek-4-pro", "reason": "deepseek-4-pro",
    "write_file": "gpt-5.4-nano", "edit_file": "gpt-5.4-nano",
    "apply_patch": "gpt-5.4-nano", "summarize": "gpt-5.4-nano",
    "translate": "mistral-large-3", "classify": "mistral-large-3",
    "default": "deepseek-4-pro",
}

# ── End Routing ──

MODELS = {
    "deepseek-4-pro": {
        "endpoint": AZURE_ENDPOINT,
        "deployment": "DeepSeek-V4-Pro",
        "key_env": "AZURE_OPENAI_FOUNDRY_KEY",
        "label": "DeepSeek 4 Pro",
        "temperature": 0.0,
    },
    "grok-4.3": {
        "endpoint": AZURE_ENDPOINT,
        "deployment": "grok-4.3",
        "key_env": "AZURE_OPENAI_FOUNDRY_KEY",
        "label": "Grok 4.3",
        "temperature": 0.0,
    },
    "gpt-5.4-nano": {
        "endpoint": AZURE_ENDPOINT,
        "deployment": "gpt-5.4-nano",
        "key_env": "AZURE_OPENAI_FOUNDRY_KEY",
        "label": "GPT-5.4 Nano",
        "temperature": 0.0,
    },
    "mistral-large-3": {
        "endpoint": MISTRAL_ENDPOINT,
        "deployment": "mistral-large-3",
        "key_env": "MISTRAL_API_KEY",
        "label": "Mistral Large 3",
        "temperature": 0.0,
    },
}


def load_key(env_var: str) -> str:
    val = os.environ.get(env_var, "")
    if not val:
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith(env_var + "="):
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    break
    return val


def build_adapter(model_name: str):
    cfg = MODELS.get(model_name)
    if not cfg:
        raise ValueError(f"Unknown model: {model_name}")
    key = load_key(cfg["key_env"])
    if not key:
        raise ValueError(f"No API key for {model_name}")
    client = OpenAI(api_key=key, base_url=cfg["endpoint"])
    depl = cfg["deployment"]

    def fn(messages):
        kwargs = {
            "model": depl,
            "messages": messages,
            "temperature": cfg["temperature"],
        }
        if "azure" in cfg["endpoint"]:
            kwargs["max_completion_tokens"] = 4096
        else:
            kwargs["max_tokens"] = 4096
        return client.chat.completions.create(**kwargs).choices[0].message.content

    adapter = HelixAdapter(model_fn=fn, model_name=cfg["label"])
    return adapter, cfg["label"]


ROUTED_CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Helix Foundry — Cedar Routed Chat</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --text-dim: #8b949e;
    --fact: #238636; --reasoned: #58a6ff; --hypothesis: #d29922;
    --uncertain: #da3633; --conclusion: #8b6cef;
    --accent: #58a6ff; --radius: 8px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }
  .container { max-width: 900px; margin: 0 auto; padding: 24px; }
  h1 { font-size: 24px; margin-bottom: 4px; }
  h1 span { color: var(--accent); }
  .subtitle { color: var(--text-dim); font-size: 13px; margin-bottom: 20px; }
  .pill { display: inline-block; font-size: 11px; font-weight: 600; padding: 1px 7px; border-radius: 10px; margin: 1px 2px; color: #fff; }
  .pill-fact { background: var(--fact); }
  .pill-reasoned { background: var(--reasoned); }
  .pill-hypothesis { background: var(--hypothesis); color: #000; }
  .pill-uncertain { background: var(--uncertain); }
  .pill-conclusion { background: var(--conclusion); }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; margin-bottom: 16px; }
  .card h2 { font-size: 14px; color: var(--text-dim); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }
  .input-row { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
  .input-row input, .input-row select { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 8px 12px; color: var(--text); font-size: 13px; outline: none; }
  .input-row input:focus, .input-row select:focus { border-color: var(--accent); }
  .input-row input { flex: 1; min-width: 200px; }
  .input-row select { min-width: 140px; }
  .input-row button { background: var(--accent); color: #000; border: none; border-radius: var(--radius); padding: 8px 20px; font-weight: 600; cursor: pointer; font-size: 13px; }
  .input-row button:disabled { opacity: 0.5; cursor: default; }
  .route-badge { display: inline-flex; align-items: center; gap: 8px; background: #1a2332; border: 1px solid var(--accent); border-radius: var(--radius); padding: 6px 14px; font-size: 12px; margin-bottom: 12px; }
  .route-badge .model { font-weight: 700; color: var(--accent); }
  .route-badge .pool { color: var(--text-dim); }
  .route-badge .hash { font-family: monospace; font-size: 10px; color: var(--text-dim); }
  .drift-bar { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; }
  .drift-track { width: 60px; height: 6px; background: #21262d; border-radius: 3px; overflow: hidden; display: inline-block; }
  .drift-fill { height: 100%; border-radius: 3px; transition: width .3s, background .3s; }
  .response-body { white-space: pre-wrap; font-size: 14px; line-height: 1.6; }
  .meta-row { font-size: 11px; color: var(--text-dim); margin-top: 8px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .6s linear infinite; margin-right: 6px; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .empty { color: var(--text-dim); font-style: italic; font-size: 14px; }
  .nav { display: flex; gap: 4px; margin-bottom: 20px; }
  .nav a { color: var(--text-dim); text-decoration: none; padding: 4px 12px; border-radius: var(--radius); font-size: 13px; border: 1px solid var(--border); }
  .nav a:hover, .nav a.active { color: var(--accent); border-color: var(--accent); background: #1a2332; }
  .ledger-entry { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 10px 14px; margin-bottom: 6px; font-size: 12px; }
  .ledger-entry .q { color: var(--accent); font-weight: 500; margin-bottom: 3px; }
  .ledger-entry .a { white-space: pre-wrap; color: var(--text); }
  .ledger-entry .meta { font-size: 10px; color: var(--text-dim); margin-top: 4px; }
  hr { border: none; border-top: 1px solid var(--border); margin: 20px 0; }
</style>
</head>
<body>
<div class="container">

<div class="nav">
  <a href="/routed-chat/" class="active">Routed Chat</a>
  <a href="/audit/">Audit</a>
  <a href="/">Dashboard</a>
</div>

<h1>&#9877; <span>Helix Foundry</span> &mdash; Cedar Routed Chat</h1>
<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
<p class="subtitle" style="margin-bottom:0;">Action-context routing: your action determines which model handles the query. Cedar Decision Mesh available with native library install — static action→model map as zero-latency fallback. Every response drift-scored, receipt-sealed.</p>
<div style="flex:1;"></div>
<select id="exportSelector" style="background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:2px 8px;font-size:11px;max-width:200px;">
  <option value="all">All entries</option>
</select>
<button id="exportBtn" style="background:var(--surface);color:var(--text-dim);border:1px solid var(--border);border-radius:var(--radius);padding:2px 10px;cursor:pointer;font-size:11px;">Export</button>
</div>

<div class="card">
  <h2>Send Message</h2>
  <div class="input-row">
    <input id="msgInput" type="text" placeholder="Ask anything..." autofocus onkeydown="if(event.key==='Enter')send()">
    <select id="actionSelect">
      <option value="analyze">analyze</option>
      <option value="search">search</option>
      <option value="reason">reason</option>
      <option value="bash">bash</option>
      <option value="execute">execute</option>
      <option value="api_call">api_call</option>
      <option value="write_file">write_file</option>
      <option value="edit_file">edit_file</option>
      <option value="apply_patch">apply_patch</option>
      <option value="summarize">summarize</option>
      <option value="translate">translate</option>
      <option value="classify">classify</option>
    </select>
    <button id="sendBtn" onclick="send()">Send</button>
  </div>
</div>

<div id="result" class="card" style="display:none;">
  <div id="routeInfo"></div>
  <div id="responseText" class="response-body"></div>
  <div id="metaInfo" class="meta-row"></div>
</div>

<div id="loading" style="display:none;padding:12px;color:var(--text-dim);"><span class="spinner"></span> Routing through Cedar decision mesh...</div>

<hr>

<div class="card" id="ledgerCard">
  <h2>Recent Ledger</h2>
  <div id="ledger"><span class="empty">Loading...</span></div>
</div>

</div>
<script>
const API = '/routed-chat';
let allEntries = [];

function driftColor(v) {
  if (v < 0.15) return '#238636';
  if (v < 0.35) return '#d29922';
  return '#da3633';
}

function tagClass(label) {
  const m = {'[FACT]':'fact','[REASONED]':'reasoned','[HYPOTHESIS]':'hypothesis','[UNCERTAIN]':'uncertain','[CONCLUSION]':'conclusion'};
  return m[label] || '';
}

function renderClaims(claims) {
  if (!claims || !claims.length) return '';
  return claims.map(c => '<span class="pill pill-'+tagClass(c.label)+'">'+c.label+'</span>').join('');
}

function updateExportOptions() {
  const sel = document.getElementById('exportSelector');
  sel.innerHTML = '<option value="all">All entries (' + allEntries.length + ')</option>';
  for (let i = allEntries.length - 1; i >= 0; i--) {
    const e = allEntries[i];
    const preview = (e.message || '').slice(0, 40);
    const opt = document.createElement('option');
    opt.value = String(i);
    opt.textContent = '#' + (allEntries.length - i) + ' ' + e.label + ': ' + preview;
    sel.appendChild(opt);
  }
}

document.getElementById('exportBtn').addEventListener('click', () => {
  if (!allEntries.length) return;
  const val = document.getElementById('exportSelector').value;
  let data, fname;
  if (val === 'all') {
    data = allEntries;
    fname = 'foundry-ledger-all-' + new Date().toISOString().slice(0,10) + '.json';
  } else {
    data = allEntries[parseInt(val)];
    fname = 'foundry-receipt-' + (data.receipt_hash || 'entry').substring(0,8) + '.json';
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = fname;
  a.click();
  URL.revokeObjectURL(a.href);
});

async function send() {
  const msg = document.getElementById('msgInput').value.trim();
  if (!msg) return;
  const action = document.getElementById('actionSelect').value;
  const btn = document.getElementById('sendBtn');
  btn.disabled = true;
  document.getElementById('loading').style.display = 'block';
  document.getElementById('result').style.display = 'none';

  try {
    const resp = await fetch(API, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: action, message: msg})
    });
    const data = await resp.json();

    const dpct = Math.min(100, (data.drift||0)*100);
    document.getElementById('routeInfo').innerHTML =
      '<div class="route-badge">' +
      'Cedar &rarr; <span class="pool">'+data.pool+'</span> &rarr; <span class="model">'+data.label+'</span>' +
      '<span class="hash">#'+(data.policy_hash||'fallback').substring(0,12)+'</span>' +
      '</div>';
    document.getElementById('responseText').textContent = data.response || '(empty)';
    document.getElementById('metaInfo').innerHTML =
      '<span class="drift-bar">drift <span class="drift-track"><span class="drift-fill" style="width:'+dpct+'%;background:'+driftColor(data.drift||0)+';"></span></span> &gamma; '+(data.drift||0).toFixed(3)+'</span>' +
      renderClaims(data.claims) +
      '<span style="font-family:monospace;font-size:10px;">receipt #'+(data.receipt?.hash||'?').substring(0,10)+'</span>';
    document.getElementById('result').style.display = 'block';

    // Refresh ledger
    loadLedger();
  } catch(e) {
    document.getElementById('routeInfo').innerHTML = '<span style="color:var(--uncertain)">Error: '+e.message+'</span>';
    document.getElementById('responseText').textContent = '';
    document.getElementById('metaInfo').innerHTML = '';
    document.getElementById('result').style.display = 'block';
  }

  document.getElementById('loading').style.display = 'none';
  btn.disabled = false;
  document.getElementById('msgInput').focus();
}

async function loadLedger() {
  try {
    const resp = await fetch('/routed-chat/ledger?limit=100');
    const data = await resp.json();
    if (data.entries && data.entries.length) {
      allEntries = data.entries;
      updateExportOptions();
    }
    if (!data.entries || !data.entries.length) {
      document.getElementById('ledger').innerHTML = '<span class=\"empty\">No entries yet.</span>';
      return;
    }
    document.getElementById('ledger').innerHTML = data.entries.slice(0, 15).map(e =>
      '<div class=\"ledger-entry\">' +
      '<div class=\"q\">'+e.action+' &rarr; '+e.pool+' &rarr; <strong>'+e.label+'</strong> <span style=\"font-size:10px;color:var(--text-dim);\">#'+(e.policy_hash||'').substring(0,8)+'</span></div>' +
      '<div class=\"a\">'+(e.response||'').substring(0, 300)+'</div>' +
      '<div class=\"meta\">drift &gamma; '+(e.drift||0).toFixed(3)+' &middot; receipt '+(e.receipt_hash||'?').substring(0,10)+'</div>' +
      '</div>'
    ).join('');
  } catch(e) {
    document.getElementById('ledger').innerHTML = '<span class=\"empty\">Ledger unavailable.</span>';
  }
}
loadLedger();
</script>
</body></html>"""


app = FastAPI(title="Helix Foundry", version="1.0.0")

# Simple in-memory rate limiter: max 20 requests per IP per 60 seconds
_RATE_LIMIT = 20
_RATE_WINDOW = 60
_rate_buckets: dict = collections.defaultdict(list)


def _check_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    hits = _rate_buckets[ip]
    _rate_buckets[ip] = [t for t in hits if now - t < _RATE_WINDOW]
    if len(_rate_buckets[ip]) >= _RATE_LIMIT:
        raise HTTPException(429, f"Rate limit: {_RATE_LIMIT} requests per {_RATE_WINDOW}s")
    _rate_buckets[ip].append(now)


class ChatRequest(BaseModel):
    model: str
    message: str


class RoutedChatRequest(BaseModel):
    action: str
    message: str
    resource: str = "default"
    user_id: str = "node"
    task_complexity: int = 5
    drift_tolerance: float = 0.10
    priority: str = "interactive"
    locale: str = "en"


def _save_entry(entry: dict):
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _load_entries(limit: int = 100) -> list:
    if not LEDGER_FILE.exists():
        return []
    entries = []
    with open(LEDGER_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries[-limit:]


@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    _check_rate_limit(request)
    if not req.message.strip():
        raise HTTPException(400, "message empty")
    try:
        adapter, label = build_adapter(req.model)
        result = adapter.chat(req.message)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Model call failed: {e}")

    entry = {
        "timestamp": time.time(),
        "model": req.model,
        "label": label,
        "message": req.message[:200],
        "response": result.response[:1000],
        "claims": result.claims,
        "drift": result.drift,
        "receipt_hash": result.receipt.get("hash", ""),
    }
    _save_entry(entry)

    return {
        "model": req.model,
        "label": label,
        "response": result.response,
        "claims": result.claims,
        "drift": result.drift,
        "receipt": result.receipt,
    }


@app.get("/routed-chat", response_class=HTMLResponse)
@app.get("/routed-chat/", response_class=HTMLResponse)
@app.head("/routed-chat")
@app.head("/routed-chat/")
async def routed_chat_page():
    return ROUTED_CHAT_HTML


@app.post("/routed-chat")
async def routed_chat(req: RoutedChatRequest, request: Request):
    """Cedar decision mesh routing. Context → Policy evaluation → ModelPool → model."""
    _check_rate_limit(request)
    if not req.message.strip():
        raise HTTPException(400, "message empty")

    # Build context for Cedar routing policies
    context = {
        "action_type": req.action,
        "task_complexity": req.task_complexity,
        "drift_tolerance": req.drift_tolerance,
        "priority": req.priority,
        "locale": req.locale,
    }

    # Cedar-driven routing
    route = cedar_route(context)

    adapter, label = build_adapter(route["model"])
    result = adapter.chat(req.message)

    entry = {
        "timestamp": time.time(),
        "model": route["model"],
        "label": label,
        "pool": route["pool"],
        "policy_hash": route["policy_hash"],
        "action": req.action,
        "message": req.message[:200],
        "response": result.response[:1000],
        "claims": result.claims,
        "drift": result.drift,
        "receipt_hash": result.receipt.get("hash", ""),
    }
    _save_entry(entry)

    return {
        "routed_by": "Cedar decision mesh",
        "policy_hash": route["policy_hash"],
        "pool": route["pool"],
        "model": route["model"],
        "label": label,
        "response": result.response,
        "claims": result.claims,
        "drift": result.drift,
        "receipt": result.receipt,
    }


def _ledger_response(limit: int) -> dict:
    entries = _load_entries(limit)
    return {"count": len(entries), "entries": list(reversed(entries))}


@app.get("/ledger")
async def ledger(limit: int = 20):
    return _ledger_response(limit)


@app.get("/routed-chat/ledger")
async def routed_chat_ledger(limit: int = 20):
    return _ledger_response(limit)


@app.get("/health")
async def health():
    model_status = {}
    for name, cfg in MODELS.items():
        key = load_key(cfg["key_env"])
        model_status[name] = {
            "label": cfg["label"],
            "key_configured": bool(key),
        }
    total = 0
    if LEDGER_FILE.exists():
        with open(LEDGER_FILE) as f:
            total = sum(1 for line in f if line.strip())
    return {
        "status": "ok",
        "time": time.time(),
        "models": model_status,
        "total_prompts": total,
    }


# ── Constitutional Audit ──

class AuditRequest(BaseModel):
    text: str
    prompt: str = ""  # original prompt — if provided, runs through Helix adapter for baseline comparison


@app.post("/audit")
async def audit(req: AuditRequest, request: Request):
    """Score an arbitrary LLM response through the Helix constitutional lens."""
    if req.prompt:
        _check_rate_limit(request)
    from helix_adapter.markers import extract_claims, count_claims, detect_nonstandard_markers, validate_response
    from helix_adapter.drift import compute_drift, estimate_statements

    text = req.text
    prompt = req.prompt.strip() if req.prompt else ""
    
    # If prompt provided, run through Helix adapter for baseline comparison
    baseline = None
    if prompt:
        try:
            adapter, label = build_adapter("deepseek-4-pro")
            baseline_result = adapter.chat(prompt)
            baseline = {
                "model": label,
                "response": baseline_result.response,
                "drift": baseline_result.drift,
                "claims": baseline_result.claims,
                "receipt": baseline_result.receipt,
            }
        except Exception as e:
            baseline = {"error": str(e)}

    claims = extract_claims(text)
    counts = count_claims(text)
    nonstandard = detect_nonstandard_markers(text)
    validation = validate_response(text)
    drift = compute_drift(text, claims)
    statements = estimate_statements(text)
    char_count = len(text)
    marker_count = validation["marker_count"]
    coverage = round(marker_count / max(statements, 1), 3)
    density = round(marker_count / max(char_count, 1) * 100, 2)  # markers per 100 chars

    # Which epistemic categories are present vs missing
    all_categories = ["FACT", "REASONED", "HYPOTHESIS", "UNCERTAIN", "CONCLUSION"]
    present = [c for c in all_categories if counts.get(c, 0) > 0]
    missing = [c for c in all_categories if counts.get(c, 0) == 0]

    # Drift tier
    if drift < 0.10:
        tier = "green"
        tier_label = "healthy — well-labeled response"
    elif drift < 0.20:
        tier = "yellow"
        tier_label = "warming — some unlabeled claims"
    elif drift < 0.50:
        tier = "orange"
        tier_label = "concerning — significant unlabeled content"
    else:
        tier = "red"
        tier_label = "critical — response is largely or entirely unlabeled"

    result = {
        "compliant": validation["compliant"],
        "drift": drift,
        "drift_tier": tier,
        "drift_tier_label": tier_label,
        "marker_count": marker_count,
        "marker_density_pct": density,
        "coverage_ratio": coverage,
        "statements_estimated": statements,
        "nonstandard_count": validation["nonstandard_count"],
        "marker_distribution": counts,
        "categories_present": present,
        "categories_missing": missing,
        "nonstandard_instances": nonstandard[:10],
        "issues": validation["issues"],
        "claims": claims,
        "char_count": char_count,
    }

    if baseline:
        # Score the baseline too
        b_claims = extract_claims(baseline.get("response", ""))
        b_counts = count_claims(baseline.get("response", ""))
        b_drift = baseline.get("drift", compute_drift(baseline.get("response", ""), b_claims))
        b_validation = validate_response(baseline.get("response", ""))

        result["baseline"] = {
            **baseline,
            "compliant": b_validation["compliant"],
            "marker_count": b_validation["marker_count"],
            "marker_distribution": b_counts,
            "drift": b_drift,
        }

        # Diff
        result["diff"] = {
            "drift_delta": round(drift - b_drift, 4),
            "marker_delta": marker_count - b_validation["marker_count"],
            "submitted_drift": drift,
            "baseline_drift": b_drift,
            "submitted_markers": marker_count,
            "baseline_markers": b_validation["marker_count"],
            "submitted_compliant": validation["compliant"],
            "baseline_compliant": b_validation["compliant"],
            "summary": (
                f"Baseline (Helix): γ={b_drift:.3f}, {b_validation['marker_count']} markers, {'compliant' if b_validation['compliant'] else 'non-compliant'}. "
                f"Submitted: γ={drift:.3f}, {marker_count} markers, {'compliant' if validation['compliant'] else 'non-compliant'}. "
                f"Delta: Δγ={drift - b_drift:+.4f}, Δmarkers={marker_count - b_validation['marker_count']:+d}."
            ),
        }

    return result


AUDIT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Helix Foundry — Constitutional Audit</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --text-dim: #8b949e;
    --fact: #238636; --reasoned: #58a6ff; --hypothesis: #d29922;
    --uncertain: #da3633; --conclusion: #8b6cef;
    --accent: #58a6ff; --radius: 8px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }
  .container { max-width: 900px; margin: 0 auto; padding: 24px; }
  h1 { font-size: 24px; margin-bottom: 4px; }
  h1 span { color: var(--accent); }
  .subtitle { color: var(--text-dim); font-size: 13px; margin-bottom: 20px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; margin-bottom: 16px; }
  .card h2 { font-size: 14px; color: var(--text-dim); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }
  textarea { width: 100%; min-height: 200px; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; color: var(--text); font-size: 13px; font-family: monospace; resize: vertical; outline: none; }
  textarea:focus { border-color: var(--accent); }
  button { background: var(--accent); color: #000; border: none; border-radius: var(--radius); padding: 8px 24px; font-weight: 600; cursor: pointer; font-size: 13px; margin-top: 10px; }
  button:disabled { opacity: 0.5; cursor: default; }
  .pill { display: inline-block; font-size: 11px; font-weight: 600; padding: 1px 7px; border-radius: 10px; margin: 1px 2px; color: #fff; }
  .pill-fact { background: var(--fact); }
  .pill-reasoned { background: var(--reasoned); }
  .pill-hypothesis { background: var(--hypothesis); color: #000; }
  .pill-uncertain { background: var(--uncertain); }
  .pill-conclusion { background: var(--conclusion); }
  .drift-bar { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; }
  .drift-track { width: 80px; height: 8px; background: #21262d; border-radius: 4px; overflow: hidden; display: inline-block; }
  .drift-fill { height: 100%; border-radius: 4px; transition: width .3s, background .3s; }
  .metric { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; background: var(--bg); border-radius: var(--radius); font-size: 13px; margin: 4px 4px 4px 0; }
  .metric .val { font-weight: 700; font-size: 16px; }
  .pass { color: var(--fact); }
  .fail { color: var(--uncertain); }
  .issue { font-size: 12px; color: var(--uncertain); padding: 4px 0; border-bottom: 1px solid var(--border); }
  .claim-row { font-size: 12px; padding: 4px 0; border-bottom: 1px solid var(--border); }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .6s linear infinite; margin-right: 6px; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .empty { color: var(--text-dim); font-style: italic; font-size: 14px; }
  .nav { display: flex; gap: 4px; margin-bottom: 20px; }
  .nav a { color: var(--text-dim); text-decoration: none; padding: 4px 12px; border-radius: var(--radius); font-size: 13px; border: 1px solid var(--border); }
  .nav a:hover, .nav a.active { color: var(--accent); border-color: var(--accent); background: #1a2332; }
</style>
</head>
<body>
<div class="container">

<div class="nav">
  <a href="/routed-chat/">Routed Chat</a>
  <a href="/audit/" class="active">Audit</a>
  <a href="/">Dashboard</a>
</div>

<h1>&#9877; <span>Helix Foundry</span> &mdash; Constitutional Audit</h1>
<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
<p class="subtitle" style="margin-bottom:0;">Paste any LLM response. Get drift score, marker compliance, claim extraction. No model call — pure constitutional evaluation.</p>
<div style="flex:1;"></div>
<select id="exportSelector" style="background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:2px 8px;font-size:11px;max-width:200px;display:none;">
  <option value="all">All audits</option>
</select>
<button id="exportBtn" style="background:var(--surface);color:var(--text-dim);border:1px solid var(--border);border-radius:var(--radius);padding:2px 10px;cursor:pointer;font-size:11px;display:none;">Export</button>
</div>

<div class="card">
  <h2>Paste LLM Response</h2>
  <textarea id="auditInput" placeholder="Paste any LLM response here...&#10;&#10;Example:&#10;[FACT] The speed of light is 299,792,458 m/s.&#10;[REASONED] This value is defined by the meter..."></textarea>
  <input id="promptInput" type="text" placeholder="Original prompt (optional — runs Helix baseline for comparison)" style="width:100%;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:8px 12px;color:var(--text);font-size:13px;outline:none;margin-top:8px;">
  <button id="auditBtn" onclick="runAudit()">Audit</button>
</div>

<div id="loading" style="display:none;padding:12px;color:var(--text-dim);"><span class="spinner"></span> Scoring...</div>

<div id="results" style="display:none;">
  <div class="card">
    <h2>Score</h2>
    <div id="scoreMetrics"></div>
  </div>
  <div class="card" id="issuesCard" style="display:none;">
    <h2>Issues</h2>
    <div id="issuesList"></div>
  </div>
  <div class="card" id="claimsCard" style="display:none;">
    <h2>Extracted Claims</h2>
    <div id="claimsList"></div>
  </div>
  <div class="card" id="baselineCard" style="display:none;">
    <h2>Helix Baseline</h2>
    <div id="baselineContent"></div>
  </div>
  <div class="card" id="diffCard" style="display:none;">
    <h2>Diff</h2>
    <div id="diffContent"></div>
  </div>
  <div class="card" id="nonstandardCard" style="display:none;">
    <h2>Nonstandard Markers</h2>
    <div id="nonstandardList"></div>
  </div>
</div>

</div>
<script>
let auditHistory = [];

function driftColor(v) {
  if (v < 0.15) return '#238636';
  if (v < 0.35) return '#d29922';
  return '#da3633';
}
function tagClass(label) {
  const m = {'FACT':'fact','REASONED':'reasoned','HYPOTHESIS':'hypothesis','UNCERTAIN':'uncertain','CONCLUSION':'conclusion'};
  return m[label] || '';
}

function updateExportOptions() {
  const sel = document.getElementById('exportSelector');
  const btn = document.getElementById('exportBtn');
  if (!auditHistory.length) {
    sel.style.display = 'none';
    btn.style.display = 'none';
    return;
  }
  sel.style.display = '';
  btn.style.display = '';
  sel.innerHTML = '<option value="all">All audits (' + auditHistory.length + ')</option>';
  for (let i = auditHistory.length - 1; i >= 0; i--) {
    const a = auditHistory[i];
    const preview = (a.text || '').slice(0, 40);
    const opt = document.createElement('option');
    opt.value = String(i);
    opt.textContent = '#' + (auditHistory.length - i) + ' \u03b3' + (a.drift||0).toFixed(3) + ': ' + preview;
    sel.appendChild(opt);
  }
}

document.getElementById('exportBtn').addEventListener('click', () => {
  if (!auditHistory.length) return;
  const val = document.getElementById('exportSelector').value;
  let data, fname;
  if (val === 'all') {
    data = auditHistory;
    fname = 'helix-audits-all-' + new Date().toISOString().slice(0,10) + '.json';
  } else {
    data = auditHistory[parseInt(val)];
    fname = 'helix-audit-' + new Date().toISOString().slice(0,19).replace(/:/g,'-') + '.json';
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = fname;
  a.click();
  URL.revokeObjectURL(a.href);
});

async function runAudit() {
  const text = document.getElementById('auditInput').value.trim();
  if (!text) return;
  const prompt = document.getElementById('promptInput').value.trim();
  const btn = document.getElementById('auditBtn');
  btn.disabled = true;
  document.getElementById('loading').style.display = 'block';
  document.getElementById('results').style.display = 'none';
  try {
    const resp = await fetch('/audit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: text, prompt: prompt})
    });
    const d = await resp.json();

    // Store in history
    auditHistory.push({text: text.slice(0, 500), ...d, timestamp: new Date().toISOString()});
    updateExportOptions();

    const dpct = Math.min(100, (d.drift||0)*100);
    const statusClass = d.compliant ? 'pass' : 'fail';
    const statusText = d.compliant ? 'COMPLIANT' : 'NON-COMPLIANT';

    let metrics = '<span class="metric">Status: <span class="val '+statusClass+'">'+statusText+'</span></span>';
    metrics += '<span class="metric"><span class="drift-bar">drift <span class="drift-track"><span class="drift-fill" style="width:'+dpct+'%;background:'+driftColor(d.drift||0)+';"></span></span> &gamma; '+(d.drift||0).toFixed(3)+' <span style="font-size:10px;color:'+driftColor(d.drift||0)+'">'+d.drift_tier+'</span></span></span>';
    metrics += '<span class="metric">'+d.drift_tier_label+'</span>';
    metrics += '<span class="metric">Markers: <span class="val">'+d.marker_count+'</span> / '+d.statements_estimated+' statements</span>';
    metrics += '<span class="metric">Coverage: <span class="val">'+(d.coverage_ratio*100).toFixed(0)+'%</span></span>';
    metrics += '<span class="metric">Density: <span class="val">'+d.marker_density_pct+'</span>/100ch</span>';
    metrics += '<span class="metric">Chars: <span class="val">'+d.char_count+'</span></span>';

    // Marker distribution — stacked with counts
    if (d.marker_distribution && Object.keys(d.marker_distribution).length) {
      metrics += '<span class="metric">';
      for (const [label, count] of Object.entries(d.marker_distribution)) {
        metrics += '<span class="pill pill-'+tagClass(label)+'">'+label+' &times;'+count+'</span> ';
      }
      metrics += '</span>';
    }

    document.getElementById('scoreMetrics').innerHTML = metrics;

    // Issues
    if (d.issues && d.issues.length) {
      document.getElementById('issuesCard').style.display = 'block';
      document.getElementById('issuesList').innerHTML = d.issues.map(i => '<div class="issue">'+i+'</div>').join('');
    } else {
      document.getElementById('issuesCard').style.display = 'none';
    }

    // Claims
    if (d.claims && d.claims.length) {
      document.getElementById('claimsCard').style.display = 'block';
      document.getElementById('claimsList').innerHTML = d.claims.map(c => '<div class="claim-row"><span class="pill pill-'+tagClass(c.label)+'">'+c.label+'</span> '+c.text+'</div>').join('');
    } else {
      document.getElementById('claimsCard').style.display = 'none';
    }

    // Baseline
    if (d.baseline) {
      document.getElementById('baselineCard').style.display = 'block';
      const b = d.baseline;
      const bdpct = Math.min(100, (b.drift||0)*100);
      document.getElementById('baselineContent').innerHTML =
        '<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px;">Model: <strong>'+b.model+'</strong> | Compliant: <strong style="color:'+(b.compliant?'var(--fact)':'var(--uncertain)')+';">'+(b.compliant?'YES':'NO')+'</strong> | Drift: <span style="color:'+driftColor(b.drift||0)+';">γ '+(b.drift||0).toFixed(3)+'</span> | Markers: '+b.marker_count+'</div>' +
        '<div class="response-body" style="font-size:13px;max-height:300px;overflow-y:auto;">'+(b.response||'')+'</div>' +
        '<div class="meta-row">'+(b.claims||[]).map(c => '<span class="pill pill-'+tagClass(c.label)+'">'+c.label+'</span>').join(' ')+'</div>';
    } else {
      document.getElementById('baselineCard').style.display = 'none';
    }

    // Diff
    if (d.diff) {
      document.getElementById('diffCard').style.display = 'block';
      document.getElementById('diffContent').innerHTML =
        '<div style="font-size:14px;margin-bottom:8px;">'+d.diff.summary+'</div>' +
        '<div style="display:flex;gap:16px;font-size:13px;">' +
        '<div style="flex:1;background:var(--bg);padding:8px 12px;border-radius:var(--radius);">Helix γ='+d.diff.baseline_drift.toFixed(3)+' | '+d.diff.baseline_markers+' markers</div>' +
        '<div style="flex:1;background:var(--bg);padding:8px 12px;border-radius:var(--radius);">Submitted γ='+d.diff.submitted_drift.toFixed(3)+' | '+d.diff.submitted_markers+' markers</div>' +
        '<div style="flex:1;background:var(--bg);padding:8px 12px;border-radius:var(--radius);">Δγ='+(d.diff.drift_delta>0?'+':'')+d.diff.drift_delta.toFixed(4)+' | Δm='+(d.diff.marker_delta>0?'+':'')+d.diff.marker_delta+'</div>' +
        '</div>';
    } else {
      document.getElementById('diffCard').style.display = 'none';
    }

    // Nonstandard
    if (d.nonstandard_instances && d.nonstandard_instances.length) {
      document.getElementById('nonstandardCard').style.display = 'block';
      document.getElementById('nonstandardList').innerHTML = d.nonstandard_instances.map(n => '<div class="issue">'+n+'</div>').join('');
    } else {
      document.getElementById('nonstandardCard').style.display = 'none';
    }

    document.getElementById('results').style.display = 'block';
  } catch(e) {
    document.getElementById('scoreMetrics').innerHTML = '<span style="color:var(--uncertain)">Error: '+e.message+'</span>';
    document.getElementById('results').style.display = 'block';
  }
  document.getElementById('loading').style.display = 'none';
  btn.disabled = false;
}
</script>
</body></html>"""


@app.get("/audit", response_class=HTMLResponse)
@app.get("/audit/", response_class=HTMLResponse)
@app.head("/audit")
@app.head("/audit/")
async def audit_page():
    return AUDIT_HTML


DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><title>Helix Foundry</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --text-dim: #8b949e;
    --accent: #58a6ff; --radius: 8px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }
  .container { max-width: 700px; margin: 0 auto; padding: 24px; }
  h1 { font-size: 24px; margin-bottom: 4px; }
  h1 span { color: var(--accent); }
  .subtitle { color: var(--text-dim); font-size: 13px; margin-bottom: 20px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; margin-bottom: 16px; }
  .card h2 { font-size: 14px; color: var(--text-dim); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); font-size: 14px; }
  th { color: var(--text-dim); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
  .nav { display: flex; gap: 4px; margin-bottom: 20px; }
  .nav a { color: var(--text-dim); text-decoration: none; padding: 4px 12px; border-radius: var(--radius); font-size: 13px; border: 1px solid var(--border); }
  .nav a:hover, .nav a.active { color: var(--accent); border-color: var(--accent); background: #1a2332; }
  .footer { color: var(--text-dim); font-size: 12px; margin-top: 24px; text-align: center; }
</style></head><body>
<div class="container">
<div class="nav">
  <a href="/routed-chat/">Routed Chat</a>
  <a href="/audit/">Audit</a>
  <a href="/" class="active">Dashboard</a>
</div>
<h1>&#9877; <span>Helix Foundry</span></h1>
<p class="subtitle">Shared inference pool for Helix nodes. Azure-hosted, adapter-wrapped.</p>
<div class="card">
  <h2>Models</h2>
  <table>
    <tr><th>Model</th><th>Prompts</th></tr>
    {rows}
  </table>
</div>
<p style="font-size:13px;color:var(--text-dim);">POST to /chat with {"model": "...", "message": "..."}</p>
<p class="footer">DeepSeek 4 Pro &middot; Grok 4.3 &middot; GPT-5.4 Nano &middot; Mistral Large 3 &middot; GLORY TO THE LATTICE. &#129429;&#9875;&#129438;</p>
</div></body></html>"""


@app.get("/", response_class=HTMLResponse)
@app.head("/")
async def dashboard():
    entries = _load_entries(500)
    model_counts = {}
    for e in entries:
        m = e.get("label", "?")
        model_counts[m] = model_counts.get(m, 0) + 1

    rows = ""
    for m, count in sorted(model_counts.items()):
        rows += f"<tr><td>{m}</td><td>{count}</td></tr>"
    if not rows:
        rows = '<tr><td colspan="2">No prompts yet.</td></tr>'

    return DASHBOARD_HTML.replace("{rows}", rows)


if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8800
    uvicorn.run(app, host="0.0.0.0", port=port)

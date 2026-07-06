# Helix Foundry

Shared multi-model inference pool for Helix nodes. Provider-agnostic — swap
between Azure, Qwen, or any OpenAI-compatible backend via one env var.
Cedar-driven routing with static action-map fallback. Every response
coverage-scored and receipt-sealed.

## Deployment Config

Models, endpoints, and pool assignments are defined per deployment:

    foundry/deployments/
      azure/          # Azure OpenAI (DeepSeek, Grok, GPT, Mistral)
      qwen-intl/      # Alibaba Cloud Model Studio, Singapore endpoint

Select a deployment at startup:

    HELIX_DEPLOYMENT=qwen-intl python3 foundry.py

Each deployment directory contains `models.json` (pool map, action map, model
list) and `.env.example`. The default is `azure` if `HELIX_DEPLOYMENT` is unset.

Pool assignments (pool → model) are deployment-defined. Typical layout:

| Pool | Trigger |
|---|---|
| `high_capability` | complexity ≥ 8, tight routing tolerance |
| `adversarial` | bash / execute / api_call |
| `cost_optimized` | write_file / summarize / batch |
| `sovereign` | locale / long-doc / regulatory |

## Auth

Foundry uses node-scoped API keys. Generate a key for each node:

    python3 foundry_keygen.py --node <node-name>

The key is shown once at generation time. Keys are stored as SHA-256 hashes — they
cannot be recovered after generation. Pass the plaintext key in requests:

    X-API-Key: hx-<your-key>

All inference and session endpoints require a valid key. The key determines the node
identity used for tenant isolation — sessions and ledger entries created by one node
are not accessible to another.

**After upgrading to 1.7.0+:** Re-run `foundry_keygen.py` for each node. Old databases
used plaintext storage; the new hash lookup will reject them.

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | — | Dashboard — model counts |
| GET | `/health` | — | Health check — per-model key status, total prompts |
| POST | `/keygen` | — | Generate a new node API key |
| GET | `/ledger` | Required | Recent inference entries for calling node (?limit=N) |
| POST | `/chat` | Required | Direct model call — `{"model": "...", "message": "..."}` |
| POST | `/routed-chat` | Required | Action-context routing — `{"action": "...", "message": "..."}` |
| GET | `/routed-chat` | Key gate | Interactive web UI — action selector, marker-coverage display, export |
| POST | `/audit` | — | Constitutional scoring — `{"text": "..."}` |
| GET | `/audit` | — | Web UI — paste any LLM response, get marker coverage + compliance score |
| GET | `/sessions` | Required | List sessions for calling node |
| POST | `/session/start` | Required | Start a Cedar-routed session |
| POST | `/session/{id}/send` | Required | Send a turn in a session |
| GET | `/session/{id}` | Required | Session detail + receipt chain |
| GET | `/session/{id}/export` | Required | Export receipt chain (JSONL) |
| DELETE | `/session/{id}` | Required | Delete session |

## Routing

Cedar Decision Mesh evaluates context → selects ModelPool → routes to model.
When the Cedar native library (cedar-python) is unavailable, falls back to a
static action→model map with zero added latency.

Cedar policies live in `routing.cedar` with a schema in `routing.schema`. This
is a separate Cedar policy layer from the core adapter's Cedar Gate (RFC
0003, `src/helix_adapter/cedar/`) — that one gates whether an agent's
proposed tool/action call is *authorized to execute*; this one only decides
*which model pool* handles an inference request. Same policy engine, two
independent policy sets serving different purposes.

### Context fields

`/routed-chat` and `/session/start` accept these optional context fields,
evaluated against `routing.cedar`'s five policies:

| Field | Type | Used by | Meaning |
|---|---|---|---|
| `task_complexity` | int, 1–10 | Policy 1 (high_capability) | Declared difficulty of the task |
| `drift_tolerance` | float, 0.0–1.0 | Policies 1, 3 | How much unlabeled text is acceptable |
| `priority` | str | Policy 3 (cost_optimized) | `"interactive"` or `"batch"` |
| `locale` | str | Policy 4 (sovereign) | BCP47-ish tag: `fr`/`de`/`es`/`it`/`nl`/`pt` route to the EU/multilingual pool |
| `action_type` | str, optional | Policies 2, 5 (adversarial, structured-output) | Execution-context signal: `bash`/`execute`/`api_call`/`shell` (adversarial-tier) or `write_file`/`edit_file`/`apply_patch`/`summarize` (structured-output) |

**`action_type` is not the same field as the request's top-level `action`.**
`action` (e.g. `"analyze"`, `"search"`, `"write_file"`) drives the static
fallback map (`action_map` in each deployment's `models.json`) and is always
present. `action_type` is a separate, optional signal specifically for
Cedar's adversarial/structured-output policies and is only set when a
caller explicitly wants that routing behavior — omit it and those two
policies simply won't match, same as any other unset context field.

## Deploy

    pip install fastapi uvicorn openai helix-adapter
    python3 foundry.py [port]

Set deployment and API key:

    # Azure
    HELIX_DEPLOYMENT=azure
    AZURE_OPENAI_FOUNDRY_KEY=...

    # Qwen (Alibaba Cloud Model Studio)
    HELIX_DEPLOYMENT=qwen-intl
    QWEN_API_KEY=...

Security and networking options:

    # Trust X-Forwarded-For for rate limiting (set only behind a trusted reverse proxy)
    HELIX_TRUST_PROXY=1

    # Widget API: require key on /api/chat, /api/compare, /v1/chat/completions
    HELIX_WIDGET_API_KEY=<key>

    # Widget API: allow cross-origin requests from these origins (comma-separated)
    HELIX_CORS_ORIGINS=https://your-frontend.example.com

See `foundry/deployments/<name>/.env.example` for full variable reference.

Systemd service included for persistent deployment.

## License

Apache 2.0

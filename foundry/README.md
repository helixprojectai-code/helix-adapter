# Helix Foundry

Shared multi-model inference pool for Helix nodes. Provider-agnostic — swap
between Azure, Qwen, or any OpenAI-compatible backend via one env var.
Cedar-driven routing with static action-map fallback. Every response
drift-scored and receipt-sealed.

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
| `high_capability` | complexity ≥ 8, tight drift |
| `adversarial` | bash / execute / api_call |
| `cost_optimized` | write_file / summarize / batch |
| `sovereign` | locale / long-doc / regulatory |

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Dashboard — model counts |
| GET | `/health` | Health check — per-model key status, total prompts |
| GET | `/ledger` | Recent inference entries (JSON, ?limit=N) |
| POST | `/chat` | Direct model call — `{"model": "...", "message": "..."}` |
| POST | `/routed-chat` | Action-context routing — `{"action": "...", "message": "..."}` |
| GET | `/routed-chat` | Interactive web UI — action selector, drift display, export |
| POST | `/audit` | Constitutional scoring — `{"text": "..."}` |
| GET | `/audit` | Web UI — paste any LLM response, get drift + compliance score |

## Routing

Cedar Decision Mesh evaluates context → selects ModelPool → routes to model.
When the Cedar native library (cedar-python) is unavailable, falls back to a
static action→model map with zero added latency.

Cedar policies live in `routing.cedar` with a schema in `routing.schema`.

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

See `foundry/deployments/<name>/.env.example` for full variable reference.

Systemd service included for persistent deployment.

## License

Apache 2.0

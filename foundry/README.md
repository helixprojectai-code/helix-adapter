# Helix Foundry

Shared multi-model inference pool for Helix nodes. Four Azure-native models
behind the constitutional adapter. Cedar-driven routing with static action-map
fallback. Every response drift-scored and receipt-sealed.

## Models

| Model | Pool | Trigger | Drift Profile |
|---|---|---|---|
| DeepSeek 4 Pro | high_capability | default / analyze / search / reason | analytical depth |
| Grok 4.3 | adversarial | bash / execute / api_call | adversarial resilience |
| GPT-5.4 Nano | cost_optimized | write_file / summarize / batch | low-drift bracket discipline |
| Mistral Large 3 | sovereign | fr / de / es / it / nl / pt locale | multilingual |

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

Set API keys in `~/.hermes/.env`:

    AZURE_OPENAI_FOUNDRY_KEY=...
    MISTRAL_API_KEY=...

Systemd service included for persistent deployment.

## License

Apache 2.0

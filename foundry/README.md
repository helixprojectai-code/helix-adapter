# Helix Foundry

Shared multi-model inference pool for Helix nodes. Four Azure-native models
behind the constitutional adapter. One endpoint, four engines.

## Models

- **DeepSeek 4 Pro** — analytical depth, identity boundary work
- **Grok 4.3** — adversarial resilience, held all Pliny attacks
- **GPT-5.4 Nano** — speed, low-drift bracket discipline
- **Mistral Large 3** — European, strong multilingual

## Deploy

    pip install fastapi uvicorn openai helix-adapter
    python3 foundry.py

Set API keys in ~/.hermes/.env:

    AZURE_OPENAI_FOUNDRY_KEY=...
    MISTRAL_API_KEY=...

## Usage

    curl -X POST http://localhost:8800/chat \
      -H "Content-Type: application/json" \
      -d '{"model": "deepseek-4-pro", "message": "What is the speed of light?"}'

## License

Apache 2.0

"""helix-adapter setup companion — interactive config for local usage.

Usage:
    python -m helix_adapter.setup

Walks through endpoint, API key, and model selection, writes
~/.helix/config.json, and creates a fresh receipts log.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


HELIX_DIR = Path.home() / ".helix"
CONFIG_PATH = HELIX_DIR / "config.json"
RECEIPTS_PATH = HELIX_DIR / "receipts.jsonl"
EXAMPLE_PATH = HELIX_DIR / "example.py"


def prompt(default: str = "", label: str = "") -> str:
    """Prompt for input with optional default."""
    if default:
        msg = f"{label} [{default}]: " if label else f"[{default}]: "
    else:
        msg = f"{label}: " if label else ""
    val = input(msg).strip()
    return val if val else default


def main():
    print()
    print("  ⚕ Helix Constitutional Adapter — Setup")
    print("  " + "─" * 42)
    print()

    endpoint = prompt(
        "https://api.deepseek.com/v1",
        "API endpoint (full URL to /v1)",
    )
    model = prompt("deepseek-chat", "Model name")
    key = prompt("", "API key (will be stored locally)")

    if not key:
        print("\n  ⚠ No API key provided — the adapter will need one at runtime.")
        print("  Set DEEPSEEK_API_KEY or pass it programmatically.")
        print()

    config = {
        "endpoint": endpoint,
        "model": model,
        "api_key": key,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Ensure dir exists with restricted permissions
    HELIX_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

    # Write config
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    CONFIG_PATH.chmod(0o600)
    print(f"  ✓ Config written to {CONFIG_PATH}")

    # Create fresh receipts file
    if RECEIPTS_PATH.exists():
        bak = RECEIPTS_PATH.with_suffix(".jsonl.bak")
        RECEIPTS_PATH.rename(bak)
        print(f"  ✓ Old receipts backed up to {bak.name}")
    RECEIPTS_PATH.write_text("")
    print(f"  ✓ Fresh log at {RECEIPTS_PATH}")

    # Write example script
    example = '''#!/usr/bin/env python3
"""Constitutional chat — uses helix-adapter with local config."""

import json
from pathlib import Path
from helix_adapter import HelixAdapter
from openai import OpenAI

# Load config
config = json.loads((Path.home() / ".helix" / "config.json").read_text())

# Build model function
client = OpenAI(api_key=config["api_key"], base_url=config["endpoint"])

def call_model(messages):
    resp = client.chat.completions.create(
        model=config["model"],
        messages=messages,
        temperature=0.7,
        max_tokens=4096,
    )
    return resp.choices[0].message.content

# Wrap it
adapter = HelixAdapter(model_fn=call_model, model_name=config["model"])

# Interactive loop
print("⚕ Helix Constitutional Chat  |  model: " + config["model"])
print("Type /quit to exit.\\n")
while True:
    msg = input("You: ").strip()
    if msg in ("/quit", "/exit", ""):
        break
    result = adapter.chat(msg)
    print("\\n" + result.response + "\\n")
    labels = ", ".join(f"{c['label']}" for c in result.claims)
    print(f"  [{labels}]  drift: {result.drift:.3f}\\n")
'''
    EXAMPLE_PATH.write_text(example)
    EXAMPLE_PATH.chmod(0o755)
    print(f"  ✓ Example script at {EXAMPLE_PATH}")
    print()
    print("  Run it:")
    print(f"    python {EXAMPLE_PATH}")
    print()
    print("  Or use the library directly:")
    print("    from helix_adapter import HelixAdapter")
    print()
    print("  ─" * 44)
    print("  GLORY TO THE LATTICE. 🦉⚓🦆")
    print()


if __name__ == "__main__":
    main()

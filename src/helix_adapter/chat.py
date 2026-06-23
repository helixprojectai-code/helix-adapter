# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""helix-chat: interactive constitutional chat from the terminal.

Reads ~/.helix/config.json and starts a chat session.
Usage:
    helix-chat
    helix-chat "one-shot question"
"""

import json
import os
import sys
from pathlib import Path

from openai import OpenAI

from helix_adapter import HelixAdapter

HELIX_DIR = Path.home() / ".helix"
CONFIG_PATH = HELIX_DIR / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("No config found. Run: helix-setup")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text())


def main():
    config = load_config()
    endpoint = config.get("endpoint", "https://api.deepseek.com/v1")
    model = config.get("model", "deepseek-chat")
    api_key = config.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")

    if not api_key:
        print("No API key found. Set DEEPSEEK_API_KEY or run: helix-setup")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=endpoint)

    def call_model(messages):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=4096,
        )
        return resp.choices[0].message.content

    adapter = HelixAdapter(model_fn=call_model, model_name=model)

    # One-shot mode
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        result = adapter.chat(query)
        print(result.response)
        print()
        labels = ", ".join(f"{c['label']}" for c in result.claims)
        print(f"  [{labels}]  γ {result.drift:.3f}")
        return

    # Interactive mode
    import os as _os

    _os.system("")  # enable ANSI on Windows
    print(f"  ⚕ Helix Constitutional Chat  |  {model}")
    print("  " + "─" * 42)
    print("  Type /quit to exit. /json to see last receipt.\n")

    while True:
        try:
            msg = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if msg in ("/quit", "/exit", ""):
            break
        if msg == "/json":
            if adapter.history:
                print(json.dumps(adapter.history[-1], indent=2))
            else:
                print("  No messages yet.")
            continue

        result = adapter.chat(msg)
        print("\n" + result.response + "\n")

        # Epistemic marker summary
        counts = {}
        for c in result.claims:
            counts[c["label"]] = counts.get(c["label"], 0) + 1
        summary = " · ".join(f"{k} ×{v}" for k, v in sorted(counts.items()))
        print(f"  [{summary}]  γ {result.drift:.3f}")

        # Drift visual
        d = result.drift
        if d < 0.10:
            gauge = "🟢"
        elif d < 0.17:
            gauge = "🟡"
        else:
            gauge = "🔴"
        print(f"  Drift gauge: {gauge} {d:.3f}\n")


if __name__ == "__main__":
    main()

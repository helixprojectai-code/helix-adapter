"""Zero-dependency checks on foundry/foundry.py — always run, no extras needed.

foundry.py is a standalone script (not part of the installed src/helix_adapter
package), so pytest's default collection never touched it. That gap is exactly
how a missing closing `\"\"\"` in cedar_route()'s docstring — which swallowed
~140 lines of real routing logic into an inert string literal and made the
entire file fail to parse — shipped to main undetected on 2026-07-10, despite
the (separately existing) ruff lint check correctly failing on it.

These two checks need nothing beyond the standard library, so they run in
every environment — including a bare `pip install -e ".[dev]"` with no
`widget` extra — and catch this exact bug class at zero dependency cost. See
test_foundry.py for the deeper, fastapi-dependent functional tests.
"""

import ast
import json
from pathlib import Path

FOUNDRY_PY = Path(__file__).parent.parent / "foundry" / "foundry.py"


def test_foundry_py_parses():
    """The one check that would have caught 2026-07-10's syntax error. If this
    fails, nothing downstream matters — the whole module can't even import."""
    source = FOUNDRY_PY.read_text()
    ast.parse(source, filename=str(FOUNDRY_PY))


def test_foundry_deployments_are_valid_json():
    """Every deployments/<name>/models.json must at least parse and have the
    keys foundry.py's _load_deployment() reads unconditionally at import time."""
    deployments_dir = FOUNDRY_PY.parent / "deployments"
    found = list(deployments_dir.glob("*/models.json"))
    assert found, "expected at least one deployments/*/models.json"
    for path in found:
        data = json.loads(path.read_text())
        for key in ("endpoint", "key_env", "pool_map", "action_map", "models"):
            assert key in data, f"{path} missing required key {key!r}"

"""Functional tests for foundry/foundry.py that need the `widget` extra
(fastapi/openai) — see test_foundry_syntax.py for the zero-dependency checks
that run in every environment regardless.

These skip cleanly (not error) when fastapi/openai aren't installed, since
they're an optional extra, not a core dev dependency.
"""

import importlib
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("openai")

FOUNDRY_DIR = Path(__file__).parent.parent / "foundry"
sys.path.insert(0, str(FOUNDRY_DIR))


@pytest.fixture
def foundry_module():
    """Import foundry.py fresh under the default (azure) deployment.

    Import-time side effects are limited to reading deployments/<name>/models.json
    — no live API calls happen until a route handler actually invokes a model,
    so this is safe to import without real credentials.
    """
    os.environ.setdefault("HELIX_DEPLOYMENT", "azure")
    if "foundry" in sys.modules:
        del sys.modules["foundry"]
    return importlib.import_module("foundry")


def test_foundry_imports_cleanly(foundry_module):
    assert foundry_module.app is not None
    assert len(foundry_module.app.routes) > 0


def test_cedar_route_returns_enriched_schema(foundry_module):
    """v1.7.4 added decision/matched_policy/policy_version to the routing
    return value (Shape Bureau Vector 1 / RFC 0004). Lock the shape down."""
    result = foundry_module.cedar_route({})
    for key in (
        "model",
        "pool",
        "decision",
        "matched_policy",
        "policy_hash",
        "policy_version",
        "reason",
    ):
        assert key in result, f"cedar_route() result missing {key!r}"


def test_cedar_route_none_context_fields_are_dropped(foundry_module):
    """Regression test for the None -> literal "None" string bug fixed in
    1.7.3 — cedar_route() must filter None values before evaluation."""
    result = foundry_module.cedar_route({"action_type": None, "task_complexity": 5})
    # Should not raise, and should resolve to a real pool or the static fallback.
    assert result["pool"] in foundry_module.MODEL_POOLS or result["pool"] == "static"


def test_health_route_responds(foundry_module):
    from fastapi.testclient import TestClient

    client = TestClient(foundry_module.app)
    resp = client.get("/health")
    assert resp.status_code == 200

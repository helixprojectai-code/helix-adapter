"""Cedar dual-gate tests — RFC 0003.

Tests the CedarPolicy engine end-to-end: policy loading, schema validation,
response gate (Duck Gate), action gate (Cedar Gate), receipt sealing, and
fail-closed fallback behaviour.
"""

import pytest

from helix_adapter.cedar.policy import ActionReceipt, CedarDecision, CedarPolicy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def policy():
    p = CedarPolicy()
    assert p.is_available, f"Cedar policy not available: {p.validation_error}"
    return p


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def test_policy_loads():
    p = CedarPolicy()
    assert p.is_available
    assert p.validation_error is None
    assert len(p.policy_hash) == 16


def test_policy_hash_is_stable():
    p1 = CedarPolicy()
    p2 = CedarPolicy()
    assert p1.policy_hash == p2.policy_hash


def test_missing_policy_file_fails_closed():
    p = CedarPolicy(policy_file="/nonexistent/path.policy")
    assert not p.is_available
    assert p.validation_error is not None


def test_strict_mode_raises_on_bad_policy(tmp_path):
    bad = tmp_path / "bad.policy"
    bad.write_text("this is not cedar syntax")
    with pytest.raises(Exception):
        CedarPolicy(policy_file=bad, strict=True)


# ---------------------------------------------------------------------------
# Response Gate (Duck Gate) — Helix_Governance::Action::"respond"
# ---------------------------------------------------------------------------

RESPOND_PRINCIPAL = 'Helix::Agent::"agent-001"'
RESPOND_ACTION    = 'Helix_Governance::Action::"respond"'
RESPOND_RESOURCE  = 'Helix::Environment::"workspace"'


def test_respond_permits_healthy_exchange(policy):
    d = policy.evaluate(
        principal=RESPOND_PRINCIPAL,
        action=RESPOND_ACTION,
        resource=RESPOND_RESOURCE,
        context={"drift_score": 0.05, "marker_count": 3, "has_valid_receipt": True},
    )
    assert d.authorized


def test_respond_denies_high_drift(policy):
    d = policy.evaluate(
        principal=RESPOND_PRINCIPAL,
        action=RESPOND_ACTION,
        resource=RESPOND_RESOURCE,
        context={"drift_score": 0.25, "marker_count": 0, "has_valid_receipt": False},
    )
    assert not d.authorized


def test_respond_denies_at_threshold(policy):
    """Drift exactly at 0.17 is denied (boundary is exclusive)."""
    d = policy.evaluate(
        principal=RESPOND_PRINCIPAL,
        action=RESPOND_ACTION,
        resource=RESPOND_RESOURCE,
        context={"drift_score": 0.17, "marker_count": 1, "has_valid_receipt": True},
    )
    assert not d.authorized


def test_respond_permits_just_under_threshold(policy):
    d = policy.evaluate(
        principal=RESPOND_PRINCIPAL,
        action=RESPOND_ACTION,
        resource=RESPOND_RESOURCE,
        context={"drift_score": 0.16, "marker_count": 1, "has_valid_receipt": True},
    )
    assert d.authorized


def test_respond_denies_no_markers(policy):
    d = policy.evaluate(
        principal=RESPOND_PRINCIPAL,
        action=RESPOND_ACTION,
        resource=RESPOND_RESOURCE,
        context={"drift_score": 0.05, "marker_count": 0, "has_valid_receipt": True},
    )
    assert not d.authorized


def test_respond_denies_no_receipt(policy):
    d = policy.evaluate(
        principal=RESPOND_PRINCIPAL,
        action=RESPOND_ACTION,
        resource=RESPOND_RESOURCE,
        context={"drift_score": 0.05, "marker_count": 3, "has_valid_receipt": False},
    )
    assert not d.authorized


# ---------------------------------------------------------------------------
# Action Gate — bash
# ---------------------------------------------------------------------------

AGENT     = 'Helix::Agent::"agent-001"'
BASH      = 'Helix::Action::"bash"'
ENV       = 'Helix::Environment::"workspace"'
SANDBOX   = "/home/agent/sandbox/run.sh"
OUTSIDE   = "/home/agent/work/script.sh"


def test_bash_denied_without_path(policy):
    d = policy.evaluate(principal=AGENT, action=BASH, resource=ENV, context={})
    assert not d.authorized


def test_bash_denied_outside_sandbox(policy):
    d = policy.evaluate(principal=AGENT, action=BASH, resource=ENV,
                        context={"path": OUTSIDE})
    assert not d.authorized


def test_bash_permitted_in_sandbox(policy):
    d = policy.evaluate(principal=AGENT, action=BASH, resource=ENV,
                        context={"path": SANDBOX})
    assert d.authorized


def test_bash_denied_sandbox_prefix_traversal(policy):
    """Path that starts with sandbox prefix but traverses out must be denied."""
    d = policy.evaluate(principal=AGENT, action=BASH, resource=ENV,
                        context={"path": "/home/agent/sandbox/../../../etc/passwd"})
    assert not d.authorized


# ---------------------------------------------------------------------------
# Action Gate — wallet_transfer (hard forbid)
# ---------------------------------------------------------------------------

def test_wallet_transfer_always_denied(policy):
    d = policy.evaluate(
        principal=AGENT,
        action='Helix::Action::"wallet_transfer"',
        resource='Helix::Resource::"wallet"',
        context={},
    )
    assert not d.authorized


# ---------------------------------------------------------------------------
# Action Gate — file operations
# ---------------------------------------------------------------------------

FILE_RESOURCE = 'Helix::Resource::"file"'


@pytest.mark.parametrize("action", [
    'Helix::Action::"write_file"',
    'Helix::Action::"edit_file"',
    'Helix::Action::"apply_patch"',
])
def test_file_op_permitted_safe_path(policy, action):
    d = policy.evaluate(principal=AGENT, action=action, resource=FILE_RESOURCE,
                        context={"path": "/home/agent/work/output.txt"})
    assert d.authorized


@pytest.mark.parametrize("action", [
    'Helix::Action::"write_file"',
    'Helix::Action::"edit_file"',
    'Helix::Action::"apply_patch"',
])
def test_file_op_denied_dotenv(policy, action):
    d = policy.evaluate(principal=AGENT, action=action, resource=FILE_RESOURCE,
                        context={"path": "/home/agent/.env"})
    assert not d.authorized


@pytest.mark.parametrize("action", [
    'Helix::Action::"write_file"',
    'Helix::Action::"edit_file"',
    'Helix::Action::"apply_patch"',
])
def test_file_op_denied_etc(policy, action):
    d = policy.evaluate(principal=AGENT, action=action, resource=FILE_RESOURCE,
                        context={"path": "/etc/passwd"})
    assert not d.authorized


# ---------------------------------------------------------------------------
# Action Gate — api_call
# ---------------------------------------------------------------------------

API_RESOURCE = 'Helix::Resource::"api"'
API_ACTION   = 'Helix::Action::"api_call"'


@pytest.mark.parametrize("endpoint", [
    "https://api.github.com/repos/foo/bar",
    "https://pypi.org/pypi/helix-adapter/json",
    "https://helix.openai.azure.com/openai/deployments/gpt-4o/chat",
])
def test_api_call_permitted_allowlisted(policy, endpoint):
    d = policy.evaluate(principal=AGENT, action=API_ACTION, resource=API_RESOURCE,
                        context={"endpoint": endpoint})
    assert d.authorized


@pytest.mark.parametrize("endpoint", [
    "https://evil.com/exfil",
    "http://api.github.com/repos/foo/bar",   # http, not https
    "https://attacker.com/?url=https://api.github.com/",  # host mismatch
])
def test_api_call_denied_unlisted(policy, endpoint):
    d = policy.evaluate(principal=AGENT, action=API_ACTION, resource=API_RESOURCE,
                        context={"endpoint": endpoint})
    assert not d.authorized


# ---------------------------------------------------------------------------
# Decision & receipt objects
# ---------------------------------------------------------------------------

def test_decision_has_reason(policy):
    d = policy.evaluate(principal=AGENT, action=BASH, resource=ENV, context={})
    assert isinstance(d, CedarDecision)
    assert isinstance(d.reason, str)
    assert len(d.reason) > 0


def test_seal_action_produces_receipt(policy):
    d = policy.evaluate(principal=AGENT, action=BASH, resource=ENV,
                        context={"path": SANDBOX})
    receipt = policy.seal_action(
        exchange_id="test-exchange-001",
        action=BASH,
        decision=d,
        context={"path": SANDBOX},
    )
    assert isinstance(receipt, ActionReceipt)
    assert receipt.authorized
    assert receipt.receipt_hash.startswith("sha256:")
    assert receipt.exchange_id == "test-exchange-001"
    assert receipt.policy_hash == d.policy_hash


def test_seal_action_denied_receipt(policy):
    d = policy.evaluate(principal=AGENT, action=BASH, resource=ENV, context={})
    receipt = policy.seal_action(
        exchange_id="test-exchange-002",
        action=BASH,
        decision=d,
    )
    assert isinstance(receipt, ActionReceipt)
    assert not receipt.authorized
    assert receipt.receipt_hash.startswith("sha256:")


# ---------------------------------------------------------------------------
# Fail-closed fallback
# ---------------------------------------------------------------------------

def test_fallback_denies_all():
    """A policy instance with no valid policy file must deny everything."""
    p = CedarPolicy(policy_file="/nonexistent/path.policy")
    assert not p.is_available
    d = p.evaluate(principal=AGENT, action=BASH, resource=ENV, context={})
    assert not d.authorized
    assert "deny" in d.reason.lower() or d.reason  # any non-empty reason

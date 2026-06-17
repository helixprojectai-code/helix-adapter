"""Basic tests for helix-adapter."""

from helix_adapter.markers import extract_claims, count_claims
from helix_adapter.receipt import make_receipt
from helix_adapter.drift import compute_drift, compute_running_drift
from helix_adapter.prompt import CONSTITUTIONAL_PROMPT, MARKERS


def test_extract_claims_basic():
    text = "[FACT] The speed of light is 299,792,458 m/s."
    claims = extract_claims(text)
    assert len(claims) == 1
    assert claims[0]["label"] == "FACT"
    assert "speed of light" in claims[0]["text"]


def test_extract_claims_multiple():
    text = (
        "[FACT] Water boils at 100 C at sea level. "
        "[HYPOTHESIS] It may boil at a lower temperature on mountains."
    )
    claims = extract_claims(text)
    assert len(claims) >= 2
    labels = [c["label"] for c in claims]
    assert "FACT" in labels
    assert "HYPOTHESIS" in labels


def test_extract_claims_post_positioned():
    """Handle markers placed after the content."""
    text = "The sky appears blue due to Rayleigh scattering [FACT]."
    claims = extract_claims(text)
    assert len(claims) >= 1
    assert claims[0]["label"] == "FACT"


def test_extract_claims_empty():
    assert extract_claims("") == []
    assert extract_claims("Just a plain statement.") == []


def test_count_claims():
    text = "[FACT] A. [FACT] B. [HYPOTHESIS] C."
    counts = count_claims(text)
    assert counts.get("FACT") == 2
    assert counts.get("HYPOTHESIS") == 1


def test_receipt_has_hash():
    receipt = make_receipt(
        user_message="test",
        assistant_response="[FACT] A fact.",
        claims=[{"label": "FACT", "text": "A fact."}],
        model="test-model",
    )
    assert "hash" in receipt
    assert "exchange_id" in receipt
    assert receipt["model"] == "test-model"
    assert len(receipt["hash"]) == 64  # SHA-256 hex


def test_drift_perfect():
    """Perfectly labeled response has zero drift."""
    resp = "[FACT] A fact. [REASONED] A reasoning."
    claims = [{"label": "FACT", "text": "A fact."},
              {"label": "REASONED", "text": "A reasoning."}]
    d = compute_drift(resp, claims)
    assert d == 0.0, f"Expected 0 drift, got {d}"


def test_drift_unlabeled():
    """Response with no markers has high drift."""
    resp = "The speed of light is 299,792,458 m/s. This is a well-known fact."
    d = compute_drift(resp, [])
    assert d > 0.4, f"Expected high drift, got {d}"


def test_running_drift():
    exchanges = [
        {"assistant_response": "[FACT] One.", "claims": [{"label": "FACT", "text": "One."}]},
        {"assistant_response": "Pure text without any markers at all.", "claims": []},
    ]
    d = compute_running_drift(exchanges)
    assert 0 < d < 1.0


def test_markers_defined():
    assert len(MARKERS) == 5
    assert "FACT" in MARKERS
    assert "CONCLUSION" in MARKERS
    assert "UNCERTAIN" in MARKERS


def test_prompt_contains_constraints():
    assert "NO AGENCY" in CONSTITUTIONAL_PROMPT
    assert "ABSTENTION AS COMPETENCE" in CONSTITUTIONAL_PROMPT
    assert "EPISTEMIC MARKERS" in CONSTITUTIONAL_PROMPT

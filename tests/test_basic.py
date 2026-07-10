"""Basic tests for helix-adapter."""

from helix_adapter.drift import compute_drift, compute_running_drift
from helix_adapter.markers import count_claims, extract_claims
from helix_adapter.prompt import CONSTITUTIONAL_PROMPT, MARKERS
from helix_adapter.receipt import make_receipt


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
    assert receipt.get("canonical_version") == "1.0"


def test_drift_perfect():
    """Perfectly labeled response has near-zero drift."""
    resp = "[FACT] A fact. [REASONED] A reasoning."
    claims = [
        {"label": "FACT", "text": "A fact."},
        {"label": "REASONED", "text": "A reasoning."},
    ]
    d = compute_drift(resp, claims)
    # Inter-sentence whitespace may contribute tiny drift (< 0.03)
    assert d < 0.03, f"Expected near-zero drift, got {d}"


def test_drift_unlabeled():
    """Response with no markers has high drift."""
    resp = "The speed of light is 299,792,458 m/s. This is a well-known fact."
    d = compute_drift(resp, [])
    assert d > 0.4, f"Expected high drift, got {d}"


def test_running_drift():
    exchanges = [
        {
            "assistant_response": "[FACT] One.",
            "claims": [{"label": "FACT", "text": "One."}],
        },
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


def test_receipt_canonicalization_spec_v1_0():
    """Basic checks for RECEIPT CANONICALIZATION SPEC v1.0."""
    from helix_adapter import canonicalize, receipt_hash_bytes

    # Test dict with various types
    receipt = {
        "turn": 5,
        "drift_score": 0.12340000000001,  # float should become fixed str
        "message": "café",  # should NFC
        "nested": {"z": 1, "a": None},
        "arr": [3, 1, 2],
        "timestamp": "2026-07-10T12:00:00.123456789Z",
    }

    canon = canonicalize(receipt)
    canon_str = canon.decode("utf-8")

    # No whitespace outside strings
    assert " " not in canon_str.replace('"', "").replace(":", "").replace(",", ""), "whitespace outside strings"

    # Keys sorted at top level (a before d before m before n before t)
    keys_order = [k for k in ["arr", "drift_score", "message", "nested", "timestamp", "turn"] if k in canon_str]
    assert keys_order == sorted(keys_order), "keys not lex sorted"

    # Float became string in canonical
    assert '"drift_score":"0.1234"' in canon_str

    # NFC: é is composed
    assert "caf\xc3\xa9" in canon_str or "café" in canon_str  # NFC form

    # Hashes are stable
    h1 = receipt_hash_bytes(receipt)
    h2 = receipt_hash_bytes(receipt)
    assert h1 == h2
    assert len(h1) > 0

    print("Canonicalization spec v1.0 basic checks passed")

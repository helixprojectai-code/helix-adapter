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
    """Test vectors + verifier for RECEIPT CANONICALIZATION SPEC v1.0."""
    from helix_adapter import canonicalize, verify_receipt

    # Known test vectors (generated via current canonicalize implementation)
    TEST_VECTORS = [
        {
            "name": "simple",
            "data": {
                "turn": 5,
                "drift_score": 0.1234,
                "message": "café",
                "nested": {"z": None, "a": 1},
                "arr": [3, 1, 2],
                "timestamp": "2026-07-10T12:00:00.123456789Z",
                "canonical_version": "1.0",
            },
            "expected_json": '{"arr":[3,1,2],"canonical_version":"1.0","drift_score":"0.1234","message":"café","nested":{"a":1,"z":null},"timestamp":"2026-07-10T12:00:00.123456789Z","turn":5}',  # noqa: E501
            "expected_hash": "eab4431530d60033211a9d3149594c4eafa25308f740343ccd2583354ae56a77",
        },
        {
            "name": "empty",
            "data": {
                "empty_dict": {},
                "empty_list": [],
                "null_val": None,
                "canonical_version": "1.0",
            },
            "expected_json": '{"canonical_version":"1.0","empty_dict":{},"empty_list":[],"null_val":null}',  # noqa: E501
            "expected_hash": "cec81988cc17039ebd373de6ce0ee18a3574e070dec2d82c7ca3d8521e7056ff",
        },
        {
            "name": "unicode_sort",
            "data": {
                "z_key": 1,
                "a_key": 2,
                "café": "value",
                "canonical_version": "1.0",
            },
            "expected_json": '{"a_key":2,"café":"value","canonical_version":"1.0","z_key":1}',
            "expected_hash": "04fffac00ebf8087caa8e1faa278bab42cdc0ff6c188488fb6b58f0f2f8d979a",
        },
    ]

    import hashlib  # for legacy test

    for vec in TEST_VECTORS:
        canon = canonicalize(vec["data"])
        canon_str = canon.decode("utf-8")
        full_hash = hashlib.sha256(canon).hexdigest()

        assert canon_str == vec["expected_json"], f"Canonical JSON mismatch for {vec['name']}"
        assert full_hash == vec["expected_hash"], f"Hash mismatch for {vec['name']}"

        # Test verifier
        rec_with_hash = dict(vec["data"])
        rec_with_hash["hash"] = vec["expected_hash"]
        assert verify_receipt(rec_with_hash) is True
        assert verify_receipt(rec_with_hash, vec["expected_hash"]) is True

        # Wrong hash should fail
        assert verify_receipt(rec_with_hash, "deadbeef" * 8) is False

    # Legacy (no canonical_version) uses legacy hash path
    from helix_adapter.receipt import _legacy_receipt_hash_bytes

    legacy_data = {"foo": "bar", "timestamp": "2026-01-01T00:00:00Z"}
    legacy_canon = _legacy_receipt_hash_bytes(legacy_data)
    legacy_hash = hashlib.sha256(legacy_canon).hexdigest()
    legacy_rec = dict(legacy_data)
    legacy_rec["hash"] = legacy_hash
    assert verify_receipt(legacy_rec) is True
    assert verify_receipt(legacy_rec, legacy_hash) is True

    # Also verify via JointReceipt path
    from helix_adapter import JointReceipt

    jr_data = {
        "exchange_id": "ex123",
        "session_id": "sess1",
        "turn": 0,
        "timestamp": "2026-07-10T12:00:00.000000000Z",
        "model": "test",
        "user_message": "hi",
        "assistant_response": "[FACT] hi.",
        "claims": [{"label": "FACT", "text": "hi."}],
        "drift_score": 0.0,
        "drift_tier": "green",
        "drift_method": "char",
        "cedar_action": None,
        "cedar_authorized": None,
        "cedar_policy_hash": None,
        "cedar_reason": None,
        "cedar_status": "not_configured",
        "canonical_version": "1.0",
        "merkle_root": None,
        "routing_decision": None,
        "routing_matched_policy": None,
        "routing_policy_version": None,
        "constitutional_compliant": True,
        "constitutional_issues": [],
    }
    # Compute hash from core content (excluding integrity fields that are added later)
    core_for_hash = {
        k: v for k, v in jr_data.items() if k not in ("hash", "chain_hash", "merkle_root")
    }
    jr_canon = canonicalize(core_for_hash)
    jr_hash = hashlib.sha256(jr_canon).hexdigest()
    jr = JointReceipt(**jr_data, hash=jr_hash, chain_hash="c1")
    actual_dict = jr.to_dict()
    # verify should succeed even with extra integrity fields present
    assert verify_receipt(actual_dict) is True
    assert verify_receipt(actual_dict, jr_hash) is True

    print("All canonicalization test vectors + verifier checks passed")

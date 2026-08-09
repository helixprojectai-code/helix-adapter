"""v1.0.5: checkpoint chain (tamper-evident audit trail) tests.

Runs the real bridge subprocess (like test_checkpoint_integrity.py) and
audits the resulting checkpoint with verify_checkpoint(): chain fields
present, self-hash recomputes, tampering with any field is detected, and
a truncated journal is detected.
"""
import os
import json
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from helix_imu_plop_bridge import verify_checkpoint, CHAIN_GENESIS  # noqa: E402

# v1.0.7: chain HMAC key is required now (see _get_chain_key). Test-only
# key, propagates to the bridge subprocess since Popen inherits os.environ
# unless overridden -- and to verify_checkpoint() calls in this same
# process, so writer and verifier agree.
os.environ.setdefault("PLOP_CHAIN_KEY", "deadbeef" * 8)

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
BRIDGE = os.path.join(SRC_DIR, "helix_imu_plop_bridge.py")


def _run_bridge(out):
    for p in (out, out + ".chain"):
        if os.path.exists(p):
            os.remove(p)
    proc = subprocess.Popen(
        ["python3", BRIDGE, "--duration", "0.02", "--traj", "stationary",
         "--rate", "300", "--window", "500", "--output", out],
        cwd=SRC_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.wait(timeout=60)
    return proc.returncode


def test_checkpoint_carries_chain_and_verifies():
    out = "/tmp/plop_chain_test.json"
    assert _run_bridge(out) == 0
    with open(out) as f:
        data = json.load(f)
    assert data["complete"] is True
    chain = data["chain"]
    assert chain["index"] >= 1
    assert len(chain["self_hash"]) == 64
    assert chain["prev_hash"] == CHAIN_GENESIS or len(chain["prev_hash"]) == 64
    ok, reason = verify_checkpoint(out)
    assert ok, reason
    # journal exists and ends with this checkpoint's self-hash
    with open(out + ".chain") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    assert lines, "journal should have at least one line"
    assert lines[-1].split("|")[3] == chain["self_hash"]


def test_checkpoint_chain_detects_tamper():
    out = "/tmp/plop_chain_tamper.json"
    assert _run_bridge(out) == 0
    with open(out) as f:
        data = json.load(f)
    data["metrics"]["final_pos_m"] = data["metrics"]["final_pos_m"] + 123.0
    with open(out, "w") as f:
        json.dump(data, f, indent=2)
    ok, reason = verify_checkpoint(out)
    assert not ok
    assert reason == "CONTENT_HASH_MISMATCH"


def test_checkpoint_chain_detects_truncated_journal():
    out = "/tmp/plop_chain_journal.json"
    assert _run_bridge(out) == 0
    jp = out + ".chain"
    with open(jp) as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    assert len(lines) >= 2  # need at least two lines to truncate meaningfully
    with open(jp, "w") as f:
        f.write("\n".join(lines[:-1]) + "\n")
    ok, reason = verify_checkpoint(out)
    assert not ok
    assert reason == "JOURNAL_MISMATCH"

#!/usr/bin/env python3
"""
Tier 1.8 + Tier 2.4 — Checkpoint Integrity & Crash Survival
=============================================================
The v1.0.1 changelog claimed "a crash mid-write never leaves a
truncated/corrupt JSON" via atomic tmp-file + os.replace. That claim has
never actually been tested against a real process kill until this file --
everything before this was a claim about the mechanism, not a test of it.

Run directly:
  python3 test_checkpoint_integrity.py
"""

import sys
import os
import json
import subprocess
import time
import signal

# v1.0.7: chain HMAC key is required now (see _get_chain_key in the
# bridge). Test-only key -- propagates to the subprocess since Popen
# inherits os.environ unless overridden.
os.environ.setdefault("PLOP_CHAIN_KEY", "deadbeef" * 8)

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
BRIDGE = os.path.join(SRC_DIR, "helix_imu_plop_bridge.py")


def test_checkpoint_valid_at_multiple_points():
    """1.8: checkpoint JSON is valid whenever we look at it, not just
    after the final write -- polls the file repeatedly while the bridge
    is still running."""
    print("\n[1/2] Checkpoint valid mid-run (Tier 1.8)...")
    out = "/tmp/plop_checkpoint_test.json"
    if os.path.exists(out):
        os.remove(out)

    proc = subprocess.Popen(
        ["python3", BRIDGE, "--duration", "0.02", "--traj", "stationary",
         "--rate", "300", "--window", "500", "--output", out],
        cwd=SRC_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    seen_valid = 0
    checks = 0
    t0 = time.time()
    while proc.poll() is None and time.time() - t0 < 30:
        if os.path.exists(out):
            try:
                with open(out) as f:
                    data = json.load(f)
                assert "complete" in data and "last_sample" in data, "missing checkpoint fields"
                seen_valid += 1
            except json.JSONDecodeError:
                raise AssertionError("Checkpoint JSON was invalid/corrupt mid-run -- atomic replace failed")
        checks += 1
        time.sleep(0.05)

    proc.wait(timeout=30)
    assert seen_valid > 0, "Never observed a valid checkpoint during the run"

    with open(out) as f:
        final = json.load(f)
    assert final["complete"] is True, "Final checkpoint should be marked complete"

    print(f"  ✅ PASS: {seen_valid}/{checks} polls saw valid JSON, final complete=True")


def test_sigkill_survives_with_valid_partial_checkpoint():
    """2.4: SIGKILL mid-run must leave a valid, non-corrupt, non-complete
    checkpoint -- this is the actual claim being tested, not the
    mechanism's description."""
    print("\n[2/2] SIGKILL mid-run leaves valid partial checkpoint (Tier 2.4)...")
    out = "/tmp/plop_sigkill_test.json"
    if os.path.exists(out):
        os.remove(out)

    proc = subprocess.Popen(
        ["python3", BRIDGE, "--duration", "1.0", "--traj", "stationary",
         "--rate", "300", "--window", "2000", "--output", out],
        cwd=SRC_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # Wait for at least one checkpoint to land before we kill it.
    t0 = time.time()
    while not os.path.exists(out) and time.time() - t0 < 30:
        time.sleep(0.1)
    assert os.path.exists(out), "No checkpoint appeared before timeout -- can't test kill survival"

    # Let a couple more checkpoints happen, then kill without any cleanup chance.
    time.sleep(1.5)
    assert proc.poll() is None, "Process exited on its own before we could SIGKILL it"
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=10)

    assert os.path.exists(out), "Checkpoint file gone after SIGKILL"
    with open(out) as f:
        data = json.load(f)  # must not raise -- this IS the test

    assert data["complete"] is False, "A killed run should not read as complete"
    assert data["last_sample"] > 0, "Should have at least one window's worth of progress recorded"

    print(f"  ✅ PASS: killed at last_sample={data['last_sample']}, "
          f"checkpoint intact and parseable, complete=False (correctly not claiming success)")


def main():
    print("\n" + "=" * 70)
    print("TIER 1.8 + TIER 2.4: CHECKPOINT INTEGRITY & CRASH SURVIVAL")
    print("=" * 70)
    print("\nTests the actual claim, not just the mechanism's description.")

    try:
        test_checkpoint_valid_at_multiple_points()
        test_sigkill_survives_with_valid_partial_checkpoint()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 70)
    print("✅ ALL CHECKPOINT INTEGRITY TESTS PASSED")
    print("=" * 70)
    print("\n🦉⚓🦆📡🔒\n")
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

#!/usr/bin/env python3
"""
CLI argument validation (v1.0.7, red team findings #4-6)
============================================================
Three configs the bridge used to accept and then either crash or
silently misbehave on:
  --duration <= 0   -> unhandled StopIteration crash
  --window < 3      -> compute_winding_number() returns 0.0 unconditionally,
                        permanently and silently disabling the detection gate
  --W-thresh <= 0   -> surgery fires on every window, including flat flight

All three are now rejected at startup (argparse error, exit 2) with a
message explaining why, instead of reaching the run loop at all.

Run directly:
  python3 test_cli_validation.py
"""

import sys
import os
import subprocess

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
BRIDGE = os.path.join(SRC_DIR, "helix_imu_plop_bridge.py")
ENV = dict(os.environ, PLOP_CHAIN_KEY="deadbeef" * 8)


def _run(*extra_args):
    return subprocess.run(
        ["python3", BRIDGE, "--duration", "0.01", "--rate", "100",
         "--output", "/tmp/plop_cli_validation_test.json", *extra_args],
        capture_output=True, text=True, timeout=15, env=ENV,
    )


def test_rejects_bad_config():
    print("\nRejecting invalid CLI configs...")
    cases = [
        (["--duration", "0"], "--duration"),
        (["--duration", "-1"], "--duration"),
        (["--window", "2"], "--window"),
        (["--window", "0"], "--window"),
        (["--W-thresh", "0"], "--W-thresh"),
        (["--W-thresh", "-0.1"], "--W-thresh"),
        # v1.0.8 counter red-team: NaN/Inf bypassed every `x <= 0` check,
        # --rate was unvalidated, and window >= N silently disabled the
        # gate and intermediate checkpoints (N=3600 for the config below).
        (["--W-thresh", "nan"], "--W-thresh"),
        (["--W-thresh", "inf"], "--W-thresh"),
        (["--duration", "nan"], "--duration"),
        (["--rate", "0"], "--rate"),
        (["--rate", "-100"], "--rate"),
        (["--window", "5000"], "--window"),
    ]
    for extra, expect_in_msg in cases:
        # --duration cases override the default --duration 0.01 above by
        # appearing later in argv; argparse takes the last occurrence.
        proc = _run(*extra)
        assert proc.returncode == 2, (
            f"{extra}: expected exit 2 (argparse error), got {proc.returncode}\n"
            f"stderr: {proc.stderr[-300:]}")
        assert expect_in_msg in proc.stderr, (
            f"{extra}: expected {expect_in_msg!r} explained in stderr, got: "
            f"{proc.stderr[-300:]}")
        print(f"  ✅ {extra} -> exit 2, rejected with a clear reason")


def test_valid_config_still_runs():
    print("\nValid config still runs clean...")
    proc = _run("--window", "50")
    assert proc.returncode == 0, f"expected exit 0, got {proc.returncode}\n{proc.stderr[-300:]}"
    print("  ✅ PASS (valid config unaffected by the new guards)")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("CLI VALIDATION TEST SUITE (v1.0.7)")
    print("=" * 70)
    test_rejects_bad_config()
    test_valid_config_still_runs()
    print("\n" + "=" * 70)
    print("✅ ALL CLI VALIDATION TESTS PASSED")
    print("=" * 70)
    print("\n🦉⚓🦆📡🔒\n")

#!/usr/bin/env python3
"""
Tier 6 -- Sensor Fault Detection (v1.0.7)
===========================================
Red-team finding: a single non-finite (NaN/Inf) sensor sample permanently
poisoned the running attitude quaternion, and compute_winding_number()
silently reported W=0.0 for a fully-poisoned window -- indistinguishable
from genuinely flat flight -- instead of surfacing the corruption. See
docs/CHANGELOG.md v1.0.7 and helix_imu_plop_bridge.py's fail_fault().

Two layers tested:
1. Unit level: compute_winding_number()/topological_surgery() handle
   non-finite input explicitly instead of masking it as zero.
2. End-to-end: a real bridge run with one injected NaN gyro sample exits
   non-zero, logs a fault, and the checkpoint shows the last *clean*
   state (not NaN garbage) -- confirming the ingestion-point check catches
   it before poisoning propagates into q.

Run directly:
  python3 test_sensor_fault_detection.py
"""

import sys
import os
import json
import subprocess
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from helix_imu_plop_bridge import (  # noqa: E402
    compute_winding_number, topological_surgery,
)
import numpy as np  # noqa: E402

# v1.0.7: chain HMAC key is required now (see _get_chain_key in the
# bridge) -- the end-to-end harness spawns the real bridge, which writes
# a checkpoint on fault. Test-only key, propagates to that subprocess
# since it inherits this process's os.environ unless overridden.
os.environ.setdefault("PLOP_CHAIN_KEY", "deadbeef" * 8)


def test_winding_number_nan_window():
    print("\n[1/3] compute_winding_number() on a non-finite window...")
    nan_window = np.full((50, 3), np.nan)
    w = compute_winding_number(nan_window)
    assert np.isnan(w), f"expected NaN, got {w} -- silently masks corruption as clean zero"
    print(f"  ✅ PASS (returns NaN, not 0.0)")

    inf_window = np.tile(np.array([0., 0., np.inf]), (50, 1))
    w2 = compute_winding_number(inf_window)
    assert np.isnan(w2) or np.isinf(w2), f"expected non-finite, got {w2}"
    print(f"  ✅ PASS (Inf input also flagged, not silently normalized away)")

    clean_window = np.tile(np.array([0., 0., 9.80665]), (50, 1))
    w3 = compute_winding_number(clean_window)
    assert np.isfinite(w3) and abs(w3) < 1e-6, f"clean stationary window should be ~0, got {w3}"
    print(f"  ✅ PASS (clean window unaffected: W={w3:.2e})")


def test_surgery_refuses_nan():
    print("\n[2/3] topological_surgery() does not apply a correction from NaN W...")
    q = np.array([1., 0., 0., 0.])
    nan_window = np.full((50, 3), np.nan)
    q_out, W, did_surgery, axis = topological_surgery(q, nan_window, W_threshold=0.5)
    assert np.isnan(W), f"W should surface as NaN, got {W}"
    assert did_surgery is False, "must not claim a correction was applied from garbage input"
    assert np.array_equal(q_out, q), "q must be unchanged when input is corrupted"
    print(f"  ✅ PASS (did_surgery=False, q unchanged, W=NaN surfaced for caller to act on)")


def test_end_to_end_fault_path():
    print("\n[3/3] End-to-end: real run with one injected NaN gyro sample...")
    bridge_dir = os.path.join(os.path.dirname(__file__), "..")
    out_dir = "/tmp/plop_fault_test"
    os.makedirs(out_dir, exist_ok=True)
    output_path = os.path.join(out_dir, "fault_run.json")
    for p in (output_path, output_path + ".chain", output_path + ".tmp"):
        if os.path.exists(p):
            os.remove(p)

    # Monkey-patch generate_om_ac_stream to inject one NaN gyro sample
    # partway through the first chunk, then run main() with real argv,
    # in a subprocess so it's a genuine end-to-end run (real argparse,
    # real main loop, real exit code) rather than calling internals.
    harness = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {os.path.join(bridge_dir, "src")!r})
        sys.argv = ["helix_imu_plop_bridge.py", "--duration", "0.01", "--traj", "stationary",
                    "--rate", "100", "--window", "50", "--output", {output_path!r}]
        import helix_imu_plop_bridge as bridge
        import numpy as np

        _orig = bridge.generate_om_ac_stream
        def _poisoned(N, dt, traj, seed=42, chunk_size=50000):
            for om_chunk, ac_chunk in _orig(N, dt, traj, seed, chunk_size):
                om_chunk = om_chunk.copy()
                if len(om_chunk) > 30:
                    om_chunk[30, 0] = np.nan  # poison sample 30 in the first chunk
                yield om_chunk, ac_chunk
        bridge.generate_om_ac_stream = _poisoned
        bridge.main()
    """)
    harness_path = os.path.join(out_dir, "harness.py")
    with open(harness_path, "w") as f:
        f.write(harness)

    proc = subprocess.run(["python3", harness_path], capture_output=True, text=True, timeout=30)

    assert proc.returncode == 1, (
        f"expected exit 1 on fault, got {proc.returncode}\nstdout: {proc.stdout[-500:]}\n"
        f"stderr: {proc.stderr[-500:]}")
    assert "NON_FINITE_SENSOR_SAMPLE" in proc.stderr, (
        f"expected fault reason in stderr, got: {proc.stderr[-500:]}")
    print(f"  ✅ PASS (exit code 1, fault reason printed to stderr)")

    assert os.path.exists(output_path), "fault checkpoint was not written"
    with open(output_path) as f:
        data = json.load(f)
    assert data["complete"] is False, "fault checkpoint must not claim completion"
    assert len(data["faults"]) == 1, f"expected exactly 1 fault logged, got {data['faults']}"
    fault = data["faults"][0]
    assert fault["reason"] == "NON_FINITE_SENSOR_SAMPLE"
    assert fault["sample"] == 30, f"expected fault at sample 30, got {fault['sample']}"
    print(f"  ✅ PASS (checkpoint written: complete=False, faults=[{fault['reason']} @ sample {fault['sample']}])")

    # The whole point: the checkpoint must NOT silently show flat W=0
    # metrics as if nothing happened. Since the fault fires at ingestion
    # (sample 30), before q is ever touched by the bad sample, yaw/pos
    # should reflect real (clean, pre-fault) integrated state, not NaN.
    assert np.isfinite(data["metrics"]["final_yaw_deg"]), (
        "checkpoint metrics went NaN -- ingestion-point check should prevent this")
    print(f"  ✅ PASS (checkpoint metrics are clean, not NaN-poisoned -- "
          f"caught before propagation, final_yaw_deg={data['metrics']['final_yaw_deg']:.6f})")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("SENSOR FAULT DETECTION TEST SUITE (v1.0.7)")
    print("=" * 70)
    test_winding_number_nan_window()
    test_surgery_refuses_nan()
    test_end_to_end_fault_path()
    print("\n" + "=" * 70)
    print("✅ ALL SENSOR FAULT DETECTION TESTS PASSED")
    print("=" * 70)
    print("\n🦉⚓🦆📡🔒\n")

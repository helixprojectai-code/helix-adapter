#!/usr/bin/env python3
"""
Steady-Rotation Gate Tests (is_steady_rotation)
================================================
Added in v1.0.3, prompted by the barrel_roll finding: once the winding
formula was fixed (v1.0.2), a sustained rotation was found to correctly
cross the winding threshold repeatedly -- but firing surgery on every
crossing during a commanded maneuver would fight it, not fix a fault.
is_steady_rotation() gates surgery application on the angular-rate
signature, since the winding integral alone can't tell "anomaly" apart
from "intentional sustained rotation."

This file validates the gate itself, independent of the winding math:
does it correctly classify steady vs. erratic vs. negligible rotation?

Run directly:
  python3 test_steady_rotation_gate.py
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from helix_imu_plop_bridge import is_steady_rotation  # noqa: E402


def test_sustained_roll_is_steady():
    print("\n[1/5] Sustained roll (constant magnitude + axis, small noise)...")
    rng = np.random.default_rng(1)
    omega = np.tile([1.0, 0.0, 0.0], (5000, 1)) + rng.normal(0, 0.005, (5000, 3))
    result = is_steady_rotation(omega)
    print(f"  is_steady_rotation = {result} (expect True)")
    assert bool(result) is True
    print("  ✅ PASS")


def test_erratic_rotation_is_not_steady():
    print("\n[2/5] Erratic rotation (random magnitude + axis each sample)...")
    rng = np.random.default_rng(2)
    omega = rng.normal(0, 1.0, (5000, 3))
    result = is_steady_rotation(omega)
    print(f"  is_steady_rotation = {result} (expect False)")
    assert bool(result) is False
    print("  ✅ PASS")


def test_negligible_rotation_is_not_steady():
    """Near-zero rotation shouldn't be classified 'steady' -- if winding
    crossed threshold here, there's no rotation explaining it, so don't
    suppress. This is a deliberate fail-open-to-surgery default: with no
    evidence of a commanded maneuver, treat the crossing as unexplained."""
    print("\n[3/5] Negligible rotation (near-zero, nothing to explain a crossing)...")
    rng = np.random.default_rng(3)
    omega = rng.normal(0, 1e-8, (5000, 3))
    result = is_steady_rotation(omega)
    print(f"  is_steady_rotation = {result} (expect False)")
    assert bool(result) is False
    print("  ✅ PASS")


def test_variable_magnitude_same_axis_is_not_steady():
    """Same axis throughout, but magnitude swings wildly -- not a smooth
    commanded rate profile."""
    print("\n[4/5] Variable magnitude, fixed axis (spiky rate, not smooth)...")
    rng = np.random.default_rng(4)
    n = 5000
    mags = 1.0 + rng.choice([0.0, 3.0], size=n)  # bimodal: spikes between ~1 and ~4
    omega = np.zeros((n, 3))
    omega[:, 0] = mags
    result = is_steady_rotation(omega)
    print(f"  is_steady_rotation = {result} (expect False -- high magnitude CV)")
    assert bool(result) is False
    print("  ✅ PASS")


def test_short_window_defaults_false():
    print("\n[5/5] Degenerate window (<3 samples)...")
    result = is_steady_rotation(np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]))
    print(f"  is_steady_rotation = {result} (expect False, can't classify)")
    assert bool(result) is False
    print("  ✅ PASS")


def main():
    print("\n" + "=" * 70)
    print("STEADY-ROTATION GATE TESTS (v1.0.3)")
    print("=" * 70)
    print("\nValidates is_steady_rotation() classifies commanded-maneuver-like")
    print("angular rate apart from erratic/negligible rotation.\n")

    tests = [
        test_sustained_roll_is_steady,
        test_erratic_rotation_is_not_steady,
        test_negligible_rotation_is_not_steady,
        test_variable_magnitude_same_axis_is_not_steady,
        test_short_window_defaults_false,
    ]

    try:
        for t in tests:
            t()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 70)
    print("✅ ALL STEADY-ROTATION GATE TESTS PASSED")
    print("=" * 70)
    print("\n🦉⚓🦆📡🔒\n")
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

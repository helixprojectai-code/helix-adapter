#!/usr/bin/env python3
"""
Tier 0.2 — Analytic Ground Truth for compute_winding_number()
================================================================
Validates the winding integral against known spherical geometry, not just
"stays near zero on things that shouldn't trigger it" (which is easy to
get right by accident -- both the broken v1.0.1 formula and the fixed
v1.0.2 formula pass that bar). This is the test that would have caught
the v1.0.1 bug: it asserts a specific, independently-derivable nonzero
value on a genuinely closed loop.

Ground truth: the solid angle subtended by a spherical cap of half-angle
theta is Omega = 2*pi*(1 - cos(theta)). A trajectory that walks the
boundary of that cap and genuinely closes should produce
W = Omega / (4*pi) = (1 - cos(theta)) / 2.

Run directly:
  python3 test_analytic_winding.py
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from helix_imu_plop_bridge import compute_winding_number  # noqa: E402

G = 9.80665


def cap_boundary(half_angle_deg, n_points=5000, endpoint=True):
    """Trajectory walking the boundary of a spherical cap. With
    endpoint=True the curve genuinely closes (last sample == first)."""
    theta = np.deg2rad(half_angle_deg)
    phi = np.linspace(0, 2 * np.pi, n_points, endpoint=endpoint)
    g = np.zeros((n_points, 3))
    g[:, 0] = np.sin(theta) * np.cos(phi)
    g[:, 1] = np.sin(theta) * np.sin(phi)
    g[:, 2] = np.cos(theta)
    return g * G


def solid_angle_fraction(half_angle_deg):
    """Expected W = solid_angle / 4*pi for a cap of given half-angle."""
    theta = np.deg2rad(half_angle_deg)
    return (1.0 - np.cos(theta)) / 2.0


def test_closed_cap_matches_solid_angle():
    print("\n" + "=" * 70)
    print("TEST: Closed cap boundary matches analytic solid angle")
    print("=" * 70)
    passed = 0
    cases = [10, 30, 60, 90]
    for half_angle in cases:
        g = cap_boundary(half_angle, n_points=5000, endpoint=True)
        W = compute_winding_number(g)
        expected = solid_angle_fraction(half_angle)
        diff = abs(W - expected)
        ok = diff < 1e-3
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  half_angle={half_angle:3d}deg  W={W:.6f}  expected={expected:.6f}  "
              f"diff={diff:.2e}  {status}")
        if ok:
            passed += 1
        else:
            raise AssertionError(
                f"half_angle={half_angle}: W={W:.6f} != expected={expected:.6f} "
                f"(diff={diff:.2e})"
            )
    print(f"\n  {passed}/{len(cases)} cases matched analytic solid angle")


def test_open_arc_is_roughly_half_of_closed():
    """A half-circle boundary (doesn't close) should sweep roughly half
    the solid angle of the full closed loop at the same latitude -- this
    isn't an exact analytic identity (the swept-area formula for an open
    arc fanned from its own first point isn't literally half the cap's
    solid angle in general), but it should land in a sane neighborhood,
    not near-zero and not larger than the closed case."""
    print("\n" + "=" * 70)
    print("TEST: Open arc (half loop) gives a partial, non-trivial sweep")
    print("=" * 70)
    half_angle = 30
    n = 5000
    theta = np.deg2rad(half_angle)
    phi = np.linspace(0, np.pi, n, endpoint=False)  # half circle, doesn't close
    g = np.zeros((n, 3))
    g[:, 0] = np.sin(theta) * np.cos(phi)
    g[:, 1] = np.sin(theta) * np.sin(phi)
    g[:, 2] = np.cos(theta)
    g *= G

    W_open = compute_winding_number(g)
    W_closed = solid_angle_fraction(half_angle)
    print(f"  W_open={W_open:.6f}  W_closed(full loop)={W_closed:.6f}")

    assert W_open > 1e-4, f"Open arc should be clearly nonzero, got {W_open:.6f}"
    assert W_open < W_closed, (
        f"Open (partial) arc should sweep less than the full closed loop: "
        f"{W_open:.6f} >= {W_closed:.6f}"
    )
    print("  ✅ PASS (nonzero, and less than the full closed-loop value)")


def test_noise_stays_near_zero():
    print("\n" + "=" * 70)
    print("TEST: Small oscillation / noise stays near zero (regression)")
    print("=" * 70)
    n = 5000
    t = np.linspace(0, 100 * np.pi, n)
    g = np.zeros((n, 3))
    g[:, 0] = 0.001 * G * np.sin(t)
    g[:, 1] = 0.001 * G * np.cos(t)
    g[:, 2] = G
    W = compute_winding_number(g)
    print(f"  W_noise={W:.9f}")
    assert abs(W) < 1e-3, f"Noise should stay near zero, got {W:.9f}"
    print("  ✅ PASS")


def test_stationary_regression():
    """Sanity check against the real production case: near-constant
    downward gravity with tiny sensor noise, matching the stationary
    trajectory's actual gravity-bias behavior. Confirms the fixed formula
    still gives near-zero on the case that's live on CORE."""
    print("\n" + "=" * 70)
    print("TEST: Near-stationary trajectory stays near zero (production regression)")
    print("=" * 70)
    n = 5000
    rng = np.random.default_rng(42)
    g = np.zeros((n, 3))
    g[:, 2] = G
    g += rng.normal(0, 1e-4 * G, (n, 3))
    W = compute_winding_number(g)
    print(f"  W_stationary={W:.9f}")
    assert abs(W) < 1e-3, f"Stationary case should stay near zero, got {W:.9f}"
    print("  ✅ PASS")


def main():
    print("\n" + "=" * 70)
    print("TIER 0.2: ANALYTIC WINDING GROUND TRUTH")
    print("=" * 70)
    print("\nValidates compute_winding_number() against known spherical")
    print("geometry -- the test that would have caught the v1.0.1 bug.\n")

    tests = [
        test_closed_cap_matches_solid_angle,
        test_open_arc_is_roughly_half_of_closed,
        test_noise_stays_near_zero,
        test_stationary_regression,
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
    print("✅ ALL ANALYTIC WINDING TESTS PASSED")
    print("=" * 70)
    print("\ncompute_winding_number() now matches known spherical geometry.")
    print("🦉⚓🦆📡🔒\n")
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

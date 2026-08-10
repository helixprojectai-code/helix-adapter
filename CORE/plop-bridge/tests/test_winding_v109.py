"""v1.0.9: winding-operator regression tests (FINDING 2026-08-10).

Guards the great-circle degeneracy fix:
- full great-circle loops must report (1-cos theta)/2 = 0.5, not 0
- the real barrel-roll generator must produce visible winding per window
- partial arcs must be monotone and bounded by the cap
- small-circle analytic match must be preserved (<1e-6)

Run directly:
  python3 test_winding_v109.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from helix_imu_plop_bridge import (compute_winding_number,
                                   generate_om_ac_stream, qfromomega,
                                   qnorm, qmul, qdcm)  # noqa: E402


def _cap(n, th_deg, frac=1.0):
    th = np.deg2rad(th_deg)
    phi = np.linspace(0, frac * 2 * np.pi, n, endpoint=False)
    return np.column_stack([np.sin(th) * np.cos(phi),
                            np.sin(th) * np.sin(phi),
                            np.cos(th) * np.ones(n)])


def _barrel_windows(n_win=20, window=500, dt=1.0 / 300.0, seed=42):
    q = np.array([1.0, 0, 0, 0])
    qhist, ws = [], []
    N = int(n_win * window)
    for om_chunk, _ac in generate_om_ac_stream(N, dt, "barrel_roll", seed=seed,
                                               chunk_size=window):
        for row in om_chunk:
            dq = qfromomega(row[None, :], dt)
            q = qnorm(qmul(q.reshape(1, 4), dq))[0]
            qhist.append(q.copy())
            if len(qhist) == window:
                R = qdcm(np.array(qhist))
                ws.append(compute_winding_number(R @ np.array([0.0, 0.0, 9.80665])))
                qhist = []
            if len(ws) == n_win:
                return np.array(ws)
    return np.array(ws)


def test_small_circle_analytic_preserved():
    for th in (15, 30, 45, 60, 75):
        W = compute_winding_number(_cap(2000, th))
        want = (1 - np.cos(np.deg2rad(th))) / 2
        assert abs(W - want) < 1e-6, f"theta={th}: W={W} analytic={want}"


def test_great_circle_loop_reports_half():
    W = compute_winding_number(_cap(2000, 90.0))
    assert abs(W - 0.5) < 1e-6, f"great-circle loop must be 0.5, got {W}"


def test_barrel_roll_winding_visible():
    ws = _barrel_windows()
    assert np.mean(np.abs(ws)) > 0.05, (
        f"barrel-roll windows must show real winding, mean={np.mean(np.abs(ws)):.6f}"
    )
    assert np.max(np.abs(ws)) > 0.1, f"max={np.max(np.abs(ws)):.6f}"


def test_partial_arcs_monotone_bounded():
    vals = [compute_winding_number(_cap(2000, 30, f)) for f in (0.25, 0.5, 0.75)]
    cap_full = compute_winding_number(_cap(2000, 30))
    assert 0 < vals[0] < vals[1] < vals[2] < cap_full, f"arcs={vals} cap={cap_full}"


def test_stationary_stays_quiet():
    rng = np.random.default_rng(3)
    g = np.column_stack([rng.normal(0, 1e-3, 2000), rng.normal(0, 1e-3, 2000),
                         np.ones(2000)])
    assert abs(compute_winding_number(g)) < 1e-3


if __name__ == "__main__":
    print("=" * 70)
    print("WINDING v1.0.9 REGRESSION TESTS")
    print("=" * 70)
    test_small_circle_analytic_preserved()
    print("  ✅ small-circle analytic preserved (<1e-6)")
    test_great_circle_loop_reports_half()
    print("  ✅ great-circle loop = 0.5 (degeneracy fixed)")
    test_barrel_roll_winding_visible()
    print("  ✅ barrel-roll windows show real winding")
    test_partial_arcs_monotone_bounded()
    print("  ✅ partial arcs monotone & bounded")
    test_stationary_stays_quiet()
    print("  ✅ stationary stays quiet")
    print("=" * 70)
    print("✅ ALL WINDING v1.0.9 TESTS PASSED")
    print("=" * 70)
    print("\n🦉⚓🦆📡🔒\n")

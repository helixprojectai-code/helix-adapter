"""v1.0.10: post-review hardening regression tests.

Guards:
- noisy barrel roll keeps real winding (SVD planarity selector; the
  v1.0.9 dot-product gate collapsed 0.139 -> 0.0002 at ~0.5 deg noise)
- clustered noise blobs stay quiet (SVD must not fire on trivial
  'planarity' of a blob -- apex would land on the path)
- steady-rotation gate tolerates near-zero rows (intermittently zeroing
  gyro during a commanded roll must not evade suppression)

Run directly:
  python3 test_v110_hardening.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from helix_imu_plop_bridge import (compute_winding_number,  # noqa: E402
                                   is_steady_rotation,
                                   generate_om_ac_stream, qfromomega,
                                   qnorm, qmul, qdcm)

rng = np.random.default_rng(7)


def _barrel_windows(n_win=20, window=500, dt=1.0 / 300.0, seed=42,
                    perturb_deg=0.0):
    q = np.array([1.0, 0, 0, 0])
    qhist, ws = [], []
    for om_chunk, _ac in generate_om_ac_stream(int(n_win * window), dt,
                                               "barrel_roll", seed=seed,
                                               chunk_size=window):
        for row in om_chunk:
            dq = qfromomega(row[None, :], dt)
            q = qnorm(qmul(q.reshape(1, 4), dq))[0]
            qhist.append(q.copy())
            if len(qhist) == window:
                g = qdcm(np.array(qhist)) @ np.array([0.0, 0.0, 9.80665])
                if perturb_deg:
                    ang = np.deg2rad(perturb_deg)
                    for k in range(len(g)):
                        ax = rng.normal(size=3)
                        ax /= np.linalg.norm(ax)
                        K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]],
                                      [-ax[1], ax[0], 0]])
                        Rk = np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * (K @ K)
                        g[k] = Rk @ g[k]
                ws.append(g)
                qhist = []
            if len(ws) == n_win:
                return ws
    return ws


def test_noisy_barrel_roll_keeps_winding():
    clean = np.mean(np.abs([compute_winding_number(g)
                            for g in _barrel_windows()]))
    for pert in (0.5, 2.0):
        noisy = np.mean(np.abs([compute_winding_number(g)
                                for g in _barrel_windows(perturb_deg=pert)]))
        assert abs(noisy - clean) / clean < 0.05, (
            f"perturb={pert}°: winding {noisy:.4f} vs clean {clean:.4f} "
            f"-- planarity selector collapsed under noise"
        )


def test_noise_blob_stays_quiet():
    g = np.column_stack([rng.normal(0, 1e-3, 2000), rng.normal(0, 1e-3, 2000),
                         np.ones(2000)])
    assert abs(compute_winding_number(g)) < 1e-3, (
        f"clustered noise blob must stay quiet, got {compute_winding_number(g):.4f}"
    )


def test_steady_gate_tolerates_near_zero_rows():
    r = np.random.default_rng(5)
    clean = np.column_stack([np.full(100, 1.0), r.normal(0, 0.01, 100),
                             r.normal(0, 0.01, 100)])
    assert is_steady_rotation(clean), "clean commanded roll must suppress"
    mixed = clean.copy()
    mixed[50] = np.array([1e-12, 0.0, 0.0])
    assert is_steady_rotation(mixed), (
        "intermittently zeroing gyro must not evade the gate"
    )
    erratic = np.column_stack([np.full(100, 1.0), np.linspace(0, 1, 100),
                               np.zeros(100)])
    erratic[:, 1] = np.linspace(-1, 1, 100)  # axis reversal -> not steady
    assert not is_steady_rotation(erratic), "axis-reversing motion must fire"
    assert not is_steady_rotation(np.zeros((50, 3))), "zero rotation must fire"


if __name__ == "__main__":
    print("=" * 70)
    print("V1.0.10 HARDENING REGRESSION TESTS")
    print("=" * 70)
    test_noisy_barrel_roll_keeps_winding()
    print("  ✅ noisy barrel roll keeps real winding (SVD selector)")
    test_noise_blob_stays_quiet()
    print("  ✅ clustered noise blob stays quiet")
    test_steady_gate_tolerates_near_zero_rows()
    print("  ✅ steady gate tolerates near-zero rows")
    print("=" * 70)
    print("✅ ALL V1.0.10 HARDENING TESTS PASSED")
    print("=" * 70)
    print("\n🦉⚓🦆📡🔒\n")

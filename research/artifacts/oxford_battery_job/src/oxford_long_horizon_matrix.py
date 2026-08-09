#!/usr/bin/env python3
"""
Oxford Battery — Long-Horizon Diffusion Bottleneck Matrix
=========================================================
For Helix-CORE / Azure Standard_E16ads_v7 (16 vCPU, 128 GiB)

Goal
----
Give diffusion time to speak. Previous 5 s probes were reaction-limited
(√(Dt) << L). This matrix runs T_end long enough that √(Dt) approaches
electrode thickness for the low-D cases, so Standard should form a
sharp surface boundary layer while Helix Master Reset is tested under
true diffusion stress.

Variants
--------
  D_Li : 1.2e-14, 5e-15, 1e-15, 5e-16, 1e-16   (m²/s)
  C    : 3.0, 5.0                              (C-rate)
  Arms : Standard, Helix
  T    : adaptive — scaled so √(D * T) ~ 0.4 * L for the lowest D

Outputs (results/)
------------------
  long_horizon_summary.csv
  profiles/  final c(x), γ(x), R(x) for each (D, C, arm)
  timeseries/ selected high-stress runs

Usage
-----
  python oxford_long_horizon_matrix.py
  python oxford_long_horizon_matrix.py --quick     # shorter subset
  python oxford_long_horizon_matrix.py --D 1e-16 --C 5 --helix
"""

import argparse
import csv
import time
from pathlib import Path
import numpy as np
import importlib.util

# ---------------------------------------------------------------------------
# Load continuum module (same directory)
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "cont", HERE / "oxford_battery_1d_continuum.py")
cont = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cont)

RESULTS = HERE.parent / "results"
PROFILES = RESULTS / "profiles"
TIMESERIES = RESULTS / "timeseries"
for d in (RESULTS, PROFILES, TIMESERIES):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Matrix definition
# ---------------------------------------------------------------------------
D_VALUES = [1.2e-14, 5e-15, 1e-15, 5e-16, 1e-16]
C_VALUES = [3.0, 5.0]

def target_T(D, L=cont.L, fraction=0.45):
    """
    Choose T so √(D T) ≈ fraction * L.
    Caps at 3600 s for the most severe cases.
    """
    target_length = fraction * L
    T = (target_length ** 2) / max(D, 1e-20)
    return float(min(max(T, 30.0), 3600.0))


def extract(h, D, C, helix, T, wall):
    return {
        "D_Li": D,
        "C_rate": C,
        "helix": int(helix),
        "T_end": T,
        "max_R": float(np.max(h["R_max"])),
        "final_R_surface": float(h["R_surface"][-1]),
        "max_gamma": float(np.max(h["gamma_max"])),
        "final_gamma_surface": float(h["gamma_surface"][-1]),
        "delta_c_norm": float((h["c_surface"][-1] - h["c_bulk"][-1]) / cont.c_max),
        "final_c_mean_norm": float(h["c_mean"][-1] / cont.c_max),
        "time_gamma_above": float(np.mean(h["gamma_max"] > cont.gamma_crit)),
        "wall_s": wall,
        "N": cont.N,
        "L_um": cont.L * 1e6,
    }


def write_profile(h, path):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["x_um", "c", "gamma", "R"])
        for i in range(cont.N):
            w.writerow([
                f"{cont.x[i]*1e6:.4f}",
                f"{h['final_c'][i]:.8e}",
                f"{h['final_gamma'][i]:.6f}",
                f"{h['final_R'][i]:.6f}",
            ])


def write_ts(h, path):
    keys = ["t", "c_mean", "c_surface", "c_bulk", "gamma_max",
            "gamma_surface", "R_max", "R_surface", "j_mean"]
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(keys)
        for i in range(len(h["t"])):
            w.writerow([f"{h[k][i]:.8e}" for k in keys])


def run_one(D, C, helix, T, dt=5e-5, record_every=100, save_ts=False):
    cont.D_Li = D
    label = "helix" if helix else "std"
    tag = f"D{D:.0e}_C{C:.0f}_{label}_T{T:.0f}"
    print(f"  → {tag} ...", end=" ", flush=True)
    t0 = time.time()
    h = cont.run_electrode(
        t_end=T,
        C_rate=C,
        helix=helix,
        dt=dt,
        record_every=record_every,
    )
    wall = time.time() - t0
    m = extract(h, D, C, helix, T, wall)
    write_profile(h, PROFILES / f"{tag}_profile.csv")
    if save_ts:
        write_ts(h, TIMESERIES / f"{tag}_ts.csv")
    print(f"max_R={m['max_R']:.2f}  R_surf={m['final_R_surface']:.2f}  "
          f"Δc={m['delta_c_norm']:.5f}  wall={wall:.1f}s")
    return m


def run_matrix(quick=False, single_D=None, single_C=None, single_helix=None):
    summary_path = RESULTS / "long_horizon_summary.csv"
    keys = ["D_Li", "C_rate", "helix", "T_end", "max_R", "final_R_surface",
            "max_gamma", "final_gamma_surface", "delta_c_norm",
            "final_c_mean_norm", "time_gamma_above", "wall_s", "N", "L_um"]

    with summary_path.open("w", newline="") as f:
        csv.DictWriter(f, fieldnames=keys).writeheader()

    Ds = [single_D] if single_D is not None else (D_VALUES[:2] if quick else D_VALUES)
    Cs = [single_C] if single_C is not None else ([5.0] if quick else C_VALUES)
    arms = ([bool(single_helix)] if single_helix is not None else [False, True])

    print("=" * 72)
    print("Oxford Battery Long-Horizon Matrix")
    print(f"Results → {RESULTS}")
    print("=" * 72)

    rows = []
    for D in Ds:
        T = target_T(D)
        if quick:
            T = min(T, 120.0)
        for C in Cs:
            for helix in arms:
                # save full timeseries only for the most severe + nominal
                save_ts = (D <= 5e-16) or (D >= 1e-14)
                m = run_one(D, C, helix, T, save_ts=save_ts)
                rows.append(m)
                with summary_path.open("a", newline="") as f:
                    csv.DictWriter(f, fieldnames=keys).writerow(
                        {k: m[k] for k in keys})

    print("\n" + "=" * 72)
    print(f"{'D_Li':>10} {'C':>4} {'Arm':>6} {'T':>7} {'max_R':>10} "
          f"{'R_surf':>10} {'Δc':>9}")
    print("-" * 72)
    for r in rows:
        arm = "HELIX" if r["helix"] else "STD"
        print(f"{r['D_Li']:10.1e} {r['C_rate']:4.0f} {arm:>6} {r['T_end']:7.0f} "
              f"{r['max_R']:10.2f} {r['final_R_surface']:10.2f} "
              f"{r['delta_c_norm']:9.5f}")
    print("=" * 72)
    print(f"\nSummary written: {summary_path}")
    return rows


def main():
    p = argparse.ArgumentParser(description="Oxford Battery long-horizon matrix")
    p.add_argument("--quick", action="store_true",
                   help="Short subset for smoke test")
    p.add_argument("--D", type=float, default=None, help="Single D_Li value")
    p.add_argument("--C", type=float, default=None, help="Single C-rate")
    p.add_argument("--helix", type=int, choices=[0, 1], default=None,
                   help="0=Standard only, 1=Helix only")
    args = p.parse_args()
    run_matrix(quick=args.quick, single_D=args.D,
               single_C=args.C, single_helix=args.helix)


if __name__ == "__main__":
    main()

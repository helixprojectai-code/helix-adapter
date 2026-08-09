#!/usr/bin/env python3
"""
Oxford Battery — Diffusivity Bottleneck Sweep
Fixed C-rate, D_Li from nominal down toward 1e-16 m²/s
Standard vs Helix: does geometric healing survive severe diffusion limits?
"""

import numpy as np
from pathlib import Path
import csv
import time
import importlib.util

spec = importlib.util.spec_from_file_location(
    "cont", "/home/workdir/artifacts/oxford_battery_1d_continuum.py")
cont = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cont)

# Diffusivity ladder (m²/s)
D_VALUES = [
    1.2e-14,   # current nominal
    5.0e-15,
    2.0e-15,
    1.0e-15,
    5.0e-16,
    2.0e-16,
    1.0e-16,
]

C_RATE = 4.0
T_END = 5.0
DT = 4.0e-5
RECORD_EVERY = 40

def extract_metrics(h, D):
    return {
        "D_Li": D,
        "C_rate": h["C_rate"],
        "helix": h["helix"],
        "max_R": float(np.max(h["R_max"])),
        "final_R_surface": float(h["R_surface"][-1]),
        "max_gamma": float(np.max(h["gamma_max"])),
        "delta_c_norm": float((h["c_surface"][-1] - h["c_bulk"][-1]) / cont.c_max),
        "final_c_mean_norm": float(h["c_mean"][-1] / cont.c_max),
        "time_gamma_above": float(np.mean(h["gamma_max"] > cont.gamma_crit)),
    }

def run_D_sweep():
    rows = []
    out_path = Path("/home/workdir/artifacts/oxford_D_sweep.csv")
    keys = ["D_Li", "C_rate", "helix", "max_R", "final_R_surface", "max_gamma",
            "delta_c_norm", "final_c_mean_norm", "time_gamma_above", "wall_s"]
    with out_path.open("w", newline="") as f:
        csv.DictWriter(f, fieldnames=keys).writeheader()

    print("=" * 72)
    print(f"Oxford Battery Diffusivity Sweep  |  fixed {C_RATE}C")
    print(f"T_end={T_END}s  N={cont.N}  L={cont.L*1e6:.0f} µm")
    print("=" * 72)

    # stash original
    D_orig = cont.D_Li

    for D in D_VALUES:
        cont.D_Li = D
        for helix in (False, True):
            label = "HELIX" if helix else "STANDARD"
            print(f"\n  → {label}  D={D:.1e} ...", end=" ", flush=True)
            t0 = time.time()
            h = cont.run_electrode(
                t_end=T_END,
                C_rate=C_RATE,
                helix=helix,
                dt=DT,
                record_every=RECORD_EVERY,
            )
            m = extract_metrics(h, D)
            m["wall_s"] = time.time() - t0
            rows.append(m)
            with out_path.open("a", newline="") as f:
                csv.DictWriter(f, fieldnames=keys).writerow({k: m[k] for k in keys})
            print(f"max_R={m['max_R']:.2f}  R_surf={m['final_R_surface']:.2f}  "
                  f"Δc={m['delta_c_norm']:.5f}  ({m['wall_s']:.1f}s)")

    cont.D_Li = D_orig
    return rows

def print_table(rows):
    print("\n" + "=" * 72)
    print(f"{'D_Li':>10}  {'Arm':>8}  {'max_R':>10}  {'R_surf':>10}  "
          f"{'max_γ':>8}  {'Δc/cmax':>9}")
    print("-" * 72)
    for r in rows:
        arm = "HELIX" if r["helix"] else "STD"
        print(f"{r['D_Li']:10.1e}  {arm:>8}  {r['max_R']:10.2f}  "
              f"{r['final_R_surface']:10.2f}  {r['max_gamma']:8.4f}  "
              f"{r['delta_c_norm']:9.5f}")
    print("=" * 72)

    print("\nSeparation (STD max_R − HELIX max_R) at each D:")
    for D in D_VALUES:
        std = next(r for r in rows if r["D_Li"] == D and not r["helix"])
        hel = next(r for r in rows if r["D_Li"] == D and r["helix"])
        print(f"  D={D:.1e} : ΔR_max = {std['max_R'] - hel['max_R']:.2f}   "
              f"(STD {std['max_R']:.2f}  vs  HELIX {hel['max_R']:.2f})")

if __name__ == "__main__":
    rows = run_D_sweep()
    print_table(rows)
    print("\nDiffusivity bottleneck probe complete.")
    print("GLORY TO THE LATTICE.")

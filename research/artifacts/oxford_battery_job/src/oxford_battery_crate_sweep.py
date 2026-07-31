#!/usr/bin/env python3
"""
Oxford Battery — C-Rate Sweep
R_max(C) for Standard vs Helix (1C → 8C)

Reuses the 1-D continuum stepper. Focused on the bifurcation:
where Standard risk goes runaway while Helix stays flat.
"""

import numpy as np
from pathlib import Path
import csv
import time
import importlib.util

# ---------------------------------------------------------------------------
# Load the continuum module
# ---------------------------------------------------------------------------
spec = importlib.util.spec_from_file_location(
    "cont", "/home/workdir/artifacts/oxford_battery_1d_continuum.py")
cont = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cont)

# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------
C_RATES = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
T_END = 5.0                 # seconds — enough for risk divergence
DT = 4.0e-5                 # coarser for sweep throughput
RECORD_EVERY = 40

def extract_metrics(h):
    return {
        "C_rate": h["C_rate"],
        "helix": h["helix"],
        "max_R": float(np.max(h["R_max"])),
        "final_R_surface": float(h["R_surface"][-1]),
        "max_gamma": float(np.max(h["gamma_max"])),
        "final_gamma_surface": float(h["gamma_surface"][-1]),
        "delta_c_norm": float((h["c_surface"][-1] - h["c_bulk"][-1]) / cont.c_max),
        "time_gamma_above": float(np.mean(h["gamma_max"] > cont.gamma_crit)),
        "final_c_mean_norm": float(h["c_mean"][-1] / cont.c_max),
    }

def run_sweep():
    rows = []
    out_path = Path("/home/workdir/artifacts/oxford_crate_sweep.csv")
    keys = ["C_rate", "helix", "max_R", "final_R_surface", "max_gamma",
            "final_gamma_surface", "delta_c_norm", "time_gamma_above",
            "final_c_mean_norm", "wall_s"]
    # write header immediately
    with out_path.open("w", newline="") as f:
        csv.DictWriter(f, fieldnames=keys).writeheader()

    print("=" * 70)
    print("Oxford Battery C-Rate Sweep  |  Standard vs Helix")
    print(f"T_end={T_END}s  N={cont.N}  L={cont.L*1e6:.0f}µm  D_Li={cont.D_Li:.1e}")
    print("=" * 70)

    for C in C_RATES:
        for helix in (False, True):
            label = "HELIX" if helix else "STANDARD"
            print(f"\n  → {label} @ {C:.0f}C ...", end=" ", flush=True)
            t0 = time.time()
            h = cont.run_electrode(
                t_end=T_END,
                C_rate=C,
                helix=helix,
                dt=DT,
                record_every=RECORD_EVERY,
            )
            m = extract_metrics(h)
            m["wall_s"] = time.time() - t0
            rows.append(m)
            # incremental write
            with out_path.open("a", newline="") as f:
                csv.DictWriter(f, fieldnames=keys).writerow({k: m[k] for k in keys})
            print(f"max_R={m['max_R']:.3f}  R_surf={m['final_R_surface']:.3f}  "
                  f"Δc={m['delta_c_norm']:.4f}  ({m['wall_s']:.1f}s)")

    return rows

def write_results(rows, path):
    path = Path(path)
    keys = ["C_rate", "helix", "max_R", "final_R_surface", "max_gamma",
            "final_gamma_surface", "delta_c_norm", "time_gamma_above",
            "final_c_mean_norm", "wall_s"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in keys})
    print(f"\nWrote {path}")

def print_table(rows):
    print("\n" + "=" * 70)
    print(f"{'C-rate':>6}  {'Arm':>8}  {'max_R':>10}  {'R_surf':>10}  "
          f"{'max_γ':>8}  {'Δc/cmax':>9}")
    print("-" * 70)
    for r in rows:
        arm = "HELIX" if r["helix"] else "STD"
        print(f"{r['C_rate']:6.1f}  {arm:>8}  {r['max_R']:10.3f}  "
              f"{r['final_R_surface']:10.3f}  {r['max_gamma']:8.4f}  "
              f"{r['delta_c_norm']:9.5f}")
    print("=" * 70)

    # separation summary
    print("\nSeparation (Standard max_R − Helix max_R):")
    for C in C_RATES:
        std = next(r for r in rows if r["C_rate"] == C and not r["helix"])
        hel = next(r for r in rows if r["C_rate"] == C and r["helix"])
        print(f"  {C:.0f}C : ΔR_max = {std['max_R'] - hel['max_R']:.2f}   "
              f"(STD {std['max_R']:.2f}  vs  HELIX {hel['max_R']:.2f})")

if __name__ == "__main__":
    rows = run_sweep()
    write_results(rows, "/home/workdir/artifacts/oxford_crate_sweep.csv")
    print_table(rows)
    print("\nDone. Core hypothesis under C-rate stress is now quantified.")
    print("GLORY TO THE LATTICE.")

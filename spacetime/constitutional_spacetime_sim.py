#!/usr/bin/env python3
"""
================================================================================
CONSTITUTIONAL SPACETIME — KNOT ENSEMBLE SIMULATOR
================================================================================
Generates a 3D field of temporal knots, computes pairwise Gauss linking numbers,
derives the emergent metric, and compares to Schwarzschild prediction.

Designed for: Azure Standard_E16ads_v7 (16 vCPU, 128 GB RAM)
Run: nohup python3 constitutional_spacetime_sim.py > run.log 2>&1 &

Expected wall time: 15-45 minutes depending on N_KNOTS and N_POINTS
================================================================================
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import csv
import time
import os
import json

# ==============================================================================
# CONFIGURATION
# ==============================================================================

N_KNOTS = 2000
N_SEGMENTS = 50
KNOT_RADIUS = 1e-3
L_KNOT = 1e-2

N_POINTS = 100
R_MIN = 1e-3
R_MAX = 1.0

F_HEARTBEAT = 300.0
T_HEARTBEAT = 1.0 / F_HEARTBEAT
C_HELIX = 3.0e8
GAMMA_CRIT = 1.0 / 3.0

M_KNOT_DENSITY = 1e20
M_POINT = 1.989e30

SEED = 42
np.random.seed(SEED)

OUT_DIR = "constitutional_spacetime_output"
os.makedirs(OUT_DIR, exist_ok=True)

print("=" * 70)
print("CONSTITUTIONAL SPACETIME — KNOT ENSEMBLE SIMULATOR")
print("=" * 70)
print(f"Knots:       {N_KNOTS}")
print(f"Segments:    {N_SEGMENTS} per knot = {N_KNOTS * N_SEGMENTS:,} total segments")
print(f"Eval points: {N_POINTS} radial points")
print(f"Mass:        {M_POINT:.3e} kg (solar-mass equivalent)")
print(f"RAM est:     ~{(N_KNOTS * N_SEGMENTS * 3 * 8 * 2) / (1024**3):.2f} GB")
print("=" * 70)


def generate_knot_ensemble(n_knots, n_segments, radius, length, mass_center, mass_scale):
    print(f"\nGenerating {n_knots} knots...")
    t0 = time.time()
    knots = np.zeros((n_knots, n_segments, 3))
    for i in range(n_knots):
        center = np.random.normal(0, mass_scale, 3)
        pos = center.copy()
        step_size = length / n_segments
        for j in range(n_segments):
            knots[i, j] = pos.copy()
            step = np.random.randn(3)
            step = step / np.linalg.norm(step) * step_size
            drift = -0.1 * (pos - center) / (np.linalg.norm(pos - center) + 1e-10) * step_size
            pos += step + drift
    print(f"  Done in {time.time() - t0:.2f}s")
    return knots


def compute_linking_matrix_fast(knots):
    print("\nComputing linking matrix (fast approximation)...")
    t0 = time.time()
    n = len(knots)
    midpoints = (knots[:, :-1, :] + knots[:, 1:, :]) / 2.0
    tangents = knots[:, 1:, :] - knots[:, :-1, :]
    lk_matrix = np.zeros((n, n))
    batch_size = 50
    for i_start in range(0, n, batch_size):
        i_end = min(i_start + batch_size, n)
        for j_start in range(i_start, n, batch_size):
            j_end = min(j_start + batch_size, n)
            r_i = midpoints[i_start:i_end, None, :, None, :]
            r_j = midpoints[None, j_start:j_end, None, :, :]
            r_diff = r_i - r_j
            r_norm = np.linalg.norm(r_diff, axis=-1, keepdims=True)
            r_norm = np.maximum(r_norm, 1e-12)
            t_i = tangents[i_start:i_end, None, :, None, :]
            t_j = tangents[None, j_start:j_end, None, :, :]
            cross = np.cross(t_i, t_j)
            numerator = np.sum(r_diff * cross, axis=-1)
            integrand = numerator / (r_norm.squeeze() ** 3)
            lk_batch = np.sum(integrand, axis=(2, 3)) / (4.0 * np.pi)
            lk_matrix[i_start:i_end, j_start:j_end] = lk_batch
    lk_matrix = lk_matrix + lk_matrix.T - np.diag(np.diag(lk_matrix))
    print(f"  Done in {time.time() - t0:.2f}s")
    return lk_matrix


def derive_metric(knots, lk_matrix, eval_points):
    print("\nDeriving emergent metric...")
    t0 = time.time()
    n_points = len(eval_points)
    g_rr = np.zeros(n_points)
    knot_density = np.zeros(n_points)
    gamma_local = np.zeros(n_points)
    for idx, r in enumerate(eval_points):
        neighborhood_radius = 3 * L_KNOT
        knot_centers = np.mean(knots, axis=1)
        distances = np.linalg.norm(knot_centers, axis=1)
        weights = 1.0 / (distances + 1e-10)
        weights = weights / np.sum(weights)
        knot_density[idx] = np.sum(weights[distances < neighborhood_radius])
        mask = distances < neighborhood_radius
        if np.sum(mask) < 2:
            g_rr[idx] = 1.0
            gamma_local[idx] = 0.0
            continue
        lk_subset = lk_matrix[np.ix_(mask, mask)]
        lk_correlation = np.mean(np.abs(lk_subset))
        alpha = 1e-4
        g_rr[idx] = 1.0 + alpha * lk_correlation * knot_density[idx]
        gamma_local[idx] = min(knot_density[idx] / np.max(knot_density), 0.999)
    print(f"  Done in {time.time() - t0:.2f}s")
    return g_rr, knot_density, gamma_local


def schwarzschild_metric(r, M, G=6.674e-11, c=3e8):
    rs = 2 * G * M / c**2
    return 1.0 / (1.0 - rs / r)


def schwarzschild_time_dilation(r, M, G=6.674e-11, c=3e8):
    rs = 2 * G * M / c**2
    return np.sqrt(1.0 - rs / r)


def main():
    t_start = time.time()
    print("\n" + "=" * 70)
    print("PHASE 1: KNOT GENERATION")
    print("=" * 70)
    mass_scale = 0.1
    knots = generate_knot_ensemble(N_KNOTS, N_SEGMENTS, KNOT_RADIUS, L_KNOT, 
                                    np.array([0, 0, 0]), mass_scale)
    print("\n" + "=" * 70)
    print("PHASE 2: LINKING NUMBER COMPUTATION")
    print("=" * 70)
    lk_matrix = compute_linking_matrix_fast(knots)
    lk_flat = lk_matrix[np.triu_indices_from(lk_matrix, k=1)]
    print(f"\nLinking number statistics:")
    print(f"  Mean |Lk|:   {np.mean(np.abs(lk_flat)):.6f}")
    print(f"  Std |Lk|:    {np.std(np.abs(lk_flat)):.6f}")
    print(f"  Max |Lk|:    {np.max(np.abs(lk_flat)):.6f}")
    print(f"  Non-zero:    {np.sum(np.abs(lk_flat) > 0.01)} / {len(lk_flat)}")
    print("\n" + "=" * 70)
    print("PHASE 3: METRIC DERIVATION")
    print("=" * 70)
    eval_points = np.linspace(R_MIN, R_MAX, N_POINTS)
    g_rr_helix, rho_knot, gamma = derive_metric(knots, lk_matrix, eval_points)
    g_rr_schwarz = schwarzschild_metric(eval_points, M_POINT)
    td_helix = 1.0 - gamma
    td_schwarz = schwarzschild_time_dilation(eval_points, M_POINT)
    print("\n" + "=" * 70)
    print("PHASE 4: EXPORT & PLOTTING")
    print("=" * 70)
    csv_path = os.path.join(OUT_DIR, "metric_comparison.csv")
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["r_m", "g_rr_helix", "g_rr_schwarzschild", 
                         "time_dilation_helix", "time_dilation_schwarzschild",
                         "knot_density", "gamma_local"])
        for i in range(N_POINTS):
            writer.writerow([
                f"{eval_points[i]:.6e}",
                f"{g_rr_helix[i]:.6f}",
                f"{g_rr_schwarz[i]:.6f}",
                f"{td_helix[i]:.6f}",
                f"{td_schwarz[i]:.6f}",
                f"{rho_knot[i]:.6f}",
                f"{gamma[i]:.6f}"
            ])
    print(f"  CSV saved: {csv_path}")
    summary = {
        "n_knots": N_KNOTS,
        "n_segments": N_SEGMENTS,
        "n_eval_points": N_POINTS,
        "mass_kg": M_POINT,
        "f_heartbeat_hz": F_HEARTBEAT,
        "lk_mean_abs": float(np.mean(np.abs(lk_flat))),
        "lk_max_abs": float(np.max(np.abs(lk_flat))),
        "g_rr_helix_max": float(np.max(g_rr_helix)),
        "g_rr_schwarzschild_max": float(np.max(g_rr_schwarz)),
        "gamma_max": float(np.max(gamma)),
    }
    fig = plt.figure(figsize=(16, 12))
    ax1 = fig.add_subplot(2, 2, 1)
    ax1.semilogy(eval_points, g_rr_helix, 'r-', lw=2.5, label='Helix (emergent)')
    ax1.semilogy(eval_points, g_rr_schwarz, 'b--', lw=2, label='Schwarzschild')
    ax1.set_xlabel('Radius r [m]')
    ax1.set_ylabel('$g_{rr}$')
    ax1.set_title('(a) Metric Component $g_{rr}$')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax2 = fig.add_subplot(2, 2, 2)
    ax2.plot(eval_points, td_helix, 'r-', lw=2.5, label='Helix ($1 - \\gamma$)')
    ax2.plot(eval_points, td_schwarz, 'b--', lw=2, label='Schwarzschild')
    ax2.set_xlabel('Radius r [m]')
    ax2.set_ylabel('Time dilation factor')
    ax2.set_title('(b) Gravitational Time Dilation')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax3 = fig.add_subplot(2, 2, 3)
    ax3.loglog(eval_points, rho_knot, 'g-', lw=2.5)
    ax3.set_xlabel('Radius r [m]')
    ax3.set_ylabel('Normalized knot density')
    ax3.set_title('(c) Knot Density Profile')
    ax3.grid(True, alpha=0.3)
    ax4 = fig.add_subplot(2, 2, 4)
    ax4.semilogx(eval_points, gamma, 'm-', lw=2.5)
    ax4.axhline(y=1.0/3.0, color='green', ls=':', lw=2, label='$\\gamma_{crit} = 1/3$')
    ax4.axhline(y=0.17, color='orange', ls=':', lw=2, label='Drift = 0.17')
    ax4.set_xlabel('Radius r [m]')
    ax4.set_ylabel('Local shear $\\gamma$')
    ax4.set_title('(d) Gravitational Shear Profile')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    plt.suptitle(
        'Constitutional Spacetime: Emergent Metric vs. Schwarzschild\n'
        f'{N_KNOTS} knots, {N_SEGMENTS} segments, {M_POINT:.2e} kg',
        fontsize=14, fontweight='bold'
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plot_path = os.path.join(OUT_DIR, "metric_comparison.png")
    plt.savefig(plot_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"  Plot saved: {plot_path}")
    summary["wall_time_s"] = time.time() - t_start
    json_path = os.path.join(OUT_DIR, "simulation_summary.json")
    with open(json_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"  JSON saved: {json_path}")
    print("\n" + "=" * 70)
    print("SIMULATION COMPLETE")
    print("=" * 70)
    print(f"Total wall time: {summary['wall_time_s']:.1f}s")
    print(f"All outputs in: {os.path.abspath(OUT_DIR)}/")


if __name__ == '__main__':
    main()

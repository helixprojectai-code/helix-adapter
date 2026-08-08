#!/usr/bin/env python3
"""
================================================================================
CONSTITUTIONAL SPACETIME — REAL TEST (Pure NumPy, no JIT)
Structured knot ensembles with controlled linking numbers
================================================================================
"""

import numpy as np
import csv
import time
import os
import json

N_HOPF_PAIRS = 500
N_TORUS_KNOTS = 300
N_FIGURE_EIGHT = 200
N_SEGMENTS = 100
R_KNOT = 1e-3
R_MIN = 1e-2
R_MAX = 10.0
M_TOTAL = 1.989e30
G = 6.674e-11
c = 3.0e8
RS = 2 * G * M_TOTAL / c**2
N_RADIAL = 200
R_EVAL_MIN = RS * 1.01
R_EVAL_MAX = 100.0
GAMMA_CRIT = 1.0 / 3.0
OUT_DIR = "constitutional_spacetime_real"
os.makedirs(OUT_DIR, exist_ok=True)

print("=" * 70)
print("CONSTITUTIONAL SPACETIME — REAL TEST (Pure NumPy)")
print("=" * 70)
print(f"Hopf pairs:     {N_HOPF_PAIRS}")
print(f"Torus knots:    {N_TORUS_KNOTS}")
print(f"Figure eights:  {N_FIGURE_EIGHT}")
print(f"Total knots:    {2*N_HOPF_PAIRS + N_TORUS_KNOTS + N_FIGURE_EIGHT}")
print(f"Segments:       {N_SEGMENTS}")
print(f"Schwarzschild:  Rs = {RS:.3f} m")
print("=" * 70)


def generate_hopf_pair(center, radius, phase, link_sign=1):
    t = np.linspace(0, 2*np.pi, N_SEGMENTS)
    knot_a = np.zeros((N_SEGMENTS, 3))
    knot_a[:, 0] = radius * np.cos(t + phase)
    knot_a[:, 1] = radius * np.sin(t + phase)
    knot_a[:, 2] = 0.0
    knot_b = np.zeros((N_SEGMENTS, 3))
    knot_b[:, 0] = radius * np.cos(t + phase + np.pi/2)
    knot_b[:, 2] = radius * np.sin(t + phase + np.pi/2)
    knot_b[:, 1] = link_sign * radius
    knot_a += center
    knot_b += center
    return knot_a, knot_b


def generate_trefoil(center, radius, phase):
    t = np.linspace(0, 2*np.pi, N_SEGMENTS)
    knot = np.zeros((N_SEGMENTS, 3))
    knot[:, 0] = radius * (np.sin(t) + 2*np.sin(2*t)) / 3 + center[0]
    knot[:, 1] = radius * (np.cos(t) - 2*np.cos(2*t)) / 3 + center[1]
    knot[:, 2] = radius * (-np.sin(3*t)) / 3 + center[2]
    return knot


def generate_figure_eight(center, radius, phase):
    t = np.linspace(0, 2*np.pi, N_SEGMENTS)
    knot = np.zeros((N_SEGMENTS, 3))
    knot[:, 0] = radius * (2 + np.cos(2*t)) * np.cos(3*t) / 3 + center[0]
    knot[:, 1] = radius * (2 + np.cos(2*t)) * np.sin(3*t) / 3 + center[1]
    knot[:, 2] = radius * np.sin(4*t) / 3 + center[2]
    return knot


def sample_shell_position(r_min, r_max, power=-2.0):
    u = np.random.random()
    p = power
    r = (u * (r_max**(p+1) - r_min**(p+1)) + r_min**(p+1))**(1/(p+1))
    theta = np.arccos(2*np.random.random() - 1)
    phi = 2 * np.pi * np.random.random()
    x = r * np.sin(theta) * np.cos(phi)
    y = r * np.sin(theta) * np.sin(phi)
    z = r * np.cos(theta)
    return np.array([x, y, z]), r


def gauss_lk_exact(knot_a, knot_b):
    """Pure numpy Gauss linking integral."""
    n = knot_a.shape[0]
    m = knot_b.shape[0]
    lk = 0.0
    for i in range(n - 1):
        r1 = knot_a[i]
        dr1 = knot_a[i+1] - knot_a[i]
        for j in range(m - 1):
            r2 = knot_b[j]
            dr2 = knot_b[j+1] - knot_b[j]
            diff = r1 - r2
            r_norm = np.linalg.norm(diff)
            if r_norm < 1e-14:
                continue
            cross = np.cross(dr1, dr2)
            numerator = np.dot(diff, cross)
            lk += numerator / (r_norm ** 3)
    return lk / (4.0 * np.pi)


def build_ensemble():
    print("\nBuilding structured knot ensemble...")
    t0 = time.time()
    knots = []
    knot_types = []
    knot_radii = []

    for i in range(N_HOPF_PAIRS):
        center, r = sample_shell_position(R_MIN, R_MAX, power=-2.0)
        phase = 2 * np.pi * np.random.random()
        link_sign = 1 if np.random.random() > 0.5 else -1
        ka, kb = generate_hopf_pair(center, R_KNOT, phase, link_sign)
        knots.append(ka)
        knots.append(kb)
        knot_types.extend(['hopf_a', 'hopf_b'])
        knot_radii.extend([r, r])

    for i in range(N_TORUS_KNOTS):
        center, r = sample_shell_position(R_MIN, R_MAX, power=-2.0)
        phase = 2 * np.pi * np.random.random()
        k = generate_trefoil(center, R_KNOT, phase)
        knots.append(k)
        knot_types.append('trefoil')
        knot_radii.append(r)

    for i in range(N_FIGURE_EIGHT):
        center, r = sample_shell_position(R_MIN, R_MAX, power=-2.0)
        phase = 2 * np.pi * np.random.random()
        k = generate_figure_eight(center, R_KNOT, phase)
        knots.append(k)
        knot_types.append('figure8')
        knot_radii.append(r)

    print(f"  Done in {time.time() - t0:.2f}s")
    return np.array(knots), np.array(knot_types), np.array(knot_radii)


def compute_linking_matrix(knots, knot_radii, max_distance=0.5):
    print("\nComputing linking matrix (neighbor-restricted)...")
    t0 = time.time()
    n = len(knots)
    lk_matrix = np.zeros((n, n))
    centers = np.array([np.mean(k, axis=0) for k in knots])
    pair_count = 0

    for i in range(n):
        if i % 100 == 0:
            print(f"  Processing knot {i}/{n}...")
        for j in range(i + 1, n):
            dist = np.linalg.norm(centers[i] - centers[j])
            if dist > max_distance:
                continue
            lk = gauss_lk_exact(knots[i], knots[j])
            lk_matrix[i, j] = lk
            lk_matrix[j, i] = lk
            pair_count += 1

    print(f"  Computed {pair_count} pairs in {time.time() - t0:.2f}s")
    return lk_matrix


def derive_metric(knots, lk_matrix, knot_radii, eval_points):
    print("\nDeriving emergent metric...")
    t0 = time.time()
    n_points = len(eval_points)
    g_rr = np.zeros(n_points)
    knot_density = np.zeros(n_points)
    gamma = np.zeros(n_points)
    lk_correlation = np.zeros(n_points)
    centers = np.array([np.mean(k, axis=0) for k in knots])
    n = len(knots)

    for idx, r_eval in enumerate(eval_points):
        nh_radius = 0.1 * r_eval + 0.05
        distances_to_eval = np.linalg.norm(centers, axis=1)
        in_shell = np.abs(distances_to_eval - r_eval) < nh_radius
        n_local = np.sum(in_shell)
        knot_density[idx] = n_local / (4/3 * np.pi * nh_radius**3)

        if n_local < 2:
            g_rr[idx] = 1.0
            gamma[idx] = 0.0
            lk_correlation[idx] = 0.0
            continue

        local_indices = np.where(in_shell)[0]
        lk_subset = lk_matrix[np.ix_(local_indices, local_indices)]
        mask = ~np.eye(len(local_indices), dtype=bool)
        if np.sum(mask) > 0:
            lk_corr = np.mean(np.abs(lk_subset[mask]))
        else:
            lk_corr = 0.0

        lk_correlation[idx] = lk_corr
        alpha = 1e-3
        g_rr[idx] = 1.0 + alpha * lk_corr * knot_density[idx]
        gamma[idx] = min(knot_density[idx] / 1e6, 0.999)

    print(f"  Done in {time.time() - t0:.2f}s")
    return g_rr, knot_density, gamma, lk_correlation


def schwarzschild_g_rr(r, rs):
    x = rs / r
    x = np.clip(x, 0, 0.999)
    return 1.0 / (1.0 - x)


def schwarzschild_time_dilation(r, rs):
    x = rs / r
    x = np.clip(x, 0, 0.999)
    return np.sqrt(1.0 - x)


def main():
    t_start = time.time()

    knots, knot_types, knot_radii = build_ensemble()
    lk_matrix = compute_linking_matrix(knots, knot_radii)

    lk_flat = lk_matrix[np.triu_indices_from(lk_matrix, k=1)]
    lk_nonzero = lk_flat[np.abs(lk_flat) > 0.001]
    print(f"\nLinking number statistics:")
    print(f"  Total pairs:      {len(lk_flat):,}")
    print(f"  Non-zero (|Lk|>0.001): {len(lk_nonzero):,}")
    print(f"  Mean |Lk|:        {np.mean(np.abs(lk_flat)):.6f}")
    if len(lk_nonzero) > 0:
        print(f"  Mean |Lk| (nz):   {np.mean(np.abs(lk_nonzero)):.6f}")
    print(f"  Max |Lk|:         {np.max(np.abs(lk_flat)):.6f}")
    if len(lk_nonzero) > 0:
        print(f"  Std |Lk| (nz):    {np.std(np.abs(lk_nonzero)):.6f}")

    eval_points = np.linspace(R_EVAL_MIN, R_EVAL_MAX, N_RADIAL)
    g_rr_helix, rho_knot, gamma, lk_corr = derive_metric(knots, lk_matrix, knot_radii, eval_points)

    g_rr_schwarz = schwarzschild_g_rr(eval_points, RS)
    td_helix = np.sqrt(1.0 - gamma)
    td_schwarz = schwarzschild_time_dilation(eval_points, RS)

    csv_path = os.path.join(OUT_DIR, "metric_real.csv")
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["r_m", "g_rr_helix", "g_rr_schwarzschild",
                         "time_dilation_helix", "time_dilation_schwarzschild",
                         "knot_density", "lk_correlation", "gamma_local"])
        for i in range(N_RADIAL):
            writer.writerow([
                f"{eval_points[i]:.6e}", f"{g_rr_helix[i]:.6f}", f"{g_rr_schwarz[i]:.6f}",
                f"{td_helix[i]:.6f}", f"{td_schwarz[i]:.6f}",
                f"{rho_knot[i]:.6e}", f"{lk_corr[i]:.6f}", f"{gamma[i]:.6f}"
            ])
    print(f"\nCSV saved: {csv_path}")

    deviation = np.abs(g_rr_helix - g_rr_schwarz) / g_rr_schwarz

    summary = {
        "n_hopf_pairs": N_HOPF_PAIRS,
        "n_torus": N_TORUS_KNOTS,
        "n_figure8": N_FIGURE_EIGHT,
        "n_segments": N_SEGMENTS,
        "mass_kg": M_TOTAL,
        "rs_m": RS,
        "lk_mean_nz": float(np.mean(np.abs(lk_nonzero))) if len(lk_nonzero) > 0 else 0,
        "lk_max": float(np.max(np.abs(lk_flat))),
        "g_rr_helix_max": float(np.max(g_rr_helix)),
        "g_rr_schwarzschild_max": float(np.max(g_rr_schwarz)),
        "gamma_max": float(np.max(gamma)),
        "deviation_max": float(np.max(deviation)),
        "wall_time_s": time.time() - t_start
    }
    json_path = os.path.join(OUT_DIR, "summary_real.json")
    with open(json_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"JSON saved: {json_path}")

    print("\n" + "=" * 70)
    print("REAL TEST COMPLETE")
    print("=" * 70)
    print(f"Wall time: {summary['wall_time_s']:.1f}s")
    print(f"Max |Lk|: {summary['lk_max']:.4f} (should be ~1.0 for Hopf pairs)")
    print(f"Max g_rr deviation: {summary['deviation_max']:.4f}")
    print(f"All outputs in: {os.path.abspath(OUT_DIR)}/")


if __name__ == '__main__':
    main()

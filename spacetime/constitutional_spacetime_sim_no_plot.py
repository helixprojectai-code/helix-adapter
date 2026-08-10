#!/usr/bin/env python3
import numpy as np
import csv
import time
import os
import json

N_KNOTS = 2000
N_SEGMENTS = 50
KNOT_RADIUS = 1e-3
L_KNOT = 1e-2
N_POINTS = 100
R_MIN = 1e-3
R_MAX = 1.0
F_HEARTBEAT = 300.0
M_POINT = 1.989e30
SEED = 42
np.random.seed(SEED)
OUT_DIR = "constitutional_spacetime_output"
os.makedirs(OUT_DIR, exist_ok=True)

print("="*70)
print("CONSTITUTIONAL SPACETIME — KNOT ENSEMBLE SIMULATOR (No Plot)")
print("="*70)

t_start = time.time()

print("\nPHASE 1: KNOT GENERATION")
knots = np.zeros((N_KNOTS, N_SEGMENTS, 3))
for i in range(N_KNOTS):
    center = np.random.normal(0, 0.1, 3)
    pos = center.copy()
    step_size = L_KNOT / N_SEGMENTS
    for j in range(N_SEGMENTS):
        knots[i, j] = pos.copy()
        step = np.random.randn(3)
        step = step / np.linalg.norm(step) * step_size
        drift = -0.1 * (pos - center) / (np.linalg.norm(pos - center) + 1e-10) * step_size
        pos += step + drift
print(f"  Done in {time.time() - t_start:.2f}s")

print("\nPHASE 2: LINKING NUMBER COMPUTATION")
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
lk_flat = lk_matrix[np.triu_indices_from(lk_matrix, k=1)]
print(f"  Done in {time.time() - t0:.2f}s")
print(f"  Mean |Lk|: {np.mean(np.abs(lk_flat)):.6f}")
print(f"  Max |Lk|:  {np.max(np.abs(lk_flat)):.6f}")

print("\nPHASE 3: METRIC DERIVATION")
t0 = time.time()
eval_points = np.linspace(R_MIN, R_MAX, N_POINTS)
g_rr_helix = np.zeros(N_POINTS)
gamma_local = np.zeros(N_POINTS)
for idx in range(N_POINTS):
    knot_centers = np.mean(knots, axis=1)
    distances = np.linalg.norm(knot_centers, axis=1)
    neighborhood_radius = 3 * L_KNOT
    mask = distances < neighborhood_radius
    if np.sum(mask) >= 2:
        lk_subset = lk_matrix[np.ix_(mask, mask)]
        lk_correlation = np.mean(np.abs(lk_subset))
        alpha = 1e-4
        weights = 1.0 / (distances + 1e-10)
        weights = weights / np.sum(weights)
        knot_density = np.sum(weights[distances < neighborhood_radius])
        g_rr_helix[idx] = 1.0 + alpha * lk_correlation * knot_density
        gamma_local[idx] = min(knot_density / np.max(weights), 0.999)
    else:
        g_rr_helix[idx] = 1.0
        gamma_local[idx] = 0.0
print(f"  Done in {time.time() - t0:.2f}s")

def schwarzschild_metric(r, M, G=6.674e-11, c=3e8):
    rs = 2 * G * M / c**2
    return 1.0 / (1.0 - rs / r)

def schwarzschild_time_dilation(r, M, G=6.674e-11, c=3e8):
    rs = 2 * G * M / c**2
    return np.sqrt(1.0 - rs / r)

print("\nPHASE 4: EXPORT")
g_rr_schwarz = schwarzschild_metric(eval_points, M_POINT)
td_helix = 1.0 - gamma_local
td_schwarz = schwarzschild_time_dilation(eval_points, M_POINT)

csv_path = os.path.join(OUT_DIR, "metric_comparison.csv")
with open(csv_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["r_m", "g_rr_helix", "g_rr_schwarzschild", 
                     "time_dilation_helix", "time_dilation_schwarzschild",
                     "gamma_local"])
    for i in range(N_POINTS):
        writer.writerow([
            f"{eval_points[i]:.6e}",
            f"{g_rr_helix[i]:.6f}",
            f"{g_rr_schwarz[i]:.6f}",
            f"{td_helix[i]:.6f}",
            f"{td_schwarz[i]:.6f}",
            f"{gamma_local[i]:.6f}"
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
    "gamma_max": float(np.max(gamma_local)),
    "wall_time_s": time.time() - t_start
}
json_path = os.path.join(OUT_DIR, "simulation_summary.json")
with open(json_path, 'w') as f:
    json.dump(summary, f, indent=2)
print(f"  JSON saved: {json_path}")

print("\n" + "="*70)
print("SIMULATION COMPLETE")
print("="*70)
print(f"Total wall time: {summary['wall_time_s']:.1f}s")
print(f"All outputs in: {os.path.abspath(OUT_DIR)}/")

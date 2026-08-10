#!/usr/bin/env python3
"""
CONSTITUTIONAL SPACETIME — HIGH MASS VARIANT
Same 32 Hopf pairs, but 100× solar mass
Keeps same geometry, denser horizon shell
"""

import os, json, csv, time, numpy as np

OUT_DIR = 'constitutional_spacetime_highmass'
os.makedirs(OUT_DIR, exist_ok=True)

M_TOTAL = 1.989e32  # 100 solar masses
G = 6.674e-11
C = 3.0e8
RS = 2 * G * M_TOTAL / C**2

N_SEGMENTS = 250
N_HOPF_PAIRS = 32
N_RADIAL = 150
R_MIN = RS * 1.01
R_MAX = 75000.0  # Scale up with Rs
SEED = 42
MAX_DISTANCE = 800.0

np.random.seed(SEED)

def gauss_linking_integral(ka, kb):
    lk = 0.0
    for i in range(len(ka) - 1):
        for j in range(len(kb) - 1):
            r1, dr1 = ka[i], ka[i+1] - ka[i]
            r2, dr2 = kb[j], kb[j+1] - kb[j]
            diff = r1 - r2
            rnorm = np.linalg.norm(diff)
            if rnorm < 1e-10:
                continue
            lk += np.dot(diff, np.cross(dr1, dr2)) / (rnorm ** 3)
    return lk / (4.0 * np.pi)

def hopf_pair_validated(center, phase, sign):
    t = np.linspace(0, 2*np.pi, N_SEGMENTS, endpoint=False)
    a = np.column_stack([
        np.cos(t + phase),
        np.sin(t + phase),
        0.05 * np.sin(2*t)
    ])
    r = 1.0 + 0.35 * np.cos(t)
    b = np.column_stack([
        r * np.cos(t + phase + sign*np.pi),
        r * np.sin(t + phase + sign*np.pi),
        0.35 * np.sin(t)
    ])
    return a + center, b + center

def schwarzschild(r, rs):
    x = np.clip(rs/r, 0, 0.999999)
    return 1.0 / (1.0 - x), np.sqrt(1.0 - x)

print("=== CONSTITUTIONAL SPACETIME: HIGH MASS (100 Msun) ===\n")
print(f"Mass: 100 solar")
print(f"Schwarzschild radius: {RS:.1f} m")
print(f"Hopf pairs: {N_HOPF_PAIRS}")
print(f"Total knots: {N_HOPF_PAIRS * 2}\n")

t_start = time.time()
knots = []
centers = []
hopf_lks = []

for i in range(N_HOPF_PAIRS):
    u = np.random.random()
    r = (u * (R_MAX**(-1) - R_MIN**(-1)) + R_MIN**(-1))**(-1)
    theta = np.arccos(2*np.random.random() - 1)
    phi = 2*np.pi*np.random.random()
    center = np.array([r*np.sin(theta)*np.cos(phi), r*np.sin(theta)*np.sin(phi), r*np.cos(theta)])

    phase = 2*np.pi*np.random.random()
    sign = 1 if np.random.random() > 0.5 else -1

    a, b = hopf_pair_validated(center, phase, sign)
    knots.append(a)
    knots.append(b)
    centers.append(np.mean(a, axis=0))
    centers.append(np.mean(b, axis=0))

    lk = gauss_linking_integral(a, b)
    hopf_lks.append(abs(lk))
    if i < 3:
        print(f"Pair {i}: Lk = {lk:.6f}, r_center = {np.linalg.norm(center):.1f} m")

centers = np.array(centers)
print(f"\nMean Hopf |Lk|: {np.mean(hopf_lks):.6f}")
print(f"Ensemble in {time.time() - t_start:.1f}s\n")

print("Computing linking matrix...")
t0 = time.time()
n = len(knots)
lk_matrix = np.zeros((n, n))

for i in range(n):
    for j in range(i + 1, n):
        if np.linalg.norm(centers[i] - centers[j]) > MAX_DISTANCE:
            continue
        lk = gauss_linking_integral(knots[i], knots[j])
        lk_matrix[i, j] = lk
        lk_matrix[j, i] = lk

print(f"Matrix in {time.time() - t0:.1f}s")

print("Deriving metric...")
eval_points = np.linspace(R_MIN, R_MAX, N_RADIAL)
g_rr_helix = np.ones(N_RADIAL)
g_rr_schwarz = np.ones(N_RADIAL)
td_helix = np.ones(N_RADIAL)
td_schwarz = np.ones(N_RADIAL)
rho = np.zeros(N_RADIAL)
gamma = np.zeros(N_RADIAL)
lk_corr = np.zeros(N_RADIAL)

center_norms = np.linalg.norm(centers, axis=1)

for idx, r_eval in enumerate(eval_points):
    nh = 0.15 * r_eval + 100.0
    local = np.abs(center_norms - r_eval) < nh
    n_local = np.sum(local)
    vol = (4/3) * np.pi * nh**3
    rho[idx] = n_local / vol if vol > 0 else 0.0

    if n_local >= 2:
        inds = np.where(local)[0]
        sub = lk_matrix[np.ix_(inds, inds)]
        mask = ~np.eye(len(inds), dtype=bool)
        if np.any(mask):
            lk_corr[idx] = np.mean(np.abs(sub[mask]))
        g_rr_helix[idx] = 1.0 + 1e-1 * lk_corr[idx] * rho[idx]
        gamma[idx] = min(rho[idx] / (rho[idx] + 1e9), 0.999)

    g_rr_s, td_s = schwarzschild(eval_points[idx], RS)
    g_rr_schwarz[idx] = g_rr_s
    td_schwarz[idx] = td_s

td_helix = np.sqrt(np.maximum(1.0 - gamma, 0))
deviation = np.abs(g_rr_helix - g_rr_schwarz) / np.maximum(g_rr_schwarz, 1.0)

with open(os.path.join(OUT_DIR, 'metric.csv'), 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['r_m', 'g_rr_helix', 'g_rr_schwarzschild', 'td_helix', 'td_schwarz', 'rho', 'lk_corr', 'gamma'])
    for i in range(N_RADIAL):
        w.writerow([f'{eval_points[i]:.8e}', f'{g_rr_helix[i]:.8f}', f'{g_rr_schwarz[i]:.8f}',
                    f'{td_helix[i]:.8f}', f'{td_schwarz[i]:.8f}', f'{rho[i]:.8e}', f'{lk_corr[i]:.8f}', f'{gamma[i]:.8f}'])

summary = {
    'version': 'highmass_100msun',
    'mass_factor': 100,
    'rs_m': float(RS),
    'r_min_m': float(R_MIN),
    'r_max_m': float(R_MAX),
    'hopf_lk_mean': float(np.mean(hopf_lks)),
    'g_rr_helix_max': float(np.max(g_rr_helix)),
    'deviation_max': float(np.max(deviation)),
    'wall_time_s': float(time.time() - t_start)
}

with open(os.path.join(OUT_DIR, 'summary.json'), 'w') as f:
    json.dump(summary, f, indent=2)

print("DONE")
print(json.dumps(summary, indent=2))

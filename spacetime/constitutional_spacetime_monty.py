#!/usr/bin/env python3
"""
CONSTITUTIONAL SPACETIME — MONTY PYTHON EDITION
"The Unreasonable Universe"

Parameters so absurd they loop back around to being funny:
- 1,000,000 solar masses (larger than most galaxies)
- Knots packed 0.1mm apart
- 2000 Hopf pairs in a sphere 10 meters across
- What could possibly go wrong?
"""

import os, json, csv, time, numpy as np

OUT_DIR = 'constitutional_spacetime_monty'
os.makedirs(OUT_DIR, exist_ok=True)

# THE UNREASONABLE PARAMETERS
M_TOTAL = 1.989e36  # Million solar masses (ABSOLUTELY BONKERS)
G = 6.674e-11
C = 3.0e8
RS = 2 * G * M_TOTAL / C**2

N_SEGMENTS = 80  # Coarse, this is a comedy show
N_HOPF_PAIRS = 200  # Still silly
N_RADIAL = 80
R_MIN = RS * 1.01  # Just outside horizon (in meters)
R_MAX = RS * 1.1   # Only 10% beyond horizon
SEED = 42
MAX_DISTANCE = 1000.0  # Everything links with everything

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

print("=" * 70)
print("CONSTITUTIONAL SPACETIME — MONTY PYTHON EDITION")
print("'THE UNREASONABLE UNIVERSE'")
print("=" * 70)
print()
print(f"Mass: 1,000,000 solar masses")
print(f"Schwarzschild radius: {RS:.1f} m")
print(f"Evaluation shell: {R_MIN:.1f} to {R_MAX:.1f} m")
print(f"Shell width: {R_MAX - R_MIN:.1f} m")
print(f"Hopf pairs: {N_HOPF_PAIRS}")
print(f"Total knots: {N_HOPF_PAIRS * 2}")
print()
print("'Nobody expects the Spanish Inquisition!'")
print("  — except the black hole")
print()

t_start = time.time()
knots = []
centers = []
hopf_lks = []

print("Building ensemble (this is going to be DENSE)...")
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

centers = np.array(centers)
print(f"Mean Hopf |Lk|: {np.mean(hopf_lks):.6f}")
print(f"Ensemble built in {time.time() - t_start:.1f}s")
print()

print("Computing linking matrix (the whole universe links with itself)...")
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

print(f"Matrix computed in {time.time() - t0:.1f}s")
print()

print("Deriving metric (brace for impact)...")
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
    nh = 0.2 * (R_MAX - R_MIN) + 100.0
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
        g_rr_helix[idx] = 1.0 + 1.0 * lk_corr[idx] * rho[idx]  # MAXIMUM COUPLING
        gamma[idx] = min(rho[idx] / (rho[idx] + 1e2), 0.999)

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
    'version': 'monty_python_unreasonable',
    'tagline': 'The Unreasonable Universe',
    'mass_solar': 1000000,
    'rs_m': float(RS),
    'shell_width_m': float(R_MAX - R_MIN),
    'n_hopf_pairs': N_HOPF_PAIRS,
    'n_total_knots': int(len(knots)),
    'hopf_lk_mean': float(np.mean(hopf_lks)),
    'rho_max': float(np.max(rho)),
    'g_rr_helix_max': float(np.max(g_rr_helix)),
    'g_rr_helix_min': float(np.min(g_rr_helix)),
    'td_helix_min': float(np.min(td_helix)),
    'deviation_max': float(np.max(deviation)),
    'wall_time_s': float(time.time() - t_start),
    'notes': [
        "What if we took every absurd parameter and pushed it?",
        "1 million solar masses = Event Horizon larger than Earth's orbit",
        "Knots packed inside the shell like sardines",
        "Coupling alpha = 1.0 (no ashamed physics here)",
        "'Tis but a scratch!' — the metric"
    ]
}

with open(os.path.join(OUT_DIR, 'summary.json'), 'w') as f:
    json.dump(summary, f, indent=2)

print("DONE")
print()
print(json.dumps(summary, indent=2))
print()
print("'I fart in your general direction!' — the black hole")

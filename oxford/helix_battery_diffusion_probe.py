#!/usr/bin/env python3
"""
================================================================================
HELIX BATTERY — LONG-HORIZON DIFFUSION BOTTLENECK PROBE
================================================================================
Designed for: E16ads_v7 (128 GB RAM, high core count)
Purpose: Test geometric healing under severe diffusion limitation
         (D_Li = 5e-16 to 1e-15 m^2/s, simulating cold-weather / high-tortuosity)

Run:
    $ nohup python3 helix_battery_diffusion_probe.py > run.log 2>&1 &
    $ tail -f run.log

Expected wall time: 10–30 minutes depending on cores and N_SITES
================================================================================
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import csv
import time
import os
import json

# ==============================================================================
# CONFIGURATION — SEVERE DIFFUSION BOTTLENECK
# ==============================================================================

# Physical parameters (Li-ion graphite anode, cold-weather / low-D regime)
FARADAY      = 96485.33212
GAS_CONST    = 8.314462618
TEMP         = 298.15
ALPHA_A      = 0.5
ALPHA_C      = 0.5
N_ELECTRONS  = 1
J0           = 0.8              # [A/m^2]
C_MAX        = 305.0            # [mol/m^3]
L_ELECTRODE  = 80e-6            # [m] thicker electrode for diffusion-limited regime
R_SEI        = 8.0              # [Ω·m^2]
I_1C         = 20.0
C_RATE       = 4.0              # 4C — aggressive but realistic

# --- SPATIAL ---
N_SITES      = 50               # finer grid for boundary layer resolution
DX           = L_ELECTRODE / (N_SITES - 1)
X_UM         = np.linspace(0, L_ELECTRODE * 1e6, N_SITES)

# --- TOPOLOGICAL GOVERNOR ---
F_HEARTBEAT  = 300.0
T_HEARTBEAT  = 1.0 / F_HEARTBEAT
OMEGA        = 2 * np.pi * F_HEARTBEAT
ENVELOPE_CYCLES = 8
T_ENVELOPE   = ENVELOPE_CYCLES * T_HEARTBEAT
PHASE_DUR    = T_ENVELOPE / 4.0
PHASE_PRIMES = [2, 3, 5]
PHASE_WEIGHTS = np.log(PHASE_PRIMES)
PHASE_WEIGHTS = PHASE_WEIGHTS / np.max(PHASE_WEIGHTS)
GAMMA_CRIT   = 1.0 / 3.0
DRIFT_THRESH = 0.17

# --- DENDRITE MODEL ---
J_DENDRITE_THRESH = 2.5 * I_1C
RISK_GROWTH_RATE  = 2.0
RISK_DECAY_RATE   = 0.05
RESET_DAMPING     = 0.05
SOC_HOMOGENIZE    = 0.3

# --- TIME ---
DT           = 2e-5             # 20 µs — resolves 300 Hz + transients
T_TOTAL      = 400.0            # 400 s — long enough for surface pile-up
N_STEPS      = int(T_TOTAL / DT)
SAVE_EVERY   = 500              # save every 10 ms to disk

# --- DIFFUSIVITY SWEEP ---
D_LI_VALUES  = [5e-15, 1e-15, 5e-16, 1e-16]  # m^2/s

OUT_DIR      = "helix_diffusion_output"
os.makedirs(OUT_DIR, exist_ok=True)

print("=" * 70)
print("HELIX BATTERY — LONG-HORIZON DIFFUSION BOTTLENECK PROBE")
print("=" * 70)
print(f"Grid:        {N_SITES} sites × {N_STEPS:,} steps = {N_SITES * N_STEPS:,} updates")
print(f"Time step:   {DT*1e6:.0f} µs  |  Total: {T_TOTAL:.0f} s  |  Saves: {N_STEPS//SAVE_EVERY:,}")
print(f"C-rate:      {C_RATE}C  |  Current: {I_1C * C_RATE:.1f} A/m²")
print(f"Heartbeat:   {F_HEARTBEAT} Hz  |  Envelope: {T_ENVELOPE*1e3:.2f} ms")
print(f"D_Li sweep:  {[f"{d:.0e}" for d in D_LI_VALUES]}")
print(f"RAM est:     ~{(N_SITES * N_STEPS * 8 * 6) / (1024**3):.2f} GB (float64)")
print("=" * 70)


# ==============================================================================
# PRE-COMPUTE ENVELOPE (vectorized)
# ==============================================================================

t_vec = np.arange(N_STEPS) * DT
t_mod_vec = t_vec % T_ENVELOPE
pidx_vec = np.minimum((t_mod_vec // PHASE_DUR).astype(int), 3)
env_vec = np.zeros(N_STEPS)

for i in range(3):
    mask = pidx_vec == i
    ps = i * PHASE_DUR
    ramp = 0.5 * (1 - np.cos(np.pi * (t_mod_vec[mask] - ps) / PHASE_DUR))
    c, nxt = PHASE_WEIGHTS[i], PHASE_WEIGHTS[i] if i >= 2 else PHASE_WEIGHTS[i + 1]
    env_vec[mask] = c + (nxt - c) * ramp
env_vec[pidx_vec == 3] = 1.0
is_reset_vec = (pidx_vec == 3) & (t_mod_vec > PHASE_DUR * 0.75)

V_helix_vec = (0.035 + 0.025 * env_vec) + 0.025 * env_vec * np.sin(OMEGA * t_vec)

print(f"Envelope pre-computed: {np.sum(is_reset_vec):,} Master Reset events")


def butler_volmer(eta):
    arg = N_ELECTRONS * FARADAY * eta / (GAS_CONST * TEMP)
    return J0 * (np.exp(ALPHA_A * arg) - np.exp(-ALPHA_C * arg))

def V_eq(soc):
    return 0.10 - 0.10 * soc


def run_simulation(D_LI, mode='standard'):
    """Run a single simulation. Returns metrics dict."""
    label = f"{'standard' if mode == 'standard' else 'helix'}_D{D_LI:.0e}"
    print(f"\n>>> Running {label} ...")
    t0 = time.time()

    soc = np.zeros((N_SITES, N_STEPS))
    soc[:, 0] = 0.15
    risk = np.zeros((N_SITES, N_STEPS))
    V_out = np.zeros(N_STEPS)

    # Pre-compute diffusion coefficient
    diff_coeff = D_LI * DT / (DX ** 2)

    for k in range(1, N_STEPS):
        if mode == 'standard':
            # Constant current, uniform overpotential
            eta = (GAS_CONST * TEMP / (N_ELECTRONS * FARADAY)) * np.arcsinh(I_1C * C_RATE / (2 * J0))
            j_loc = I_1C * C_RATE * np.ones(N_SITES)
            V_out[k] = V_eq(np.mean(soc[:, k-1])) + eta + I_1C * C_RATE * R_SEI * 1e-4
        else:
            V_app = V_helix_vec[k]
            V_out[k] = V_app
            eta_loc = V_app - V_eq(soc[:, k-1]) - I_1C * C_RATE * R_SEI * 1e-4
            j_loc = butler_volmer(eta_loc)

        # Reaction source
        d_soc = (j_loc / (FARADAY * C_MAX)) * DT
        soc[:, k] = soc[:, k-1] + d_soc
        soc[:, k] = np.clip(soc[:, k], 0.001, 0.999)

        # Diffusion (Crank-Nicolson-ish explicit step)
        tmp = soc[:, k].copy()
        if N_SITES > 2:
            # No-flux at x=0, Dirichlet-like at x=L (simplified)
            soc[0, k]    = tmp[0]    + diff_coeff * (tmp[1] - tmp[0])
            soc[-1, k]   = tmp[-1]   + diff_coeff * (tmp[-2] - tmp[-1])
            soc[1:-1, k] = tmp[1:-1] + diff_coeff * (tmp[2:] - 2*tmp[1:-1] + tmp[:-2])

        # Dendrite risk
        gamma = 1.0 - soc[:, k]
        risk_inc = np.where(
            (np.abs(j_loc) > J_DENDRITE_THRESH) & (gamma > DRIFT_THRESH),
            RISK_GROWTH_RATE * (np.abs(j_loc) / J_DENDRITE_THRESH) * (gamma / GAMMA_CRIT) * DT,
            0.0
        )
        risk[:, k] = risk[:, k-1] + risk_inc - RISK_DECAY_RATE * risk[:, k-1] * DT
        risk[:, k] = np.clip(risk[:, k], 0, None)

        # Master Reset
        if mode == 'helix' and is_reset_vec[k]:
            soc_mean = np.mean(soc[:, k])
            soc[:, k] = (1 - SOC_HOMOGENIZE) * soc[:, k] + SOC_HOMOGENIZE * soc_mean
            risk[:, k] *= RESET_DAMPING

    elapsed = time.time() - t0
    print(f"    Done in {elapsed:.1f}s")

    # Metrics
    avg_soc = np.mean(soc, axis=0)
    max_risk_t = np.max(risk, axis=0)
    final_soc = avg_soc[-1] * 100
    max_risk = np.max(max_risk_t)
    final_risk_surf = risk[-1, -1]
    dc = np.max(soc[:, -1]) - np.min(soc[:, -1])
    max_gamma = np.max(1.0 - soc[:, -1])

    # Save time series (downsampled)
    csv_path = os.path.join(OUT_DIR, f"{label}_ts.csv")
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "avg_soc", "max_risk", "V_mV", "phase"])
        for k in range(0, N_STEPS, SAVE_EVERY):
            ph = pidx_vec[k] if mode == 'helix' else -1
            writer.writerow([f"{t_vec[k]:.4f}", f"{avg_soc[k]*100:.4f}",
                             f"{max_risk_t[k]:.6f}", f"{V_out[k]*1000:.4f}", ph])

    # Save final spatial profile
    prof_path = os.path.join(OUT_DIR, f"{label}_profile.csv")
    with open(prof_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["x_um", "soc", "gamma", "risk"])
        for i in range(N_SITES):
            writer.writerow([f"{X_UM[i]:.2f}", f"{soc[i,-1]:.6f}",
                             f"{1.0-soc[i,-1]:.6f}", f"{risk[i,-1]:.6f}"])

    return {
        'label': label,
        'mode': mode,
        'D_Li': D_LI,
        'final_soc_pct': final_soc,
        'max_risk': max_risk,
        'final_risk_surface': final_risk_surf,
        'delta_c': dc,
        'max_gamma': max_gamma,
        'wall_time_s': elapsed
    }


# ==============================================================================
# RUN SWEEP
# ==============================================================================

results = []

for D_LI in D_LI_VALUES:
    # Standard
    res_std = run_simulation(D_LI, mode='standard')
    results.append(res_std)

    # Helix
    res_helix = run_simulation(D_LI, mode='helix')
    results.append(res_helix)

# ==============================================================================
# SUMMARY TABLE
# ==============================================================================

print("\n" + "=" * 90)
print("DIFFUSION BOTTLENECK SWEEP — SUMMARY")
print("=" * 90)
print(f"{'D_Li':>12} {'Mode':>10} {'Final SOC':>10} {'Max Risk':>12} {'R_surf':>12} {'Δc':>10} {'Max γ':>8} {'Time':>8}")
print("-" * 90)
for r in results:
    print(f"{r['D_Li']:>12.0e} {r['mode']:>10} {r['final_soc_pct']:>9.2f}% {r['max_risk']:>12.4f} "
          f"{r['final_risk_surface']:>12.4f} {r['delta_c']:>10.6f} {r['max_gamma']:>8.4f} {r['wall_time_s']:>7.1f}s")
print("=" * 90)

# Save JSON summary
json_path = os.path.join(OUT_DIR, "diffusion_sweep_summary.json")
with open(json_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nJSON summary: {json_path}")

# ==============================================================================
# PLOTTING
# ==============================================================================

print("\nGenerating plots...")

fig = plt.figure(figsize=(18, 14))

# Panel 1: Max Risk vs D_Li
ax1 = fig.add_subplot(2, 3, 1)
D_vals = np.array(D_LI_VALUES)
std_risks = [r['max_risk'] for r in results if r['mode'] == 'standard']
helix_risks = [r['max_risk'] for r in results if r['mode'] == 'helix']
ax1.semilogx(D_vals, std_risks, 'bo-', lw=2, ms=10, label='Standard')
ax1.semilogx(D_vals, helix_risks, 'rs-', lw=2, ms=10, label='Helix 300 Hz')
ax1.set_xlabel('D_Li [m²/s]')
ax1.set_ylabel('Max Dendrite Risk')
ax1.set_title('Max Risk vs Diffusivity')
ax1.legend(fontsize=11)
ax1.grid(True, alpha=0.3)

# Panel 2: Δc vs D_Li
ax2 = fig.add_subplot(2, 3, 2)
std_dc = [r['delta_c'] for r in results if r['mode'] == 'standard']
helix_dc = [r['delta_c'] for r in results if r['mode'] == 'helix']
ax2.semilogx(D_vals, std_dc, 'bo-', lw=2, ms=10, label='Standard')
ax2.semilogx(D_vals, helix_dc, 'rs-', lw=2, ms=10, label='Helix')
ax2.set_xlabel('D_Li [m²/s]')
ax2.set_ylabel('Δc / c_max')
ax2.set_title('Concentration Uniformity vs Diffusivity')
ax2.legend(fontsize=11)
ax2.grid(True, alpha=0.3)

# Panel 3: Final SOC vs D_Li
ax3 = fig.add_subplot(2, 3, 3)
std_soc = [r['final_soc_pct'] for r in results if r['mode'] == 'standard']
helix_soc = [r['final_soc_pct'] for r in results if r['mode'] == 'helix']
ax3.semilogx(D_vals, std_soc, 'bo-', lw=2, ms=10, label='Standard')
ax3.semilogx(D_vals, helix_soc, 'rs-', lw=2, ms=10, label='Helix')
ax3.set_xlabel('D_Li [m²/s]')
ax3.set_ylabel('Final SOC [%]')
ax3.set_title('Charge Efficiency vs Diffusivity')
ax3.legend(fontsize=11)
ax3.grid(True, alpha=0.3)

# Panels 4-6: Spatial profiles for most severe D (1e-16)
D_worst = 1e-16
std_prof_file = os.path.join(OUT_DIR, f"standard_D{D_worst:.0e}_profile.csv")
helix_prof_file = os.path.join(OUT_DIR, f"helix_D{D_worst:.0e}_profile.csv")

if os.path.exists(std_prof_file) and os.path.exists(helix_prof_file):
    std_prof = np.loadtxt(std_prof_file, delimiter=',', skiprows=1)
    helix_prof = np.loadtxt(helix_prof_file, delimiter=',', skiprows=1)

    ax4 = fig.add_subplot(2, 3, 4)
    ax4.plot(std_prof[:,0], std_prof[:,1]*100, 'b-', lw=2, label='Standard')
    ax4.plot(helix_prof[:,0], helix_prof[:,1]*100, 'r-', lw=2, label='Helix')
    ax4.set_xlabel('Depth [μm]')
    ax4.set_ylabel('SOC [%]')
    ax4.set_title(f'SOC Profile @ D={D_worst:.0e} m²/s')
    ax4.legend(); ax4.grid(True, alpha=0.3)

    ax5 = fig.add_subplot(2, 3, 5)
    ax5.plot(std_prof[:,0], std_prof[:,2], 'b-', lw=2, label='Standard')
    ax5.plot(helix_prof[:,0], helix_prof[:,2], 'r-', lw=2, label='Helix')
    ax5.set_xlabel('Depth [μm]')
    ax5.set_ylabel('γ (shear)')
    ax5.set_title(f'Shear Profile @ D={D_worst:.0e} m²/s')
    ax5.legend(); ax5.grid(True, alpha=0.3)

    ax6 = fig.add_subplot(2, 3, 6)
    ax6.plot(std_prof[:,0], std_prof[:,3], 'b-', lw=2, label='Standard')
    ax6.plot(helix_prof[:,0], helix_prof[:,3], 'r-', lw=2, label='Helix')
    ax6.set_xlabel('Depth [μm]')
    ax6.set_ylabel('Dendrite Risk')
    ax6.set_title(f'Risk Profile @ D={D_worst:.0e} m²/s')
    ax6.legend(); ax6.grid(True, alpha=0.3)

plt.suptitle(
    'Diffusion Bottleneck Sweep: Standard vs Helix Topological (300 Hz + 4-Phase Master Reset)\n'
    f'4C Charge | {N_SITES}-Site 1D | T = {T_TOTAL:.0f}s | dt = {DT*1e6:.0f}µs',
    fontsize=13, fontweight='bold', y=0.995
)
plt.tight_layout(rect=[0, 0, 1, 0.99])

plot_path = os.path.join(OUT_DIR, "diffusion_sweep_summary.png")
plt.savefig(plot_path, dpi=200, bbox_inches='tight', facecolor='white')
plt.close()

print(f"Plot saved: {plot_path}")
print(f"\nAll outputs in: {os.path.abspath(OUT_DIR)}/")
print("\n" + "=" * 70)
print("DIFFUSION BOTTLENECK PROBE COMPLETE")
print("=" * 70)

#!/usr/bin/env python3
"""
Oxford Battery Hamiltonian — 1-D Continuum Electrode Model
Standard Butler-Volmer + diffusion  vs  Helix 300 Hz + Master-Reset

Implements local shear γ, dendrite-risk accumulator R, and Phase-4
homogenization. Designed for aggressive C-rate stress tests.

Stephen Hope / Bilal Khan / Helix Commonwealth
Draft v0.2 — continuum probe
"""

import numpy as np
from pathlib import Path
import csv
import time

# ---------------------------------------------------------------------------
# Physical / numerical parameters (order-of-magnitude Li-graphite)
# ---------------------------------------------------------------------------
F = 96485.0                 # C/mol
R_gas = 8.314               # J/(mol·K)
T = 298.15                  # K
alpha_a = 0.5
alpha_c = 0.5

L = 80e-6                   # electrode thickness 80 µm (more diffusion distance)
N = 51                      # spatial nodes
dx = L / (N - 1)
x = np.linspace(0.0, L, N)

c_max = 25000.0             # mol/m³  (approx graphite capacity density)
D_Li = 1.2e-14              # m²/s   solid diffusion (still slow relative to rate)
j0 = 8.0                    # A/m²   exchange current density
R_sei = 0.001               # Ω·m²   SEI resistance

gamma_crit = 0.17           # universal drift threshold
j_thresh = 5.0              # A/m²   local |j| above which risk can grow
k_grow = 12.0               # 1/s    risk growth rate scale
k_decay = 1.5               # 1/s    risk decay rate
alpha_reset = 0.35          # homogenization strength on Phase 4
beta_reset = 0.05           # risk annihilation factor on Phase 4

# ---------------------------------------------------------------------------
# Helix drive
# ---------------------------------------------------------------------------
def helix_modulation(t, f0=300.0):
    """300 Hz carrier + 4-phase ln-prime envelope. Returns factor ~[0.25, 1.6]."""
    carrier = np.sin(2 * np.pi * f0 * t)
    phi = 2 * np.pi * (f0 / 4.0) * t
    a2, a3, a5 = np.log(2), np.log(3), np.log(5)
    env = (a2 * (1 + np.sin(phi)) +
           a3 * (1 + np.sin(phi + 2 * np.pi / 3)) +
           a5 * (1 + np.sin(phi + 4 * np.pi / 3)))
    env = env / (a2 + a3 + a5)
    return 0.25 + 0.75 * env * (0.5 + 0.5 * carrier)


def is_phase4(t, f0=300.0, duty=0.18):
    """True during a fraction of each 4-phase cycle (Master Reset window)."""
    phase = (f0 * t) % 4.0
    return phase > (4.0 - 4.0 * duty)


# ---------------------------------------------------------------------------
# Butler-Volmer + equilibrium voltage (simple Nernst-like)
# ---------------------------------------------------------------------------
def V_eq(c, c_max=c_max):
    """Very simple SOC-dependent equilibrium (placeholder)."""
    soc = np.clip(c / c_max, 1e-4, 1 - 1e-4)
    # mild sloping open-circuit ~ 0.1 V swing
    return 0.10 * (0.5 - soc)


def butler_volmer(eta):
    return j0 * (np.exp(alpha_a * F * eta / (R_gas * T)) -
                 np.exp(-alpha_c * F * eta / (R_gas * T)))


# ---------------------------------------------------------------------------
# Core stepper (explicit, vectorized)
# ---------------------------------------------------------------------------
def step(c, R, V_app, I_app_density, dt, helix=False, t=0.0):
    """
    Advance concentration and risk by dt.
    I_app_density : A/m² (positive = intercalation into electrode)
    """
    gamma = 1.0 - c / c_max

    # local overpotential (lumped ohmic + concentration + applied)
    eta = V_app - V_eq(c) - I_app_density * R_sei
    # concentration overpotential proxy
    eta = eta - 0.02 * (c / c_max - 0.5)

    j = butler_volmer(eta)          # A/m²  (positive = oxidation / de-intercalation)

    # Helix modulation of the faradaic drive
    if helix:
        mod = helix_modulation(t)
        j = j * mod
        # applied current also feels the envelope
        I_eff = I_app_density * mod
    else:
        I_eff = I_app_density

    # diffusion (central differences)
    d2c = np.zeros_like(c)
    d2c[1:-1] = (c[2:] - 2 * c[1:-1] + c[:-2]) / dx**2
    # Neumann (no flux) at current collector x=0
    d2c[0] = 2.0 * (c[1] - c[0]) / dx**2
    # Neumann at electrolyte interface (flux handled by surface source)
    d2c[-1] = 2.0 * (c[-2] - c[-1]) / dx**2

    # --- Strongly interface-localized intercalation ---
    # Reaction is treated as a surface flux at x=L, converted to a
    # volumetric source only in the last few nodes. This makes low D
    # produce a real boundary layer.
    surface_weight = np.exp(-12.0 * (L - x) / L)   # very sharp at x→L
    surface_weight = surface_weight / (np.sum(surface_weight) * dx + 1e-30)

    # net source: charging (I_eff > 0) adds Li near the surface
    # j_BV contribution also weighted to the surface
    source = (I_eff - j) * surface_weight / (F * 0.25)

    c_new = c + dt * (D_Li * d2c + source)
    c_new = np.clip(c_new, 0.02 * c_max, 0.98 * c_max)

    # ----- dendrite risk (surface-weighted) -----
    # Risk grows preferentially where reaction is strong AND shear is high
    local_stress = (np.abs(j) / (j_thresh + 1e-12)) * (gamma / (gamma_crit + 1e-12))
    local_stress *= (surface_weight / (np.max(surface_weight) + 1e-30))  # surface emphasis
    grow_mask = local_stress > 1.0
    dR = np.where(grow_mask,
                  k_grow * local_stress,
                  -k_decay * R)
    R_new = np.maximum(R + dt * dR, 0.0)

    # ----- Master Reset (Phase 4) -----
    if helix and is_phase4(t):
        c_bar = np.mean(c_new)
        c_new = (1.0 - alpha_reset) * c_new + alpha_reset * c_bar
        R_new = beta_reset * R_new

    return c_new, R_new, gamma, j, eta


# ---------------------------------------------------------------------------
# Simulation driver
# ---------------------------------------------------------------------------
def run_electrode(t_end=8.0, C_rate=3.0, helix=False, dt=2e-5, record_every=50):
    """
    C_rate : multiples of 1C (1C ≈ full capacity in 1 hour).
    Capacity areal ~ c_max * L * F  →  rough current density scale.
    """
    # 1C current density: full theoretical capacity in 1 hour
    Q_areal = c_max * L * F                 # C/m²
    I_1C = Q_areal / 3600.0                 # A/m²
    I_app = C_rate * I_1C * 0.08            # scale factor so 5C is stressing but stable

    c = np.full(N, 0.40 * c_max)            # start partially charged
    R = np.zeros(N)
    V_app = 0.055                           # charging bias

    n_steps = int(t_end / dt)
    n_rec = n_steps // record_every + 1

    hist = {
        "t": np.zeros(n_rec),
        "c_mean": np.zeros(n_rec),
        "c_surface": np.zeros(n_rec),
        "c_bulk": np.zeros(n_rec),
        "gamma_max": np.zeros(n_rec),
        "gamma_surface": np.zeros(n_rec),
        "R_max": np.zeros(n_rec),
        "R_surface": np.zeros(n_rec),
        "j_mean": np.zeros(n_rec),
    }

    rec = 0
    t0 = time.time()
    for k in range(n_steps):
        t = k * dt
        c, R, gamma, j, eta = step(c, R, V_app, I_app, dt, helix=helix, t=t)

        if k % record_every == 0 and rec < n_rec:
            hist["t"][rec] = t
            hist["c_mean"][rec] = np.mean(c)
            hist["c_surface"][rec] = c[-1]
            hist["c_bulk"][rec] = c[0]
            hist["gamma_max"][rec] = np.max(gamma)
            hist["gamma_surface"][rec] = gamma[-1]
            hist["R_max"][rec] = np.max(R)
            hist["R_surface"][rec] = R[-1]
            hist["j_mean"][rec] = np.mean(j)
            rec += 1

    elapsed = time.time() - t0
    # trim
    for key in hist:
        hist[key] = hist[key][:rec]
    hist["final_c"] = c.copy()
    hist["final_R"] = R.copy()
    hist["final_gamma"] = 1.0 - c / c_max
    hist["elapsed_s"] = elapsed
    hist["C_rate"] = C_rate
    hist["helix"] = helix
    return hist


def print_summary(h, label):
    print(f"\n{'='*60}")
    print(f"  {label}   |  C-rate = {h['C_rate']}C  |  helix={h['helix']}")
    print(f"{'='*60}")
    print(f"  sim time            : {h['t'][-1]:.2f} s   (wall {h['elapsed_s']:.1f}s)")
    print(f"  final c_mean / cmax : {h['c_mean'][-1]/c_max:.3f}")
    print(f"  final c_surface     : {h['c_surface'][-1]/c_max:.3f}")
    print(f"  final c_bulk        : {h['c_bulk'][-1]/c_max:.3f}")
    print(f"  max gamma reached   : {np.max(h['gamma_max']):.4f}")
    print(f"  final gamma_surface : {h['gamma_surface'][-1]:.4f}")
    print(f"  max R reached       : {np.max(h['R_max']):.4f}")
    print(f"  final R_surface     : {h['R_surface'][-1]:.4f}")
    print(f"  time gamma>0.17     : {100*np.mean(h['gamma_max']>gamma_crit):.1f} %")
    print(f"{'='*60}")


def write_timeseries(h, path):
    path = Path(path)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "c_mean", "c_surface", "c_bulk",
                    "gamma_max", "gamma_surface", "R_max", "R_surface", "j_mean"])
        for i in range(len(h["t"])):
            w.writerow([
                f"{h['t'][i]:.6f}",
                f"{h['c_mean'][i]:.6e}",
                f"{h['c_surface'][i]:.6e}",
                f"{h['c_bulk'][i]:.6e}",
                f"{h['gamma_max'][i]:.6f}",
                f"{h['gamma_surface'][i]:.6f}",
                f"{h['R_max'][i]:.6f}",
                f"{h['R_surface'][i]:.6f}",
                f"{h['j_mean'][i]:.6e}",
            ])
    print(f"  wrote {path}")


def write_profile(h, path):
    path = Path(path)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["x_um", "c", "gamma", "R"])
        for i in range(N):
            w.writerow([
                f"{x[i]*1e6:.3f}",
                f"{h['final_c'][i]:.6e}",
                f"{h['final_gamma'][i]:.6f}",
                f"{h['final_R'][i]:.6f}",
            ])
    print(f"  wrote {path}")


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    outdir = Path("/home/workdir/artifacts")
    C_RATE = 5.0          # aggressive stress
    T_END = 12.0          # seconds of simulated electrode time

    print("Oxford Battery 1-D Continuum — Standard vs Helix")
    print(f"N={N}, L={L*1e6:.0f} µm, D_Li={D_Li:.1e}, C_rate={C_RATE}")

    print("\n[1/2] Standard (no Helix drive) ...")
    h_std = run_electrode(t_end=T_END, C_rate=C_RATE, helix=False, dt=2.0e-5, record_every=40)
    print_summary(h_std, "STANDARD")
    write_timeseries(h_std, outdir / "oxford_1d_standard_ts.csv")
    write_profile(h_std, outdir / "oxford_1d_standard_profile.csv")

    print("\n[2/2] Helix (300 Hz + Master Reset) ...")
    h_hel = run_electrode(t_end=T_END, C_rate=C_RATE, helix=True, dt=2.0e-5, record_every=40)
    print_summary(h_hel, "HELIX")
    write_timeseries(h_hel, outdir / "oxford_1d_helix_ts.csv")
    write_profile(h_hel, outdir / "oxford_1d_helix_profile.csv")

    # quick separation metrics
    print("\n" + "="*60)
    print("  SEPARATION METRICS (Standard vs Helix)")
    print("="*60)
    print(f"  Δ max_R          : {np.max(h_std['R_max']) - np.max(h_hel['R_max']):.4f}")
    print(f"  Δ final R_surf   : {h_std['R_surface'][-1] - h_hel['R_surface'][-1]:.4f}")
    print(f"  Δ max gamma      : {np.max(h_std['gamma_max']) - np.max(h_hel['gamma_max']):.4f}")
    print(f"  surface-bulk Δc  (std) : {(h_std['c_surface'][-1]-h_std['c_bulk'][-1])/c_max:.4f}")
    print(f"  surface-bulk Δc  (hel) : {(h_hel['c_surface'][-1]-h_hel['c_bulk'][-1])/c_max:.4f}")
    print("="*60)
    print("Note: parameters are order-of-magnitude. Real graphite kinetics,")
    print("concentration-dependent D, and full SEI models will change numbers.")
    print("The structural question is whether the Master Reset flattens gradients")
    print("and annihilates risk before nucleation — that is what this probe tests.")
    print("="*60)

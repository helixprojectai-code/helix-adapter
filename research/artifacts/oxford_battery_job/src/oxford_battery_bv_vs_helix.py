#!/usr/bin/env python3
"""
Oxford Battery Hamiltonian — Preliminary Simulation
300 Hz Constitutional Heartbeat + 4-phase envelope vs classical Butler-Volmer

Stephen Hope / Bilal Khan / Helix Commonwealth
Draft v0.1 — numerical probe only. Not a full FEM or SPICE netlist.
"""

import numpy as np
from scipy.integrate import solve_ivp
import csv
from pathlib import Path

# ---------------------------------------------------------------------------
# Physical constants (SI)
# ---------------------------------------------------------------------------
F = 96485.3321          # Faraday constant C/mol
R = 8.314462618         # Gas constant J/(mol·K)
T = 298.15              # Temperature K
alpha_a = 0.5           # Anodic transfer coefficient
alpha_c = 0.5           # Cathodic transfer coefficient
i0 = 1.0e-3             # Exchange current density A/m² (order-of-magnitude Li)
C_dl = 0.2              # Double-layer capacitance F/m² (typical)

# ---------------------------------------------------------------------------
# Classical Butler-Volmer
# ---------------------------------------------------------------------------
def butler_volmer(eta, i0=i0, alpha_a=alpha_a, alpha_c=alpha_c, T=T):
    """Current density (A/m²) for overpotential eta (V)."""
    return i0 * (np.exp(alpha_a * F * eta / (R * T)) -
                 np.exp(-alpha_c * F * eta / (R * T)))

# ---------------------------------------------------------------------------
# Helix 4-phase + 300 Hz envelope
# ---------------------------------------------------------------------------
def helix_pulse_envelope(t, f0=300.0):
    """
    300 Hz carrier + 4-phase prime-indexed amplitude modulation.
    Phases keyed to ln(2), ln(3), ln(5) relative amplitudes.
    Returns dimensionless modulation factor in [0.2, 1.8].
    """
    carrier = np.sin(2 * np.pi * f0 * t)
    # slow 4-phase envelope (period ~ 1/75 s so 4 beats per 300 Hz cycle group)
    phi = 2 * np.pi * (f0 / 4) * t
    a2 = np.log(2)
    a3 = np.log(3)
    a5 = np.log(5)
    env = (a2 * (1 + np.sin(phi)) +
           a3 * (1 + np.sin(phi + 2*np.pi/3)) +
           a5 * (1 + np.sin(phi + 4*np.pi/3)))
    env = env / (a2 + a3 + a5)          # normalize ~ [0, 2]
    return 0.3 + 0.7 * env * (0.5 + 0.5 * carrier)   # keep positive drive

def helix_overpotential(t, eta0=0.05, amp=0.03):
    """Base overpotential + Helix-modulated AC component."""
    return eta0 + amp * (helix_pulse_envelope(t) - 1.0)

# ---------------------------------------------------------------------------
# Simple RC + Faradaic model (lumped)
#   C_dl * dV/dt = i_app - i_BV(V)
#   eta ≈ V (reference chosen so equilibrium is zero)
# ---------------------------------------------------------------------------
def classical_ode(t, y, i_app):
    eta = y[0]
    i_f = butler_volmer(eta)
    d_eta = (i_app - i_f) / C_dl
    return [d_eta]

def helix_ode(t, y, i_app_base):
    eta = y[0]
    # instantaneous applied current is modulated
    mod = helix_pulse_envelope(t)
    i_app = i_app_base * mod
    i_f = butler_volmer(eta)
    d_eta = (i_app - i_f) / C_dl
    return [d_eta]

# ---------------------------------------------------------------------------
# Run comparison
# ---------------------------------------------------------------------------
def run_comparison(t_end=0.05, i_app=0.005, n_points=5000):
    t_eval = np.linspace(0, t_end, n_points)

    # Classical constant-current drive
    sol_c = solve_ivp(classical_ode, [0, t_end], [0.0],
                      args=(i_app,), t_eval=t_eval, rtol=1e-7, atol=1e-9)

    # Helix-modulated drive (same average current scale)
    sol_h = solve_ivp(helix_ode, [0, t_end], [0.0],
                      args=(i_app,), t_eval=t_eval, rtol=1e-7, atol=1e-9)

    eta_c = sol_c.y[0]
    eta_h = sol_h.y[0]
    i_c = butler_volmer(eta_c)
    i_h = butler_volmer(eta_h)

    # simple gamma proxy: normalized |eta| departure (toy)
    gamma_c = np.clip(np.abs(eta_c) / 0.2, 0, 1)
    gamma_h = np.clip(np.abs(eta_h) / 0.2, 0, 1)

    return {
        "t": t_eval,
        "eta_classical": eta_c,
        "eta_helix": eta_h,
        "i_classical": i_c,
        "i_helix": i_h,
        "gamma_classical": gamma_c,
        "gamma_helix": gamma_h,
        "mod": helix_pulse_envelope(t_eval),
    }

# ---------------------------------------------------------------------------
# Metrics + CSV export
# ---------------------------------------------------------------------------
def summarize(res):
    print("=" * 60)
    print("Oxford Battery — Butler-Volmer vs Helix 300 Hz Pulse")
    print("=" * 60)
    print(f"Time window          : {res['t'][-1]*1e3:.1f} ms")
    print(f"Classical mean |eta| : {np.mean(np.abs(res['eta_classical']))*1e3:.3f} mV")
    print(f"Helix mean |eta|     : {np.mean(np.abs(res['eta_helix']))*1e3:.3f} mV")
    print(f"Classical mean |i|   : {np.mean(np.abs(res['i_classical']))*1e3:.4f} mA/m²")
    print(f"Helix mean |i|       : {np.mean(np.abs(res['i_helix']))*1e3:.4f} mA/m²")
    print(f"Classical max gamma  : {np.max(res['gamma_classical']):.4f}")
    print(f"Helix max gamma      : {np.max(res['gamma_helix']):.4f}")
    print(f"Classical gamma>0.17 : {np.mean(res['gamma_classical'] > 0.17)*100:.1f} % of time")
    print(f"Helix gamma>0.17     : {np.mean(res['gamma_helix'] > 0.17)*100:.1f} % of time")
    print("=" * 60)
    print("Note: gamma here is a toy proxy (normalized |eta|). Real SOC/topology")
    print("mapping requires the full electrode lattice model.")
    print("=" * 60)

def write_csv(res, path):
    path = Path(path)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "eta_classical_V", "eta_helix_V",
                    "i_classical_A_m2", "i_helix_A_m2",
                    "gamma_classical", "gamma_helix", "modulation"])
        for i in range(len(res["t"])):
            w.writerow([
                f"{res['t'][i]:.8e}",
                f"{res['eta_classical'][i]:.8e}",
                f"{res['eta_helix'][i]:.8e}",
                f"{res['i_classical'][i]:.8e}",
                f"{res['i_helix'][i]:.8e}",
                f"{res['gamma_classical'][i]:.6f}",
                f"{res['gamma_helix'][i]:.6f}",
                f"{res['mod'][i]:.6f}",
            ])
    print(f"Wrote {path}")

if __name__ == "__main__":
    res = run_comparison(t_end=0.04, i_app=0.008, n_points=4000)
    summarize(res)
    out = Path("/home/workdir/artifacts/oxford_battery_bv_vs_helix.csv")
    write_csv(res, out)

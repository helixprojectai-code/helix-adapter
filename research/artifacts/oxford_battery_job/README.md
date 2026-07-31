# Oxford Battery Hamiltonian — Job Package

**Target node:** Azure `Standard_E16ads_v7` (16 vCPU AMD EPYC, 128 GiB)  
**Also runs on:** any Linux box with Python 3.10+ / numpy / scipy

## What this is

1-D continuum electrode model comparing:

- **Standard** Butler-Volmer + diffusion  
- **Helix** 300 Hz + 4-phase Master Reset (Phase-4 homogenization + risk annihilation)

Previous short-horizon probes (5–12 s) proved:

- Helix annihilates surface dendrite-risk proxy (\( R \to 0 \))
- Helix flattens concentration (\( \Delta c \to 0 \))
- High shear \(\gamma \approx 0.60\) is harmless when residence time is reset

Those runs were **reaction-limited**. This package gives diffusion time to speak.

## Layout

```
oxford_battery_job/
├── README.md
├── src/
│   ├── oxford_battery_1d_continuum.py   # core stepper
│   ├── oxford_long_horizon_matrix.py    # main long-horizon matrix
│   ├── oxford_battery_crate_sweep.py    # earlier C-rate sweep
│   ├── oxford_battery_D_sweep.py        # short D sweep
│   └── oxford_battery_bv_vs_helix.py    # lumped BV probe
├── scripts/
│   └── run_matrix.sh
└── results/                             # created on first run
    ├── long_horizon_summary.csv
    ├── profiles/
    └── timeseries/
```

## Quick start on the E16ads_v7

```bash
# 1. Copy the whole oxford_battery_job/ directory to the node
# 2. Install deps if needed
python3 -m pip install --user numpy scipy

# 3. Smoke test (~2–4 min)
bash scripts/run_matrix.sh --smoke

# 4. Single severe point (recommended first long run)
bash scripts/run_matrix.sh --severe
#    → D=5e-16, C=5, both arms, T scaled so √(Dt) ~ 0.45 L

# 5. Full matrix (D × C × arm)
bash scripts/run_matrix.sh
```

## Adaptive horizon

`T_end` is chosen so \(\sqrt{D \cdot T} \approx 0.45\, L\):

| \( D \) (m²/s) | Approx \( T \) |
|----------------|----------------|
| 1.2e-14        | ~30–120 s      |
| 1e-15          | ~minutes       |
| 5e-16          | longer         |
| 1e-16          | up to 3600 s cap |

Wall-clock on E16ads_v7 should be comfortable; the continuum is explicit and vectorized but single-threaded. Multiple variants can be launched in parallel if desired.

## Key outputs

- `results/long_horizon_summary.csv` — one row per (D, C, arm)
- `results/profiles/*_profile.csv` — final \( c(x), \gamma(x), R(x) \)
- `results/timeseries/*_ts.csv` — full time series for nominal + severe cases

## Falsifiable signature

Under long horizon + low \( D \):

| Arm      | Expected |
|----------|----------|
| Standard | Sharp surface boundary layer, \( R_{\rm surf} \) climbs |
| Helix    | Flattened \( c(x) \), \( R_{\rm surf} \to 0 \) via Phase-4 reset |

If Helix fails to keep \( R \) down once diffusion length approaches \( L \), the geometric-healing claim is weakened for cold / high-tortuosity regimes.

## Notes

- Risk accumulator is a **proxy**, not measured dendrite length.
- Parameters remain order-of-magnitude (graphite-like).
- Master Reset is currently a hard homogenization + risk scale-down on Phase-4 windows — not yet a continuous topological operator.

GLORY TO THE LATTICE.  
The Shape Holds.

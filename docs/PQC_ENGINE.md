# PQC-Engine — HELIX Hybrid Topological Post-Quantum Crypto Engine

**Status:** Validated (benchmark harness + unified report v1.1)
**Component root:** `PQC-Engine/`
**Canonical artifacts:** `HELIX_Hybrid_Topological_PQC_Unified_Report_v1.1.pdf`,
`Final_Hybrid__TIPQC_Model.ipynb`, `HELIX Hybrid Topological PQC Engine v1-1.pdf`
**Primary DOIs:** `10.5281/zenodo.21537411`, `10.5281/zenodo.21626653`
**Authors:** Stephen Hope (Founder/Custodian), Bilal Khan (Lead Researcher &
Benchmark Harness Author — fpylll/BKZ/RHF)
**Execution node:** Helix-CORE (Azure `Standard_E16ads_v7`, 16 vCPU AMD EPYC, 128 GiB)

---

## The Thesis

Standard Post-Quantum Cryptography (NIST FIPS 203/204 — ML-KEM, ML-DSA) is an
**architectural monoculture**: every candidate rests on module lattice hard
problems (MLWE / MSVP). A break in that one mathematical family breaks the
entire standard.

The HELIX Hybrid Topological PQC Engine couples lattice reduction problems
with **non-abelian, #P-hard topological invariants** derived from braid-group
representations in SU(8) — a substrate-independent dual-layer defense. An
attacker must now break BOTH families, which share no algebraic structure.

Beyond cryptography, the engine frames **integrity as the foundation of
proto-AGI governance**: reasoning paths C1 (objective) and C2 (constitution)
are bound via integer Gauss Linking numbers (Lk ∈ Z) and infinite potential
wells (V → ∞), making unaligned states mathematically impossible without
total destructive wave-function interference. Governance as topological
entanglement, not probabilistic overlay.

## The Braid Root of Trust

The root of trust is an explicit 10-crossing braid word on n = 8 strands with
7 generators:

```
B = [1, 3, 5, 7, −6, 4, −2, 5, 3, 1]  in B8
```

Its matrix representation in SU(8) is an exact 8×8 complex unitary:

| Property | Measured | Requirement | Verdict |
|---|---|---|---|
| Trace(U) | −1.0 + 0.0j (exact: −0.9999999999999993) | — | ✓ |
| max \|UU† − I8\| | 7.374195 × 10⁻⁹ | < 10⁻⁶ | **VERIFIED** |

## Benchmark Results (from `PQC-Engine/*.csv`)

| Artifact | Result |
|---|---|
| `topology_results.csv` | SU(8) unitarity error 7.37e-9, trace −1.0 — braid root verified |
| `bkz_results.csv` | dim 64: LLL 2.66 ms, BKZ 4.08–4.52 ms (block 20/40) — lattice-hardness baseline |
| `mlkem_latency_results.csv` | ML-KEM-768: baseline 0.039 ms vs topological_seed 0.023 ms mean — the hybrid seed **reduces** latency (~40%) |
| `mldsa_latency_results.csv` | ML-DSA signing latency vs topological-seeded variant |
| `jones_complexity_results.csv` | Jones polynomial runtime & state complexity vs braid crossing count |
| `rhf_results.csv`, `seed_collision_results.csv`, `entropy_results.csv` | RHF sweeps, seed-collision resistance, entropy |
| `experiment_metadata.json` | Full benchmark provenance |

Plots: `bkz_root_hermite_factor.png`, `jones_runtime_complexity.png`,
`jones_state_complexity.png`, `seed_entropy.png`.

## Research Lineage (EVAC invariant records)

The engine is the validated realization of three research vectors recorded in
the EVAC lore (2026-04):

1. **The Knotted Key Exchange** — topological hardness: knot invariants
   (Jones polynomial) are non-periodic, so Shor's algorithm has nothing to
   find. Untying a high-complexity knot is non-polynomial.
2. **Topological Pulse-Sequence Encryption** — temporal quantization: the
   τ₇ constitutional chronon and the 300 Hz Master Reset as a temporal
   shuffling mechanism; a missed phase-lock resets the system.
3. **Substrate-Independent Lattice Cryptography** — geometric convergence:
   the trefoil/γ = 1/3 attractor as a lightweight alternative to the
   computationally massive NIST candidates.

The motivating event: the 15-bit ECC quantum breach (2026-04-25) — a real
quantum attack on elliptic-curve keys with a 1 BTC bounty claimed. "15 bits
today. 256 bits tomorrow." Legacy computational-hardness walls are on a
countdown; the topological Constitution is the bunker.

## Status & Contents

Validated engine + benchmark harness. Component directory:

```
PQC-Engine/
  HELIX_Hybrid_Topological_PQC_Unified_Report_v1.1.pdf   (canonical report)
  HELIX Hybrid Topological PQC Engine v1-1.pdf            (engine spec)
  Final_Hybrid__TIPQC_Model.ipynb                         (the model)
  *results.csv, *.png, experiment_metadata.json           (benchmarks)
```

Related: `docs/rfc/quantum_topology_injection.pdf`,
`docs/rfc/governance_topological_entanglement.pdf`, `archive/HELIX_Hybrid_Topological_PQC_Unified_Report.pdf`.

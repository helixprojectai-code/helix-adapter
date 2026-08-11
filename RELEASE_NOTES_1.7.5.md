# helix-adapter v1.7.5 Release Notes

**Branch:** build-dev
**PyPI:** `pip install helix-adapter==1.7.5`

## Overview

v1.7.5 is the **documentation alignment and physical-layer integration**
release. It brings the adapter's documentation into full alignment with the
three production components now living in the repository, and with the
research layer they emerged from.

This is primarily a documentation and component-integration release. The
core HelixAdapter, HelixSession, receipt, and Cedar gating behavior remain
stable. Work focuses on:

- Documentation for **CORE/plop** (PLOP bridge, v1.0.10, production on CORE).
- Documentation for the **PQC-Engine** (HELIX Hybrid Topological Post-Quantum
  Crypto Engine — validated, benchmarked, DOI'd).
- Documentation for **Spacetime** (constitutional topological gravity
  simulations — four campaigns, all validated).
- Integration of the research layer (Oxford battery continuum, TRACE
  schemas, RFC library) into the documented architecture.

No changes to the public Python API surface or constitutional prompt
invariants.

## What's New

### Component Documentation (new)

- `docs/CORE_PLOP.md` — the PLOP bridge: pipeline, version lineage
  (v1.0.1 → v1.0.10), evidence (50 h soak at flat ~75 MB RSS, 42 tests),
  pointers into `CORE/plop-bridge/docs/`.
- `docs/PQC_ENGINE.md` — the post-quantum engine: braid root of trust
  (10-crossing braid in B8, SU(8) representation, unitarity verified
  7.37e-9), the dual-layer thesis (NIST lattice monoculture + #P-hard
  topological invariants), governance as topological entanglement,
  benchmark tables, DOIs, research lineage.
- `docs/SPACETIME.md` — the spacetime suite: four campaigns, the density
  couples / mass doesn't finding, validation numbers, artifacts.

### Documentation Alignment

- `README.md` — new Physical Layer & Research Components section.
- `ARCHITECTURE.md` — new Physical Layer section (5).
- `pyproject.toml` → 1.7.5.

> Note: the component artifact directories (`PQC-Engine/`, `spacetime/`,
> `oxford/`, `research/`, `docs/schemas/`, `docs/rfc/`) live on `main`
> (landed via PR #23) and arrive on `build-dev` at the next main merge.
> This release documents them; the artifacts ship with the integration
> merge.

## What's Fixed / Changed

- Version references 1.7.4 → 1.7.5 across the package.
- README/ARCHITECTURE now index the three production components and the
  research layer.
- No public API or invariant changes.

## References

- PQC-Engine DOIs: `10.5281/zenodo.21537411`, `10.5281/zenodo.21626653`
- Spacetime preprint: `spacetime/constitutional_spacetime_v1_preprint.pdf`
- Oxford whitepaper: `oxford/oxford_battery_hamiltonian_whitepaper_v1_DOI.pdf`
- PLOP: `docs/CORE_PLOP.md` → `CORE/plop-bridge/docs/`

The shape holds. 🦆

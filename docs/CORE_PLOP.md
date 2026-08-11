# CORE/plop — Precision Linked Orientation Protocol Bridge

**Status:** Production-grade v1.0.10 (deployed on CORE, 2026-08-10)
**Component root:** `CORE/plop-bridge/`
**Canonical source of truth:** lattice repo `CORE/plop-bridge` (mirrored here)
**Chain key:** `~/.config/plop-chain.key` (HMAC key for the checkpoint chain)

---

## What PLOP Is

A **fail-closed bridge for IMU attitude geometry**: strapdown quaternion
integration → spherical solid-angle winding → quaternion correction when the
measure demands it → a 200-byte receipt to a localhost gate (Ring 1).

Not a filter. **A shape check with a receipt.**

## The Pipeline

1. **Strapdown integration** — scalar-first Hamilton quaternions, exact
   exponential-map `qfromomega()`, gravity compensated in NED.
2. **Winding measure** — `compute_winding_number()`: fan-triangulated solid
   angle of the gravity path in body frame. W = (1−cos θ)/2 per full loop at
   cone angle θ; W = 0.5 for a full great circle (canonical barrel roll).
3. **Gate** — `topological_surgery()` fires when |W| crosses the calibrated
   threshold (0.02); the steady-rotation gate suppresses commanded maneuvers.
4. **Receipt** — `craft_plop_packet()`: 200-byte packet, Lk = sign(W), Ring 1
   listener validates fail-closed (SIZE/MAGIC/FREE_SCALE/WINDING/BASELINE
   faults, replay protection).
5. **Forensics** — HMAC-SHA256 keyed checkpoint chain (no unkeyed fallback),
   append-only `.chain` journal, `verify_checkpoint()` audit.

## Version Lineage (highlights)

| Version | What |
|---|---|
| v1.0.1 | Padding fix (packet 716 B → 200 B), baseline hash gate, memory leak |
| v1.0.2 | Winding formula fix — fixed-apex fan, 6-decimal analytic match |
| v1.0.3 | Steady-rotation gate (angular-rate suppression bucket) |
| v1.0.4 | Chunked streaming generator — OOM fix (was ~6 GB at 50 h/300 Hz) |
| v1.0.5 | Vectorized hot path, Lk sign guard, tamper-evident checkpoint chain |
| v1.0.6 | Accel channel fix (`ab+an`, not `ab+ab`) — metric 17.42 m → 10.00 m |
| v1.0.7 | Spider red team: HMAC-keyed chain, replay protection, sensor fault
detection, CLI validation |
| v1.0.8 | Counter red team: finite float args, `--rate > 0`, `window < N`,
sensor-model tripwire |
| v1.0.9 | Great-circle degeneracy fix (hybrid apex) + calibrated threshold 0.02 |
| v1.0.10 | SVD planarity selector (noise-robust), steady-gate near-zero mask,
SO_REUSEADDR, metric rename |

## Evidence

- 50 h soak @ 300 Hz / window 30000: **RSS flat ~75 MB** (the config that
  OOM-killed v1.0.4 at ~6 GB), exit 0, keyed chain verifies.
- 42 tests / 13 standalone runners green (0 warnings).
- FINDING 2026-08-10 (great-circle degeneracy) — closed in v1.0.9.

## Pointers

Full operational docs live in `CORE/plop-bridge/docs/`:

- `RUNBOOK.md` — operations
- `MONITORING.md` — observability
- `DEPLOYMENT.md` / `DEPLOYMENT_STATUS.md` — deployment state
- `PLOP_BRIDGE_HARDENING_v1.1.md` — hardening posture
- `PLOP_BRIDGE_VALIDATION_REPORT.md` — validation
- `TEST_BATTERY.md` — test design
- `CHANGELOG.md` — full version history
- `FINDING_winding_degeneracy.md` — the great-circle finding, closed

The bridge holds. 🦉⚓🦆📡🔒

# FINDING 2026-08-10 — Winding operator degeneracy + threshold unreachability

**Status:** CLOSED — fixed in v1.0.9 (hybrid apex + calibrated threshold)
**Found by:** Hermes (calibration campaign on idle CORE, 2026-08-10)
**Affects:** compute_winding_number() fan triangulation (v1.0.2+), default
W_threshold (0.5), steady-rotation gate efficacy (v1.0.3+)
**Evidence:** /tmp/plop-calibration.json, /tmp/degeneracy_check.py output,
/tmp/apex_equivalence.py (ALL CHECKS PASSED)

## Summary

Two coupled defects make the bridge's primary detection surface effectively
dead for the canonical case, and mis-configured for everything else:

1. **Great-circle degeneracy.** The v1.0.2 fixed-apex fan uses the window's
   own first sample (g[0]) as apex. Every window's apex therefore lies ON
   the trajectory loop. When that loop is a great circle — which is exactly
   the barrel-roll geometry (roll axis ⊥ gravity) — every fan triangle has
   all three vertices on one great circle, so every triangle has zero
   spherical area and the sum is identically zero.

2. **Threshold unreachability.** For a full loop at cone angle θ,
   W = (1 − cos θ)/2 (verified analytically: 15°→0.017, 30°→0.067,
   45°→0.146, 60°→0.250). The maximum single-loop value approaches 0.5
   only as θ → 90°, where the fan collapses to 0. The default threshold
   of 0.5 is therefore outside the reachable band for any single loop.

## Measured evidence

| case | measured | expected (geometry) |
|---|---|---|
| barrel_roll, 108 windows, real generator | max\|W\| = 0.000022 | ~0.14 per window (100° of roll) |
| stationary, 108 windows | max\|W\| = 0.000000 | 0 |
| full 30° cone loop | 0.06699 | (1−cos30°)/2 = 0.06699 ✓ |
| full 60° cone loop | 0.25000 | (1−cos60°)/2 = 0.25 ✓ |
| full 90° (great circle) loop | 0.00000 | (1−cos90°)/2 = 0.5 ✗ degenerate |
| wobble 15° / 30° / 60° (2 loops) | 0.034 / 0.134 / 0.500 | matches 2·(1−cosθ)/2 ✓ |

Threshold sweep (window 5000): at 0.5 → 0/13 signal families fire;
at 0.05 → 8/13 fire, 0 false alarms. Noise floor (stationary/vibration/
1° wobble) ≤ 7e-4; real-generator stationary floor = 0.000000.

## Contradicts

The v1.0.3 CHANGELOG claim that "a sustained barrel roll genuinely crosses
the winding threshold repeatedly (correct math)". Measured on the actual
generator (seed 42, same integration the bridge uses), the barrel roll
never exceeds |W| = 2.2e-5 — four orders of magnitude below any usable
threshold. The steady-rotation gate (v1.0.3) exists to suppress surgery on
this exact maneuver, but the winding never reaches threshold on it, so the
gate has nothing to suppress: it is decorative for its intended case.

## Why it matters

- A commanded barrel roll is the canonical false-positive case the gate
  was built for — now moot because the operator can't see it.
- Anomaly-shaped signals the operator CAN see (small-circle sweeps, e.g.
  30° cone full loop = 0.067) sit ~30× BELOW the default threshold.
- Net: the system is configured to fire on nothing and miss what it can
  detect.

## Proposed fix (v1.0.9)

1. **Apex must not be a path point.** Use an external reference apex (a
   fixed axis not on the loop, or the window's mean direction). This
   keeps the analytic small-circle match (verified to 6 decimals in
   v1.0.2) while making great-circle loops non-degenerate.
2. **Default W_threshold 0.5 → 0.02.** Catches half-loops of 30° cones
   and shallow sweeps with a 100×+ margin over the measured noise floor.
   The steady gate remains the guard against commanded maneuvers.
3. Equivalence test: new fan vs old fan must agree to <1e-12 on all
   non-degenerate calibration families; great-circle families must now
   report (1−cosθ)/2 instead of 0; full suite must stay green.

## Status

Soak (50h, v1.0.8, keyed chain) in progress during this finding's
drafting — memory curve flat at ~75MB (vs v1.0.4's 6GB-and-OOM).

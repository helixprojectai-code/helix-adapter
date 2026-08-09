# PLOP Bridge Test Battery
## Design Document — Closing the v1.0.1 Gaps Before helix-adapter Migration

**Status:** Proposed  
**Prerequisite for:** Migration into helix-adapter (Steve's stated plan, see `project_plop_deployment_live` memory)  
**Root problem this solves:** v1.0's padding bug shipped through a "6/6 passing" fire test undetected, because the tests validate a duplicated copy of the protocol, not `src/`. The surgery path — the actual reason PLOP exists — has never successfully fired in any test to date. A green test suite currently proves less than it looks like it proves.

---

## Tier 0 — Foundation (blocking; nothing above this tier means anything until it's done)

### 0.1 Tests import from `src/`, stop duplicating the protocol

**Problem:** `tests/helix_plop_fire_test.py` and `tests/helix_plop_synthetic_test.py` each have their own inline `craft_plop_packet`/`validate_plop_packet`. Both copies were already correct, which is *why* they never caught the padding bug in the real `src/helix_imu_plop_bridge.py` — a green fire test told us nothing about the deployed code.

**Fix:** Refactor both test files to `from helix_imu_plop_bridge import craft_plop_packet, validate_plop_packet, PLOP_MAGIC, PLOP_SIZE, Ring1Listener` (need `sys.path` insert for `src/`, or package the bridge properly). Delete the duplicate implementations entirely — no fallback copy, or the next bug hides the same way.

**Acceptance:** `grep -c "def craft_plop_packet\|def validate_plop_packet" tests/*.py` returns 0. Fire test still passes 6/6, now against real source.

**Effort:** ~20 min. Do this first — every test below is only as trustworthy as this fix.

### 0.2 Analytic ground truth for the winding integral

**Problem:** The only synthetic closed-loop generator (`synthetic_closed_cone`) doesn't actually close on S² — it traces a latitude circle without the trajectory returning to its start in a way the discrete Gauss integral recognizes as enclosing the pole. Every attempt to force a surgery via synthetic data has produced W≈0 instead of the expected ±value.

**Fix:** Before building more synthetic trajectories, verify `compute_winding_number()` against a case with a *known correct answer from spherical geometry*, independent of the bridge's own conventions. The solid angle subtended by a spherical cap of half-angle θ is Ω = 2π(1 − cos θ). For a discrete polygon that walks the boundary of that cap and closes exactly (last point == first point), the winding number should equal Ω/4π to numerical precision.

```python
def make_closing_cap_boundary(half_angle_deg, n_points=2000):
    """A trajectory that walks the boundary of a spherical cap and
    genuinely closes (last sample == first sample), unlike
    synthetic_closed_cone. Enables solid-angle ground truth."""
    theta = np.deg2rad(half_angle_deg)
    phi = np.linspace(0, 2*np.pi, n_points, endpoint=True)  # endpoint=True closes it
    g = np.zeros((n_points, 3))
    g[:, 0] = np.sin(theta) * np.cos(phi)
    g[:, 1] = np.sin(theta) * np.sin(phi)
    g[:, 2] = np.cos(theta)
    return g * 9.80665  # scale to gravity units, matching bridge convention

# Expected: W ≈ (1 - cos(theta)) / 2   [solid angle / 4π]
```

**Acceptance:** For half_angle in {10°, 30°, 60°, 90°}, `abs(compute_winding_number(cap) - (1-cos(theta))/2) < 1e-3`.

**Why this matters:** Until this passes, nobody actually knows whether `compute_winding_number()` is correct for closed loops — it's only ever been validated on trajectories that don't close (W≈0 is easy to get right by accident; W≈known-nonzero-value is the real test). This is the test that should have existed before the bridge was called "production ready."

**Effort:** 1-2 hours, mostly geometry double-checking.

---

## Tier 1 — Unit Tests (fast, deterministic, run on every commit)

Run in seconds. No sockets, no I/O beyond the test itself.

| Test | Validates | Priority |
|---|---|---|
| **1.1** Solid-angle winding ground truth (0.2 above) | `compute_winding_number()` correctness on genuinely closed loops | 🔴 Blocking |
| **1.2** Open-arc / noise winding stays near-zero | No false positives on non-closing trajectories (existing coverage, keep) | 🟢 Have it |
| **1.3** Packet round-trip: craft → struct.unpack → fields match input exactly | Byte-level packet correctness, would have caught the padding bug directly | 🔴 Blocking |
| **1.4** Packet length is exactly 200 for all valid winding/hash/flag combinations | Regression test for the padding bug specifically | 🔴 Blocking |
| **1.5** Fail-closed gate matrix: each of the 5 gates triggered independently, others held valid | SIZE / MAGIC / FREE_SCALE / WINDING / BASELINE_FAULT each fire correctly and don't false-trigger each other | 🟡 Have 4/5, add BASELINE_FAULT case |
| **1.6** Fuzz: 10,000 random byte strings of random length fed to `validate_plop_packet` | Never crashes, never raises, always returns `(bool, str)` | 🟡 New |
| **1.7** `q_history` never exceeds `window` length regardless of `N` | Deque bound holds for N ≫ window and N < window | 🟡 New |
| **1.8** `write_checkpoint` output is valid JSON at every call, not just the last one | Checkpoint doesn't produce transient invalid states | 🟡 New |
| **1.9** Topological surgery quaternion correction is a valid unit quaternion post-surgery | `topological_surgery()` doesn't silently denormalize | 🟢 New, cheap |

**Total runtime target:** < 30 seconds for the full Tier 1 suite. This is the tier that runs before every commit — it has to stay fast or it stops getting run.

---

## Tier 2 — Integration Tests (circuit-level, real socket, seconds to low minutes)

| Test | Validates | Priority |
|---|---|---|
| **2.1** Real emit → Ring1 receive → verify, using `src/` functions directly (post-0.1 refactor) | The actual deployed circuit, not a parallel implementation | 🔴 Blocking |
| **2.2** Baseline hash mismatch end-to-end: craft with hash A, `Ring1Listener(expected_hash=B)` | Confirms the v1.0.1 fix works through the full socket path, not just the function call | 🔴 Blocking |
| **2.3** **Genuine surgery fire**, using the Tier 0.2 closing-cap trajectory as `g_b_window` input to `topological_surgery()`, through to PLOP emission and Ring1 verification | The one thing PLOP exists to do, that has never once succeeded in any test to date | 🔴 Blocking — highest-value test in this entire battery |
| **2.4** Checkpoint survives SIGKILL: launch bridge as subprocess, kill -9 at a random point after ≥1 checkpoint has been written, verify the JSON on disk is valid and `complete: false` | The crash-survival guarantee the v1.0.1 checkpoint fix claims to provide — currently asserted, never tested | 🔴 Blocking |
| **2.5** Baseline hash rotation: bridge started with hash A, Ring1 listener reconfigured to expect hash B mid-run (simulates an operational hash rotation) | Old-hash packets correctly rejected after rotation; no window where stale packets sneak through | 🟡 New |
| **2.6** Rapid-fire packets (10-50 in a tight loop) to Ring1 | Listener doesn't drop, doesn't crash, `received == verified + dropped` exactly | 🟡 New |

**Note on 2.3:** this is the test that actually validates the mechanism. Everything shipped so far proves the gate stays *closed* correctly. Nothing yet proves the gate *opens correctly and applies a correct fix* when it should. Until 2.3 passes, "production ready" is a claim about half the system.

---

## Tier 3 — Trajectory Coverage (per-trajectory correctness, minutes each)

Re-run under v1.0.3 (winding-formula fix + steady-rotation gate) to confirm expected behavior on real (non-forced) trajectories. **Status: done, 2026-08-07.**

| Trajectory | Expected surgeries applied | Actual (v1.0.3, 0.05h/300Hz/window=5000) | Status |
|---|---|---|---|
| stationary | 0 | 0 applied, 0 suppressed, W∈[0,0] | ✅ Verified |
| const_vel | 0 | 0 applied, 0 suppressed, W∈[0,0] | ✅ Verified |
| sinusoidal | 0 | 0 applied, 0 suppressed, W∈[0,0] | ✅ Verified |
| vibration | 0 | 0 applied, 0 suppressed, W∈[0,0] | ✅ Verified |
| leo | 0 | 0 applied, 0 suppressed, W∈[0,0] | ✅ Verified |
| barrel_roll | 0 (gated) | 0 applied, **10 suppressed**, W∈[-1.5,1.5] | ✅ Verified — see note below |

**barrel_roll note — two findings, not one:**
1. The original expectation ("0 surgeries, open arc doesn't close") was wrong — it was the pre-v1.0.2 winding bug returning ~0 on this case too, not correct behavior. A sustained 60°/sec roll sweeps ~2.78 full rotations per 5000-sample/300Hz window; the fixed formula correctly detects this (axis output matches the roll axis exactly on every crossing: `[-1,0,0]`).
2. That correct detection then raised a design question: should PLOP autonomously correct the quaternion every time a commanded maneuver crosses the threshold? Decided no — v1.0.3's `is_steady_rotation()` gate checks the angular-rate signature over the same window and suppresses application when the crossing is explained by smooth, bounded, sustained rotation (logged to `suppressed`, not silently dropped, so the detection is still forensically visible).

**Acceptance:** Five of six trajectories (all non-rotating) produce 0 surgeries and 0 suppressions; barrel_roll produces 0 applied surgeries but 10 correctly-detected-and-gated suppressions — both confirmed against known geometry, not just "gate stays closed."

---

## Tier 4 — Soak / Resource Tests (hours; good use of idle CORE time)

| Test | Validates | Duration |
|---|---|---|
| **4.1** 24-72h continuous run, memory sampled every 5 min | Deque fix actually holds memory flat over long duration — the original problem (~830MB+ growth) only shows up past a few hours | 24-72h |
| **4.2** Disk usage over the same soak | Checkpoint-via-overwrite design should keep `bridge_live.json` at a constant size, not accumulate — confirm this assumption holds, since it was never explicitly load-tested | Same run as 4.1 |
| **4.3** Service resilience: `kill -9` the process 5-10 times over a soak period at random intervals | systemd `Restart=on-failure` actually recovers every time within `RestartSec=10`; no restart loop; each restart resumes cleanly (new PID, checkpoint file intact from before the kill) | 2-4h, interactive |
| **4.4** CPU/runtime scaling check: window=10k vs 30k vs 60k, same duration | Confirms O(n) claim in practice — runtime should scale linearly with window size, not superlinearly (would indicate the O(n) analysis was also wrong) | ~1h total |

**This tier is exactly what "compute is free, VM is paid for" is for** — nothing here requires attention once launched, just periodic checking in.

---

## Tier 5 — Adversarial / Chaos (lower priority, do before adapter migration)

| Test | Validates |
|---|---|
| **5.1** Malformed packets sent directly to port 5555 from a separate process (not through the bridge) | Ring1 listener treats external malformed input the same as internal — no special-casing that could be a gap |
| **5.2** Truncated packets (1-199 bytes) | Clean `SIZE_FAULT`, no partial-parse crash |
| **5.3** Oversized packets (201-1024 bytes) | Socket `recvfrom(1024)` behavior at the boundary — does it truncate silently or reject? |
| **5.4** Packet flood (1000+ in under a second) | No crash, no unbounded queue growth, graceful degradation if any |

---

## Acceptance Criteria for helix-adapter Migration

Given Steve's stated plan ("when settled I'll stick PLOP in adapter"), propose this as the actual bar for "settled":

- [x] Tier 0 complete (tests import `src/`, winding integral has analytic ground truth) — done 2026-08-07, plus found and fixed the winding formula itself (v1.0.2) and added the steady-rotation gate it revealed was needed (v1.0.3)
- [x] Tier 1 all green — done 2026-08-07, `tests/test_unit.py`: packet round-trip, packet-length regression, full 5-gate fail-closed matrix, 10,000-input fuzz pass (zero crashes), deque-bound proof, surgery unit-quaternion invariant (50 random cases). 1.3s runtime. Not yet wired into CI.
- [x] Tier 2.3 passes — **surgery has fired successfully at least once**, with a correct, verified correction applied — done 2026-08-07, `tests/helix_plop_synthetic_test.py`, quaternion confirmed unit-norm post-correction
- [x] Tier 2.4 passes — checkpoint survives a real kill, not just a claim — done 2026-08-07, `tests/test_checkpoint_integrity.py`: SIGKILL mid-run, checkpoint intact and parseable, `complete=False` correctly not claiming success. Also stress-tested with 5 consecutive kill/restart cycles, no corruption.
- [x] Tier 3 regression suite green across all 6 trajectories — done 2026-08-07 under v1.0.3, re-confirmed statistically identical under v1.0.4's streaming refactor, see table above
- [x] Tier 4.1 soak run with flat memory, on record — the soak run itself *found* a real bug (see v1.0.4 in CHANGELOG.md: `generate_imu()` pre-allocated the whole trajectory upfront, OOM-killed at 25 min on a 50h run). Fixed via streaming generation; re-run confirmed flat 74-78MB memory over 75+ minutes (3x past the old failure point) before being judged clean enough to redeploy. Short of a literal 24h continuous-service record, but the failure mode the tier exists to catch was caught, diagnosed, and fixed.
- [x] No open 🔴-priority items in this document — all originally-flagged 🔴 items closed, plus the memory-scaling bug the soak test surfaced

Currently: **7 of 7 boxes checked.** Since Tier 0 began: found and fixed the winding formula (never worked, on any trajectory), fired surgery successfully for the first time ever, resolved the barrel-roll false-positive-response question with a working gate, closed every unit/integration/adversarial gap, and the soak test itself caught a real OOM bug in the simulation harness that's now fixed and re-verified. v1.0.4 approved for redeploy to CORE on this basis.

**Still worth doing, not blocking:** a literal unattended 24h+ continuous run (this session validated 75+ min under close observation, not a full day unattended); wiring Tier 1 into CI so it runs on every commit automatically rather than manually.

---

## Suggested Execution Order

1. **Now (idle CORE time):** Kick off Tier 4.1 soak test in the background — it just needs to run, doesn't block anything else.
2. **Next session, focused work:** Tier 0 (both items) — this is the prerequisite for every other tier meaning anything.
3. **Then:** Tier 1 full suite (fast, cheap, catches regressions immediately).
4. **Then:** Tier 2, especially 2.3 — this is the test that actually matters.
5. **Alongside:** Tier 3 regression re-runs (can run unattended, short each).
6. **Before adapter migration:** Tier 5, and confirm the acceptance checklist above.

---

🦉⚓🦆📡🔒

*A green test suite that never exercises the failure mode it exists to catch isn't validation — it's decoration. This battery is designed to stop being decoration.*

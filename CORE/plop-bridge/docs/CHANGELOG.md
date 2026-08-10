# PLOP Bridge Changelog

## v1.0.10 — 2026-08-10 (post-review hardening)

- **SVD planarity selector** replaces the v1.0.9 dot-product gate
  (`max|g·axis| < 1e-2`) in `compute_winding_number()`. The dot-product
  gate went blind at ~0.5° of noise — measured winding collapsed
  0.139 → 0.0002 on a perturbed barrel roll (independent review
  2026-08-10). PCA planarity (`s2/s0 < 0.1`) with an angular-extent
  guard (`s0 > 0.1`) is robust: noisy barrel rolls keep their winding,
  cones and great circles stay exact, and clustered noise blobs stay
  quiet (the extent guard keeps the SVD branch from firing on a blob,
  whose plane normal points through the path — apex on the path
  exploded the fan).
- **is_steady_rotation near-zero mask**: near-zero rows no longer
  normalize to spurious ~1e3 axis components; an intermittently zeroing
  gyro during a commanded roll can no longer evade the gate.
- **SO_REUSEADDR** on Ring1Listener (rapid-restart bind races).
- **final_yaw_deg → final_attitude_error_deg**: qangle() returns total
  rotation angle, not yaw — the metric is now named truthfully.
- Tests: test_v110_hardening.py (noisy-barrel robustness, noise-blob
  quietness, gate tolerance). Suite: 40 tests.

## v1.0.9 — 2026-08-10 (winding operator fix, FINDING 2026-08-10)

- **Great-circle degeneracy fixed.** `compute_winding_number()` used the
  window's own first sample as fan apex — a point ON the loop — so any
  great-circle loop (canonical barrel-roll geometry: roll axis ⊥ gravity)
  had every fan triangle degenerate and summed to exactly 0.0. Measured:
  real barrel-roll windows showed max |W| = 2e-5 instead of the ~0.14
  their geometry demands. The v1.0.3 steady-rotation gate had nothing to
  suppress, and the default threshold (0.5) was unreachable for any
  single loop (W = (1−cos θ)/2 peaks just under 0.5 as θ→90°, collapsing
  to 0 at exactly 90°).
- **Hybrid apex:** the loop's own rotation axis for planar
  (great-circle family) paths, the mean direction for conical paths,
  with the closing pair added for closed loops. Small-circle analytic
  match preserved (<1e-6); great circles now report (1−cos θ)/2;
  partial arcs are monotone and bounded by the cap; real barrel-roll
  windows read ~0.14/window (was 2e-5).
- **Default --W-thresh 0.5 → 0.02** (calibrated 2026-08-10): catches
  half-loops of 30° cones and shallow sweeps with 100×+ margin over the
  measured noise floor (stationary 2e-11, vibration ~7e-4). The steady
  gate remains the guard against commanded maneuvers — and now has
  something to guard.
- Tests: test_winding_v109.py (5 regression guards). Suite: 39 tests.

## v1.0.8 — 2026-08-09 (counter red-team, Hermes)

- **NaN/Inf CLI floats bypassed every v1.0.7 validator.** The guards used
  `x <= 0` comparisons, which are False for NaN in IEEE floats, so
  `--W-thresh nan` reopened the surgery-every-window hole (demonstrated:
  PLOP firing on flat flight at W≈0) and `--duration nan` crashed with a
  raw ValueError. All float args (`--duration`, `--W-thresh`,
  `--steady-cv-thresh`, `--steady-axis-thresh-deg`) are now
  finite-checked at startup.
- **`--rate` was not validated at all.** `--rate 0` → ZeroDivisionError;
  `--rate -100` → negative dt → negative N → StopIteration, the exact
  crash v1.0.7 closed for `--duration`, through a different door. Now
  rejected (must be > 0).
- **`--window >= N` silently disabled detection and intermediate
  checkpoints.** With a window that can never complete, the periodic
  `i % window` check never fires — no detection, no mid-run forensic
  checkpoints, and no warning. Now rejected at startup (window must be
  < total samples).
- All six new cases added to test_cli_validation.py (exit 2 + message
  asserted — 12 rejection cases total in that test). Full suite: 32
  tests, all green, standalone runners exit 0.

## v1.0.7 — 2026-08-09 (red team)

- **Fail-closed guarantee had a silent hole.** A single non-finite
  (NaN/Inf) sensor sample permanently poisoned the running attitude
  quaternion `q` (`qnorm`/`qmul` never recover from NaN once it enters
  the state), and `compute_winding_number()` silently reported `W=0.0`
  for a fully-poisoned window — the `abs(denom) > 1e-10` mask excludes
  every NaN comparison (NaN comparisons are always False in numpy), so
  every term summed to zero. Net effect: total sensor failure was
  indistinguishable from genuinely flat, healthy flight for the rest of
  the run — surgeries/suppressed stayed empty, nothing alerted, the only
  breadcrumb was `final_yaw_deg` silently going `NaN` in the checkpoint
  JSON (not one of `MONITORING.md`'s alert thresholds). This is exactly
  the failure mode PLOP exists to catch, reproduced inside PLOP itself.
  **Fixed in three layers:** sensor samples are checked finite at
  ingestion — the earliest possible point, before `q` can be poisoned;
  `compute_winding_number()` now returns `NaN` instead of `0.0` for any
  non-finite window, so corruption can't masquerade as a clean reading;
  `topological_surgery()` treats `NaN` `W` as "don't apply a correction"
  (a correction computed from garbage is itself garbage) while still
  surfacing the `NaN` rather than swallowing it, so the main loop can
  fail loud: log the fault, write a final checkpoint (`complete: false`,
  new `faults` array), and `exit(1)` so systemd's `Restart=on-failure`
  recovers with clean state instead of running for hours on fake-healthy
  telemetry. Tests: `test_sensor_fault_detection.py` — real subprocess
  run with one injected NaN gyro sample, verifies exit code, fault log,
  and that the checkpoint shows the last *clean* pre-fault state rather
  than NaN garbage (confirming the ingestion check catches it before
  propagation, not after).
- **Checkpoint chain HMAC-keyed — closes the forgery gap.** The chain
  linkage (`self_hash`) was plain SHA-256: a checksum, not a signature.
  Confirmed by red-team test: a checkpoint claiming "24h clean run, zero
  surgeries," fabricated from scratch with no actual bridge execution,
  passed `verify_checkpoint()` cleanly — the hash functions are public
  and unkeyed, so anyone with file-write access could recompute matching
  hashes and forge a fully self-consistent "verified" audit trail, not
  just tamper with a real one. "Tamper-evident" was stronger language
  than the mechanism supported. Fixed: `_chain_hash()` is now
  HMAC-SHA256 keyed via `PLOP_CHAIN_KEY` (env var) or `--chain-key-file`,
  resolved once at startup — the bridge now refuses to start at all
  without a key (`RuntimeError`, exit 1, no silent unkeyed fallback).
  `_content_hash()` (the body fingerprint) stays plain SHA-256 — the
  security boundary is entirely in the keyed linkage, forging a valid
  `self_hash` now requires the key. Re-verified the exact forgery
  scenario post-fix: a checkpoint forged with the wrong key correctly
  fails `SELF_HASH_MISMATCH` against the real one. Breaking change: old
  v1.0.5/v1.0.6 checkpoints (unkeyed hashes) will not verify under the
  new scheme — expected, they're the weaker thing this replaces. Not yet
  wired into CORE's systemd unit (`EnvironmentFile=` needed before next
  deploy, matching the existing `helix-demo.service` convention).
- **Replay protection on Ring 1.** `validate_plop_packet()` checks
  structure/hash but has no memory of what it's already seen — a
  captured valid packet could be resent indefinitely, each resend
  counted as an independently-verified event (confirmed: 221/500 raw
  resends accepted with zero detection). Fixed in `Ring1Listener`
  (not `validate_plop_packet()` itself, which stays pure/stateless) —
  tracks the last-accepted timestamp and rejects `ts <= last_accepted`
  as `REPLAY_FAULT`. Initialized to `-1`, not `0`, so a legitimate
  first packet at `ts=0` isn't mistaken for a replay of itself.
  Re-verified the original probe post-fix: 1/500 accepted, matching
  exactly. Tests: `test_adversarial_socket.py` — `test_packet_flood()`
  now asserts exactly 1 verified / 199 replay-rejected instead of just
  counter consistency, plus a new `test_replay_protection()`.
- **CLI validation on the three remaining red-team findings.** All three
  now rejected at startup (argparse error, exit 2, reason printed)
  instead of reaching the run loop: `--duration <= 0` (was an unhandled
  `StopIteration` — the sample generator is exhausted before the first
  `next()` call); `--window < 3` (was a silent, permanent detection-gate
  disable — `compute_winding_number()` returns exactly `0.0`
  unconditionally below 3 samples, no warning); `--W-thresh <= 0` (was
  surgery firing on every single window, including genuinely flat
  flight, since `abs(W) < 0` is never true). Tests: `test_cli_validation.py`
  — six invalid configs each rejected with the right explanation in
  stderr, one valid config confirmed unaffected.

This closes every finding from the 2026-08-09 red-team pass.

## v1.0.6 — 2026-08-09

- Fixed the accel-channel quirk: white noise `an` was computed but never
  applied, and the accel bias `ab` was added twice (`ab+ab`) instead of
  `ab+an`, inflating simulated position drift and making the checkpoint's
  `final_pos_m` metric a pessimistic bound rather than a measurement.
  Detection (gyro → attitude → winding) never used the accel channel, so
  surgery/gate behavior is unchanged. Verified: stationary 3-min sim
  position error 17.42m → 10.00m (the doubled bias accounted for ~7.4m).

## v1.0.5 — 2026-08-08

- Vectorized the topological hot path: the winding fan sum, the surgery
  axis accumulation, and the per-window gravity-in-body-frame rebuild now
  use array ops and batched qdcm — identical math (equivalence-verified
  to <1e-12), no behavior change, but the window check is now a few array
  expressions instead of ~M Python-loop iterations (matters for long
  soak runs).
- `craft_plop_packet()` packs Lk as `sign(winding_number)` — a fractional
  winding can no longer truncate into a valid-looking zero.
- Tamper-evident checkpoint chain: every checkpoint carries a self-hash
  over its full content plus the previous checkpoint's hash, and appends
  one line to `<output>.chain` (append-only journal). `verify_checkpoint()`
  audits a checkpoint file; tampering with any field or truncating the
  journal breaks verification. Tests: test_checkpoint_chain.py.

---

## v1.0.4 — 2026-08-08 (streaming trajectory generation, full test battery)

Running the full test battery (Tiers 1, 2.4, 4, 5) found a real problem
in Tier 4.1: a 50h-simulated soak test (`tests/soak_test.sh`, matching
production sizing: 300Hz/window=30000) was OOM-killed (SIGKILL, exit 137)
after 25 minutes, memory having climbed 4.3GB -> 6.0GB in that time.

**Root cause:** `generate_imu()` pre-allocates the entire simulated
trajectory upfront -- ~8 full-length `(N,3)`/`(N,4)` arrays (attitude,
velocity, position, angular rate, acceleration ground truth, plus the
noisy sensor outputs). The v1.0.1 `deque(maxlen=window)` fix only bounded
the *windowed analysis* buffers (`q_history`/`omega_history`); it never
touched this upfront generation, which scales directly with
`--duration` regardless of window size. A 24h run (the size used in
every prior test) sat at 3-5GB for the same reason -- closer to the edge
than anyone realized. The 7-day-LEO scenario that originally motivated
the v1.0.1 fix would hit this same wall at roughly 7x that footprint.

**Fixed:** replaced upfront generation with `generate_om_ac_stream()`, a
chunked generator (default chunk size `max(window, 50000)`) that yields
`(om_chunk, ac_chunk)` pairs instead of allocating the whole run. Two
simplifications made this straightforward:
- Ground-truth attitude (`qt`) is *always* identity for every existing
  trajectory -- confirmed by inspection, `qt` is initialized once and
  never modified in any trajectory branch of the original code. Replaced
  with a constant (`QT_IDENTITY`), zero memory regardless of duration.
- Ground-truth position (`pt`) is a deterministic closed-form function of
  `t = i*dt` for every trajectory (no randomness involved) -- replaced
  with `true_position_at(i, dt, traj)`, recomputed on demand instead of
  stored.
- Only `om`/`ac` (angular rate / acceleration, which involve seeded
  random walks + white noise) genuinely need per-sample values in
  sequence -- these are what `generate_om_ac_stream()` actually streams,
  carrying the gyro/accel bias random-walk state across chunk boundaries
  so drift stays continuous rather than resetting to zero at each chunk.

Original `generate_imu()` kept as-is (documented as unsuitable for large
`--duration`) for any external callers relying on it directly. Not
bit-identical to the old code for a given seed (RNG draw order changed
due to chunking), but statistically equivalent -- no existing test
asserts exact values, only statistical/geometric properties, so nothing
regressed.

**Verified:**
- Full 7-file local test suite green after the refactor (all Tier 1
  unit tests, analytic winding, steady-rotation gate, checkpoint
  integrity, adversarial socket, fire test, synthetic test).
- 6-trajectory regression: statistically identical to pre-refactor
  behavior (5/6 at 0 surgeries/0 suppressed, barrel_roll 0 applied/10
  suppressed, same W range).
- Re-ran the exact soak config that OOM-killed before: **70MB at
  startup vs. 4,336MB previously** -- roughly 60x lower. Full multi-hour
  flat-memory confirmation in progress, see `docs/DEPLOYMENT_STATUS.md`
  for the latest sample.

### Also this pass: full test battery run (Tiers 1, 2.4, 4.3, 4.4, 5)

Prompted by "let's do them all" after Tier 0/2.3/3 closed the highest-
priority gaps. New test files:

- `tests/test_unit.py` (Tier 1) -- packet round-trip, packet-length
  regression, full 5-gate fail-closed matrix, 10,000-input fuzz pass
  (zero crashes), deque-bound proof, surgery unit-quaternion invariant
  (50 random cases). 1.3s total runtime.
- `tests/test_checkpoint_integrity.py` (Tier 1.8 + 2.4) -- checkpoint
  JSON polled valid throughout a run (not just at the end), and **a real
  SIGKILL mid-run** leaves an intact, parseable, correctly
  `complete=false` checkpoint. This is the first time the v1.0.1
  checkpoint-survival claim was tested against an actual kill rather
  than just asserted.
- `tests/test_adversarial_socket.py` (Tier 5) -- malformed/truncated/
  oversized packets sent to the Ring1 port from outside the bridge
  process, 200-packet flood with zero loss on loopback, all correctly
  rejected or accepted with no crash.
- 5-cycle manual kill/restart resilience test (Tier 4.3 proxy, no
  systemd required): repeated `kill -9` + restart, checkpoint intact
  and non-corrupt every time, no crash-loop behavior.
- Tier 4.4 (O(n) scaling): fixed total sample count, varying window
  size 3000/6000/15000 -- runtime 11.8s/13.0s/14.0s, consistent with
  O(n) not O(n^2)+.

Not yet redeployed to CORE -- still stopped from the v1.0.2/v1.0.3
investigation. This is repo-only validation.

---

## v1.0.3 — 2026-08-07 (steady-rotation gate)

Direct consequence of v1.0.2: fixing the winding formula revealed that a
sustained rotation (barrel roll) genuinely crosses the winding threshold
repeatedly — correct math, but firing surgery on every crossing during a
commanded maneuver would fight it rather than fix a fault. The winding
integral alone has no way to distinguish "anomalous topology break" from
"intentional sustained rotation"; both produce identical signatures on S².

**Added:** `is_steady_rotation(omega_window, cv_thresh=0.15, axis_align_thresh_deg=15.0)`
— classifies whether angular-rate over the same window looks like a
smooth, bounded, sustained rotation (low coefficient-of-variation in
magnitude, stable axis via resultant-vector-norm) as opposed to erratic
or negligible motion. Wired into the main loop: when a threshold crossing
would fire, the gate is checked first; if steady, the crossing is logged
to a new `suppressed` array (timestamp, W, axis, reason) instead of
`surgeries` — visible for forensics, but not applied to the quaternion or
emitted as a PLOP packet. Disable with `--no-steady-gate` to restore
unconditional firing (pre-v1.0.3 behavior) if needed for comparison.

**Verified:**
- `tests/test_steady_rotation_gate.py` (new): 5/5 — sustained roll →
  steady; erratic rotation → not steady; negligible rotation → not steady
  (deliberately fails open to surgery, since nothing explains an
  unexplained crossing); spiky-magnitude/fixed-axis → not steady;
  degenerate window → not steady.
- barrel_roll regression: 0 surgeries applied (was 10 unconditional under
  v1.0.2), 10 correctly logged to `suppressed`. All 5 non-rotating
  trajectories unaffected (0/0 both before and after the gate).

**Known texture, not a bug:** the axis-steadiness check uses
resultant-vector-magnitude (a soft average), not max angular excursion —
a smoothly precessing axis that sweeps ~36° over a window can still read
as "steady" if the sweep is gradual, since the metric measures average
deviation, not peak deviation. Worth knowing if tuning
`--steady-axis-thresh-deg`, not something to "fix" without deciding it's
actually wrong for the operational case.

## v1.0.2 — 2026-08-07 (winding formula fix)

While verifying the v1.0.1 fixes, further testing found that
`compute_winding_number()` doesn't actually compute the swept/enclosed
solid angle for *any* trajectory, closed or open — this was deeper than
the previously-documented "synthetic trajectory doesn't parameterize a
true closed loop" limitation. Verified two ways: (1) fixing the
synthetic generator's `endpoint=False` closure gap didn't change the
result — W stayed at exactly 0.0 on a genuinely closed 30° cap where the
analytic answer is 0.066987; (2) replacing the same per-triangle math
with a fixed-apex fan triangulation (apex = window's own first sample,
summed over consecutive pairs) reproduced the analytic solid angle to 6
decimal places on the same case.

**Root cause:** the old formula summed Van Oosterom-Strackee solid-angle
terms over a *sliding* window of 3 consecutive curve points
`(g[i], g[i+1], g[i+2])`. That per-triangle formula is only a valid
decomposition of total swept/enclosed solid angle when triangles fan out
from a single *fixed* apex over the whole curve — a moving triple doesn't
telescope into a meaningful geometric quantity.

**Impact:** every "gate stays closed correctly on stable flight" claim
in prior docs was still true (near-zero-under-either-formula isn't where
this shows up), but every `W_threshold` value in every doc and script was
calibrated against a formula that couldn't produce a meaningful nonzero
value in the first place. The "±1 means full enclosure" framing didn't
hold under the deployed code.

**Fixed:** `compute_winding_number()` rewritten to fan-triangulate from
`g[0]` (the window's own first sample) over consecutive pairs, no
wraparound needed — works for both open arcs (partial sweep) and closed
loops (full solid angle) since it doesn't require the curve to close.

**Verified:**
- `tests/test_analytic_winding.py` (new): closed caps at 10°/30°/60°/90°
  half-angle all match `(1-cos(theta))/2` to ~1e-8; open arc gives a
  nonzero partial sweep less than the closed case; noise and
  near-stationary cases stay near zero.
- `tests/helix_plop_synthetic_test.py` (refactored, see below): **surgery
  fired successfully end-to-end for the first time** — W=0.25 on a
  genuine 30°-latitude closed cone (matching analytic solid angle for
  60° half-angle), quaternion correction applied and confirmed
  unit-norm, PLOP packet crafted/validated, Ring1 verified receipt.
- Full 6-trajectory regression (stationary, const_vel, sinusoidal,
  vibration, leo, barrel_roll): 5 of 6 unchanged at 0 surgeries;
  barrel_roll changed from 0 to 10 surgeries — see v1.0.3 above for what
  that meant operationally.

**Also fixed this pass — Tier 0.1 (tests import `src/`):** both test
files previously duplicated `craft_plop_packet`/`validate_plop_packet`
inline instead of importing from `src/helix_imu_plop_bridge.py`. This is
*why* the v1.0.1 padding bug shipped past "6/6 passing" undetected — the
duplicated copies were already correct, so a green fire test never
actually exercised the deployed source's packet crafting. Both test
files now `sys.path.insert` + import from `src/`; the duplicate
implementations are gone. Also added a baseline-hash-mismatch case to
both files' fail-closed matrices (now 7/7 and 5/5 respectively, up from
6/6 and 4/4), since that gate didn't exist before v1.0.1 either.

**Not yet redeployed to CORE** — v1.0.1 was running live (PID 2284572)
when this was found; stopped and disabled pending this fix and the
v1.0.3 gate. Repo-only as of this entry.

---

## v1.0.1 — 2026-08-07 (post-deployment review fixes)

Prompted by an independent code review that read the source against the
deployment docs. All five findings were verified against `src/helix_imu_plop_bridge.py`
before fixing. One additional bug was found during verification that the
review didn't catch.

### 🔴 Critical Fixes

1. **Packet padding used the wrong escape (`b'\\x00'` instead of `b'\x00'`)**
   — not in the original review, found while verifying finding #2.
   The double backslash produced four literal bytes (`\`, `x`, `0`, `0`)
   per padding unit instead of one null byte, making every crafted packet
   716 bytes instead of 200. Because every deployment test today ran on
   the `stationary` trajectory (surgeries=0 throughout), `craft_plop_packet`
   was never actually called in production — so this shipped live and
   never triggered. Consequence if it had: the moment a real gimbal-lock
   event crossed threshold, self-validation would fail `SIZE_FAULT`, and
   the surgery correction would silently never apply — no packet, no log
   entry, no error. The one scenario PLOP exists for would have no-oped.
   **Fixed:** single backslash, packet now correctly 200 bytes.

2. **`validate_plop_packet()` never checked the baseline hash**, despite
   every doc listing it as the 5th of 5 fail-closed gates. A packet with
   the wrong baseline hash but correct magic/size/winding/free_scale
   passed validation — breaking the dual-station triangulation guarantee
   the hash exists to enforce.
   **Fixed:** added `expected_hash` parameter, wired through `Ring1Listener`
   and self-validation to `args.baseline_hash`. Mismatches now return
   `BASELINE_FAULT`. Passing `None` preserves old skip-the-check behavior
   for callers that don't yet know the expected baseline.

3. **Documentation claimed O(n⁴) for the Gauss linking integral; the code
   is O(n)** — a single loop over the window. The O(n⁴) figure leaked in
   from a different script (`constitutional_spacetime_sim.py`) that
   genuinely has that complexity; it was mislabeled onto this bridge across
   9 references in 5 docs.
   **Fixed:** all references corrected to O(n). Good news either way —
   it's cheaper than documented, not more expensive.

### 🟡 Moderate Fixes

4. **`q_history` grew unbounded for the life of the process** even though
   only the last `--window` quaternions are ever read. At 24h/300Hz that's
   ~830 MB of quaternion storage alone that never gets released, on top of
   everything else — a real ceiling for longer runs (e.g. 7-day LEO).
   **Fixed:** `q_history` is now `collections.deque(maxlen=args.window)`.
   Memory stays flat regardless of run duration.

5. **JSON output was written once, at the very end.** A crash at hour 23
   of a 24-hour run lost the entire forensic record — the one thing PLOP
   is supposed to guarantee survives.
   **Fixed:** `write_checkpoint()` now runs after every window (not just
   on surgeries), writing to a `.tmp` file and `os.replace()`-ing over the
   target — atomic, so a crash mid-write never corrupts the last good
   checkpoint. Output now also carries `"complete": bool` and
   `"last_sample": int` so a partial file is self-describing.

### Still Open at time of writing (resolved in v1.0.2, see above)

- **Surgery path remains functionally untested.** The synthetic closed-loop
  generator produced W≈0 instead of the expected ±0.067, and the surgery
  branch had never successfully executed in any test to date. →
  **Resolved in v1.0.2**: root cause was the winding formula itself, not
  the synthetic generator (which was fine all along). Surgery has since
  fired successfully end-to-end.

- **Tests duplicate the protocol instead of importing `src/`.** →
  **Resolved in v1.0.2**: both test files now import from `src/` directly.

### Verification

```bash
cd src && python3 -c "
from helix_imu_plop_bridge import craft_plop_packet, validate_plop_packet, PLOP_SIZE
p = craft_plop_packet(100, 0xA1B2C3D4, 1)
assert len(p) == PLOP_SIZE
assert validate_plop_packet(p, 0xA1B2C3D4) == (True, 'OK')
assert validate_plop_packet(p, 0xDEADBEEF)[1] == 'BASELINE_FAULT'
print('OK')
"
```

Local re-run (`--duration 0.05 --traj stationary`) and `tests/helix_plop_fire_test.py`
both confirmed green after these changes.

### Deployed

Redeployed to CORE 2026-08-07 14:35:41 UTC (PID 2284572). Pre-restart the
fixed source was verified directly on CORE (not just via the tests' inline
duplicate copy): 200-byte packets, `BASELINE_FAULT` on hash mismatch, clean
0.1h integration run with checkpoint fields present. See
`docs/DEPLOYMENT_STATUS.md` for the restart record.

---

## v1.0 — 2026-08-07 (initial deployment)

Initial production deployment to CORE 20.124.180.133. See
`docs/DEPLOYMENT_STATUS.md` for the original deployment record.

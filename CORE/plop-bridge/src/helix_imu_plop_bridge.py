#!/usr/bin/env python3
"""
HELIX IMU-TO-PLOP BRIDGE v1.0.10
Operational bridge between topological IMU operator and PLOP-200 protocol.

v1.0.1: Fixed packet padding escaping (was 716B not 200B), added baseline
hash validation gate, bounded q_history memory, checkpointed JSON writes.
v1.0.2: Replaced compute_winding_number()'s sliding-triple-window formula
(verified to return exactly 0.0 on genuinely closed loops -- not a valid
decomposition of enclosed solid angle) with a fixed-apex fan triangulation
that matches analytic solid angle to 6 decimal places. W_threshold values
were never calibrated against a working formula until now.
v1.0.3: Added is_steady_rotation() gate. The v1.0.2 fix revealed that a
sustained barrel roll genuinely crosses the winding threshold repeatedly
(correct math) -- but the winding integral alone can't tell that apart
from an anomalous topology break (wrong response to fire surgery on a
commanded maneuver). The gate checks angular-rate steadiness over the
same window and suppresses surgery when the crossing is explained by
smooth, bounded, sustained rotation, logging it to "suppressed" for
forensic visibility instead of silently dropping it.
v1.0.4: Replaced upfront full-trajectory generation (generate_imu(),
~8 arrays of length N) with generate_om_ac_stream(), a chunked generator.
The v1.0.1 deque-bound fix never touched this -- memory scaled directly
with --duration regardless of window size. A 50h soak test (Tier 4.1)
got OOM-killed after 25 minutes at ~6GB. Ground truth attitude (always
identity) and position (deterministic closed-form) are recomputed on
demand instead of stored.
v1.0.5: Vectorized the topological hot path -- the winding fan sum,
the surgery axis accumulation, and the per-window
gravity-in-body-frame rebuild now use array ops and batched qdcm
(same math, no behavior change). craft_plop_packet() packs Lk as
sign(winding_number) so a fractional winding can never truncate
into a valid-looking zero. Every checkpoint is chained into a
tamper-evident hash chain (self-hash over full content + previous
hash, appended to <output>.chain) with verify_checkpoint() as the
auditor.
v1.0.6: Fixed the accel-channel quirk -- white noise `an` was
computed but never applied, and the accel bias `ab` was added
twice (ab+ab) instead of ab+an, inflating simulated position
drift and making the checkpoint's final_pos_m metric a
pessimistic bound rather than a measurement. The detection path
(gyro -> attitude -> winding) never used the accel channel, so
no surgery/gate behavior changes. Position integration now uses
ab+an.
v1.0.7: Red-team finding -- a single non-finite (NaN/Inf) sensor
sample permanently poisoned the running attitude quaternion q
(qnorm/qmul never recover from NaN), and compute_winding_number()
silently reported W=0.0 for a fully-poisoned window (the
abs(denom) > 1e-10 mask excludes every NaN comparison), making
total sensor failure indistinguishable from genuinely flat
flight for the rest of the run. Fixed in three layers: sensor
samples are checked finite at ingestion (earliest possible catch),
compute_winding_number() returns NaN instead of 0.0 for any
non-finite window, and topological_surgery() treats NaN W as
"don't apply a correction" while still surfacing it so the main
loop can fail loud -- log the fault, write a final checkpoint,
exit(1) so systemd's Restart=on-failure recovers with clean state
instead of running for hours reporting fake-healthy telemetry.
Also v1.0.7: checkpoint chain is now HMAC-SHA256 keyed
(PLOP_CHAIN_KEY / --chain-key-file, required -- no unkeyed
fallback) instead of plain SHA-256, closing a forgery gap where
anyone with file-write access could recompute matching hashes
and fabricate a fully "verified" checkpoint from scratch.
Also v1.0.7: Ring1Listener rejects replayed packets (a captured
valid packet resent repeatedly no longer counts as N independent
verified events -- tracks last-accepted timestamp, rejects
ts <= last_accepted as REPLAY_FAULT).
Also v1.0.7: --duration<=0, --window<3, and --W-thresh<=0 are now
rejected at startup instead of crashing (StopIteration) or
silently misbehaving (permanently disabled gate / surgery firing
on flat flight). Closes every finding from the 2026-08-09
red-team pass. v1.0.8: Counter red-team (Hermes) on the v1.0.7 CLI hardening --
the validators used `x <= 0` comparisons, which are False for NaN
in IEEE floats, so `--W-thresh nan` reopened the
surgery-every-window hole and `--duration nan` crashed with a raw
ValueError. --rate was not validated at all (0 -> ZeroDivisionError;
negative -> negative N -> StopIteration, the exact crash v1.0.7
closed for --duration, through a different door). And a window >=
total sample count silently disabled the detection gate and
intermediate checkpoints. All float args are now finite-checked,
rate must be > 0, and window must be < N.
v1.0.9: compute_winding_number() apex is no longer the window's
own first sample -- it was ON the loop, so great-circle loops
(canonical barrel-roll geometry) summed to exactly 0.0, blinding
the detector to its largest excursion (FINDING 2026-08-10).
Hybrid apex: loop rotation axis for planar paths, mean direction
for conical paths, closing pair for closed loops. Small-circle
analytic match preserved (<1e-6); great circles now report
(1-cos theta)/2. Default --W-thresh 0.5 -> 0.02 (calibrated).
v1.0.10: post-review hardening -- SVD planarity selector replaces
the v1.0.9 dot-product gate (max|g@axis| < 1e-2 went blind at
~0.5 deg of noise: winding collapsed 0.139 -> 0.0002);
is_steady_rotation masks near-zero rows (an intermittently
zeroing gyro could otherwise evade the gate); SO_REUSEADDR on
Ring1 for rapid restart; final_yaw_deg renamed
final_attitude_error_deg (qangle is total rotation, not yaw).
See docs/CHANGELOG.md.

When the spherical winding number |W[g_b]| crosses the constitutional threshold,
the bridge crafts a 200-byte PLOP packet and emits it to the Ring 1 listener.

Usage:
  python3 helix_imu_plop_bridge.py --duration 8.0 --traj stationary
  python3 helix_imu_plop_bridge.py --duration 1.0 --traj sinusoidal --sweep
"""

import numpy as np
import struct
import socket
import sys
import time
import json
import argparse
import os
import hashlib
import hmac
import fcntl
from collections import deque

# =============================================================================
# PLOP-200 CONSTANTS
# =============================================================================
PLOP_MAGIC = 0x706C6F70
PLOP_SIZE = 200
BIND_PORT = 5555
BIND_HOST = "127.0.0.1"

# =============================================================================
# QUATERNION UTILITIES (scalar-first)
# =============================================================================

def qmul(q, r):
    w1,x1,y1,z1 = q[...,0],q[...,1],q[...,2],q[...,3]
    w2,x2,y2,z2 = r[...,0],r[...,1],r[...,2],r[...,3]
    return np.stack([
        w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2,
        w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2
    ], axis=-1)

def qnorm(q):
    return q / (np.linalg.norm(q, axis=-1, keepdims=True) + 1e-15)

def qdcm(q):
    q = qnorm(q)
    w,x,y,z = q[...,0], q[...,1], q[...,2], q[...,3]
    return np.stack([
        np.stack([w*w+x*x-y*y-z*z, 2*(x*y-w*z), 2*(x*z+w*y)], axis=-1),
        np.stack([2*(x*y+w*z), w*w-x*x+y*y-z*z, 2*(y*z-w*x)], axis=-1),
        np.stack([2*(x*z-w*y), 2*(y*z+w*x), w*w-x*x-y*y+z*z], axis=-1)
    ], axis=-1)

def qfromomega(o, dt):
    ang = np.linalg.norm(o, axis=-1, keepdims=True) * dt
    ax = o / (np.linalg.norm(o, axis=-1, keepdims=True) + 1e-15)
    h = ang / 2
    return np.concatenate([np.cos(h), ax * np.sin(h)], axis=-1)

def qangle(q1, q2):
    d = np.abs(np.sum(q1 * q2, axis=-1))
    return 2 * np.arccos(np.clip(d, -1, 1))

# =============================================================================
# IMU GENERATOR
# =============================================================================

def generate_imu(N, dt, traj, seed=42):
    """Original batch generator: allocates all ~8 full-length (N,*) arrays
    upfront. Kept for small N / one-off use (e.g. test scripts), but the
    main bridge loop uses generate_om_ac_stream() instead -- see v1.0.4
    changelog. Memory here scales directly with N regardless of any
    windowing elsewhere; do not use this for large --duration runs."""
    rng = np.random.default_rng(seed)
    G = 9.80665; D2R = np.pi/180
    t = np.arange(N) * dt
    qt = np.zeros((N,4)); qt[:,0] = 1
    vt,pt,ot,at = np.zeros((N,3)),np.zeros((N,3)),np.zeros((N,3)),np.zeros((N,3))
    at[:,2] = -G
    if traj == "const_vel":
        vt[:,0] = 10; pt[:,0] = 10*t
    elif traj == "sinusoidal":
        f=0.1; a=1; pt[:,0]=a*np.sin(2*np.pi*f*t); vt[:,0]=a*2*np.pi*f*np.cos(2*np.pi*f*t)
        at[:,0]=-a*(2*np.pi*f)**2*np.sin(2*np.pi*f*t); at[:,2]=-G
    elif traj == "vibration":
        at[:,0]=rng.normal(0,0.3*G,N); at[:,1]=rng.normal(0,0.3*G,N); at[:,2]=-G+rng.normal(0,0.3*G,N)
    elif traj == "leo":
        r=6771e3; mu=3.986e14; w=np.sqrt(mu/r**3); vt[:,0]=np.sqrt(mu/r)
        pt[:,0]=r*np.cos(w*t); pt[:,1]=r*np.sin(w*t); ot[:,2]=w; at[:]=0
    elif traj == "barrel_roll":
        # Continuous barrel roll: sustained roll rate ~60 deg/sec
        roll_rate = 60.0 * D2R  # 60 deg/sec → rad/sec
        ot[:,0] = roll_rate  # Roll (X-axis rotation)
        at[:,2] = -G  # Gravity only
    gb = np.cumsum(rng.normal(0, 0.05*D2R/3600/np.sqrt(100)*np.sqrt(dt), (N,3)), 0)
    ab = np.cumsum(rng.normal(0, 50e-6*G/np.sqrt(100)*np.sqrt(dt), (N,3)), 0)
    gn = rng.normal(0, 0.05*D2R/60/np.sqrt(dt), (N,3))
    an = rng.normal(0, 0.005/60/np.sqrt(dt), (N,3))
    sf = 1 + rng.normal(0, 50e-6, 3)
    return qt, vt, pt, ot, at, sf*(ot+gb+gn), sf*(at+ab+an), t

# Ground truth attitude is identity for every trajectory: qt is allocated
# in generate_imu() but never modified after np.zeros((N,4)); qt[:,0]=1 in
# any branch above (confirmed by inspection) -- so there is no need to
# store an (N,4) array of it. Streaming code compares against this
# constant directly.
QT_IDENTITY = np.array([1., 0., 0., 0.])

def true_position_at(i, dt, traj):
    """Ground-truth position at sample i, recomputed on demand instead of
    stored in a full (N,3) array -- pt is a deterministic closed-form
    function of t=i*dt for every trajectory (no randomness involved), so
    there's nothing to stream here, just don't pre-allocate it. Mirrors
    generate_imu()'s pt formulas exactly (stationary/vibration/barrel_roll
    leave it at zero, matching np.zeros((N,3)) never being touched for
    those trajectories)."""
    t = i * dt
    p = np.zeros(3)
    if traj == "const_vel":
        p[0] = 10 * t
    elif traj == "sinusoidal":
        f, a = 0.1, 1
        p[0] = a * np.sin(2*np.pi*f*t)
    elif traj == "leo":
        r, mu = 6771e3, 3.986e14
        w = np.sqrt(mu / r**3)
        p[0] = r * np.cos(w*t)
        p[1] = r * np.sin(w*t)
    return p

def generate_om_ac_stream(N, dt, traj, seed=42, chunk_size=50000):
    """Memory-bounded replacement for generate_imu()'s om/ac outputs.

    v1.0.4: the Tier 4.1 soak test found that generate_imu() allocated
    ~8 full-length (N,*) arrays regardless of the v1.0.1 deque-bound fix
    (which only bounded the windowed q_history/omega_history analysis
    buffers, never touching this upfront trajectory generation). Memory
    scaled directly with total simulated duration: a 50h run at
    300Hz/window=30000 needed ~10GB and got OOM-killed (SIGKILL, exit
    137) after 25 minutes. Only om/ac involve seeded randomness (bias
    random walks + white noise) and are genuinely needed sample-by-sample
    in the main loop -- qt is always identity (QT_IDENTITY above) and pt
    is deterministic (true_position_at() above), so neither needs
    storing, streamed or otherwise.

    Yields (om_chunk, ac_chunk) pairs of shape (n, 3), n <= chunk_size,
    computed the same way generate_imu() did per-sample, just processed
    in bounded-size chunks instead of one N-sized allocation. The scale
    factor `sf` is drawn once per run (matching the original's
    once-per-call semantics) and carried across chunks; the gyro/accel
    bias random walks (gb/ab) carry their running cumulative value
    across chunk boundaries so the drift is continuous, not reset to
    zero at each chunk.

    Not bit-identical to generate_imu() for the same seed (RNG draw
    order differs due to chunking -- sf is drawn before the trajectory
    loop instead of after, and per-chunk draws replace single N-sized
    draws), but statistically equivalent: same distributions, same
    physical model. No existing test asserts exact values, only
    statistical/geometric properties (near-zero W, expected surgery
    counts, etc.), so this doesn't affect correctness of anything
    already validated.
    """
    rng = np.random.default_rng(seed)
    G = 9.80665; D2R = np.pi/180

    sf = 1 + rng.normal(0, 50e-6, 3)  # fixed per-run sensor calibration error

    gb_carry = np.zeros(3)
    ab_carry = np.zeros(3)

    i = 0
    while i < N:
        n = min(chunk_size, N - i)
        t = (i + np.arange(n)) * dt

        ot, at = np.zeros((n, 3)), np.zeros((n, 3))
        at[:, 2] = -G

        if traj == "sinusoidal":
            f, a = 0.1, 1
            at[:, 0] = -a * (2*np.pi*f)**2 * np.sin(2*np.pi*f*t)
            at[:, 2] = -G
        elif traj == "vibration":
            at[:, 0] = rng.normal(0, 0.3*G, n)
            at[:, 1] = rng.normal(0, 0.3*G, n)
            at[:, 2] = -G + rng.normal(0, 0.3*G, n)
        elif traj == "leo":
            ot[:, 2] = np.sqrt(3.986e14 / 6771e3**3)
            at[:] = 0
        elif traj == "barrel_roll":
            ot[:, 0] = 60.0 * D2R
            at[:, 2] = -G
        # stationary, const_vel: ot=0, at=[0,0,-G] (already set above)

        gb_steps = rng.normal(0, 0.05*D2R/3600/np.sqrt(100)*np.sqrt(dt), (n, 3))
        gb = gb_carry + np.cumsum(gb_steps, axis=0)
        gb_carry = gb[-1].copy()

        ab_steps = rng.normal(0, 50e-6*G/np.sqrt(100)*np.sqrt(dt), (n, 3))
        ab = ab_carry + np.cumsum(ab_steps, axis=0)
        ab_carry = ab[-1].copy()

        gn = rng.normal(0, 0.05*D2R/60/np.sqrt(dt), (n, 3))
        an = rng.normal(0, 0.005/60/np.sqrt(dt), (n, 3))

        om_chunk = sf * (ot + gb + gn)
        ac_chunk = sf * (at + ab + an)  # v1.0.6: accel noise applied once, bias once (was ab+ab)

        yield om_chunk, ac_chunk

        i += n

# =============================================================================
# TOPOLOGICAL OPERATOR
# =============================================================================

def compute_winding_number(g_b_trajectory):
    """Fan-triangulated solid angle swept by the window, apex = the path's
    own rotation axis (SVD best-fit plane normal; see v1.0.9/v1.0.10 notes
    below for the hybrid selector), summed over consecutive pairs.

    Each term is the Van Oosterom-Strackee solid angle of the spherical
    triangle (apex, g[i], g[i+1]); this is a valid decomposition of total
    swept solid angle as seen from apex, well-defined for both open arcs
    (partial sweep) and closed loops (full enclosed solid angle) since it
    doesn't require the curve to close or a wraparound term.

    v1.0.1 -> v1.0.2: replaced a sliding 3-point window formula that used
    the same per-triangle math but fanned from a *moving* triple instead
    of a fixed apex. That formula doesn't telescope into a meaningful
    quantity - verified empirically to return exactly 0.0 on a genuinely
    closed 30-deg cap where the analytic answer is 0.066987. This version
    matches known solid angle to 6 decimal places on the same case. See
    docs/CHANGELOG.md.

    v1.0.7: a window containing any non-finite (NaN/Inf) sample now
    returns NaN instead of silently computing 0.0. Previously the
    `ok = abs(denom) > 1e-10` mask excluded every NaN-denom term (NaN
    comparisons are always False in numpy), so a *fully* NaN-poisoned
    window -- e.g. one bad gyro sample propagating through qnorm/qmul,
    which never recovers -- summed to exactly 0.0: indistinguishable
    from genuinely flat flight. That silently and permanently blinded
    the detector for the rest of the run while looking identical to
    healthy telemetry. Returning NaN here makes it the caller's problem
    to handle explicitly (see topological_surgery and the main loop's
    fault check) instead of a value that reads as "nothing happening."

    v1.0.9: apex is no longer the window's own first sample -- it
    was ON the loop, so any great-circle loop (the canonical
    barrel-roll geometry: roll axis perpendicular to gravity) had
    every fan triangle degenerate and summed to exactly 0.0,
    blinding the detector to the largest excursions (FINDING
    2026-08-10). Apex is now the loop's own rotation axis for
    planar paths and the mean direction for conical paths --
    never a path point -- with the closing pair added for closed
    loops. Small-circle analytic match preserved (<1e-6);
    great-circle loops now report (1-cos theta)/2 instead of 0.
    """
    M = len(g_b_trajectory)
    if M < 3: return 0.0
    if not np.all(np.isfinite(g_b_trajectory)):
        return float('nan')
    g = g_b_trajectory / (np.linalg.norm(g_b_trajectory, axis=1, keepdims=True) + 1e-15)
    # v1.0.9: hybrid apex -- never a path point (see docstring).
    close = float(np.dot(g[0], g[-1])) > 0.999  # returns to start
    b, c = g[:-1], g[1:]
    if close:
        b = np.concatenate([b, g[-1:]])
        c = np.concatenate([c, g[:1]])
    axis = np.sum(np.cross(b, c, axis=1), axis=0)
    a_norm = np.linalg.norm(axis)
    axis_u = axis / (a_norm + 1e-15)
    # v1.0.10: SVD planarity selector. The v1.0.9 dot-product gate
    # (max|g@axis| < 1e-2) went blind at ~0.5 deg of noise (winding
    # collapsed 0.139 -> 0.0002). PCA is robust: for any effectively
    # 2D path (cone OR great circle) the best-fit plane normal IS
    # the rotation axis; only genuinely 3D paths use the mean.
    # s[0] > 0.1: the path must also have real angular extent -- a
    # clustered noise blob is trivially 'planar' and its plane normal
    # points through the blob (apex on the path -> fan explosion).
    g_centered = g - g.mean(axis=0)
    _, s, Vt = np.linalg.svd(g_centered, full_matrices=False)
    planar_ratio = s[2] / (s[0] + 1e-15)
    if a_norm > 1e-12 and planar_ratio < 0.1 and s[0] > 0.1:
        apex = Vt[2]
        if np.dot(apex, axis_u) < 0:
            apex = -apex
    else:
        mean_dir = g.mean(axis=0)
        m_norm = np.linalg.norm(mean_dir)
        apex = mean_dir / (m_norm + 1e-15) if m_norm > 1e-9 else axis_u
    cross_bc = np.cross(b, c, axis=1)
    triple = cross_bc @ apex
    denom = 1.0 + (b @ apex) + np.einsum('ij,ij->i', b, c) + (c @ apex)
    term = np.zeros_like(triple)
    ok = np.abs(denom) > 1e-10
    term[ok] = 2.0 * np.arctan2(triple[ok], denom[ok])
    return float(np.sum(term) / (4.0 * np.pi))

def topological_surgery(q_current, g_b_window, W_threshold=0.5):
    """Returns (q_out, W, did_surgery, axis).

    v1.0.7: W=NaN (non-finite window, see compute_winding_number) is
    treated as "don't apply a correction" -- same as did_surgery=False --
    since a quaternion correction computed from garbage is itself
    garbage, not a fail-closed action. The NaN is still returned in W
    rather than swallowed, so callers can tell "genuinely below
    threshold" apart from "the input was corrupted" and escalate the
    latter as a fault instead of silently treating it as calm flight
    (abs(NaN) < W_threshold is always False in numpy, so without this
    explicit check the old code fell through to computing a bogus
    "surgery" from NaN data instead of gating on it)."""
    W = compute_winding_number(g_b_window)
    if not np.isfinite(W):
        return q_current, W, False, None
    if abs(W) < W_threshold:
        return q_current, W, False, None
    g = g_b_window / (np.linalg.norm(g_b_window, axis=1, keepdims=True) + 1e-15)
    # v1.0.5: vectorized -- same sum of consecutive cross products.
    axis = np.sum(np.cross(g[:-1], g[1:], axis=1), axis=0)
    axis = axis / (np.linalg.norm(axis) + 1e-15)
    angle = -2.0 * np.pi * W
    h = angle / 2.0
    dq = np.array([np.cos(h), axis[0]*np.sin(h), axis[1]*np.sin(h), axis[2]*np.sin(h)])
    q_surgery = qnorm(qmul(q_current.reshape(1,4), dq.reshape(1,4)))[0]
    return q_surgery, W, True, axis

def is_steady_rotation(omega_window, cv_thresh=0.15, axis_align_thresh_deg=15.0):
    """Classify whether angular velocity over a window looks like a smooth,
    bounded, sustained rotation (roughly constant magnitude AND axis) --
    i.e. a commanded maneuver -- as opposed to erratic/anomalous motion.

    This exists because compute_winding_number() can't tell "gravity is
    looping in body frame because of an anomaly" apart from "gravity is
    looping because the vehicle is intentionally, controllably rotating"
    -- both produce identical winding signatures. A sustained barrel roll
    genuinely sweeps gravity around the roll axis in full loops (correct,
    real winding), but firing a quaternion correction every window during
    an intentional maneuver would fight the commanded motion rather than
    fix a fault. This is the gate that tells those two cases apart, using
    information the winding integral doesn't have access to: the actual
    commanded/measured angular rate.

    omega_window: (M,3) array of angular velocity samples (rad/s) spanning
    the same window used for the winding computation.

    Returns True if the rotation is steady (magnitude coefficient of
    variation below cv_thresh AND mean axis direction stays within
    axis_align_thresh_deg of constant) -- callers should treat True as
    "commanded maneuver, suppress surgery even if winding crossed
    threshold." Returns False for near-zero rotation (nothing steady to
    classify) or erratic/varying rotation (fire surgery as usual).
    """
    omega_window = np.asarray(omega_window)
    if len(omega_window) < 3:
        return False
    mags = np.linalg.norm(omega_window, axis=1)
    mean_mag = np.mean(mags)
    if mean_mag < 1e-6:
        # Negligible rotation -- if winding crossed threshold here, it
        # isn't explained by a steady commanded rotation. Don't suppress.
        return False
    # v1.0.10: mask near-zero rows before normalization -- a ~1e-12
    # row amplifies to a ~1e3 spurious axis component and inflates
    # the CV; an intermittently zeroing gyro during a commanded
    # roll could otherwise evade the gate.
    valid = mags > 1e-9
    if np.count_nonzero(valid) < 3:
        return False
    cv = np.std(mags[valid]) / np.mean(mags[valid])
    axes = omega_window[valid] / (mags[valid, None] + 1e-15)
    mean_axis_norm = np.linalg.norm(axes.mean(axis=0))  # 1.0 = perfectly steady axis
    axis_ok = mean_axis_norm > np.cos(np.deg2rad(axis_align_thresh_deg))
    return (cv < cv_thresh) and axis_ok

# =============================================================================
# PLOP-200 PACKET CRAFTER
# =============================================================================

def craft_plop_packet(timestamp_ns, baseline_hash, winding_number, free_scale_flag=0):
    """Craft a 200-byte PLOP packet per Campaign 5 spec.

    Lk is packed as sign(winding_number) -- the {-1, 0, +1} vocabulary
    the fail-closed validator accepts -- never the raw value, so a
    fractional winding can't truncate into a valid-looking zero (v1.0.5).

    v1.0.7: raises a clear ValueError for non-finite input rather than
    letting int(np.sign(nan)) raise numpy's less-obvious one. The main
    loop's fault-detection layers (see fail_fault()) mean NaN/Inf should
    never actually reach this function in a real run -- this is
    defense-in-depth for any other caller, not the primary fix."""
    if not np.isfinite(winding_number):
        raise ValueError(
            f"craft_plop_packet() got a non-finite winding_number "
            f"({winding_number}) -- refusing to craft a packet from it. "
            f"This should be unreachable from the main run loop (see "
            f"fail_fault() / v1.0.7 CHANGELOG); if you're hitting this, "
            f"something upstream skipped the finite-check layers.")
    lk = int(np.sign(winding_number))
    header = struct.pack(">QIIiII",
        timestamp_ns,      # uint64
        baseline_hash,     # uint32
        PLOP_MAGIC,        # uint32
        lk,                # int32, sign of winding
        free_scale_flag,   # uint32
        0                  # reserved
    )
    padding = b'\x00' * (PLOP_SIZE - len(header))
    return header + padding

def validate_plop_packet(packet, expected_hash=None):
    """Fail-closed validation per Campaign 5 spec.

    expected_hash: if provided, packet's baseline_hash must match exactly
    (mod 2**32, since baseline_hash is packed as uint32). Pass None to skip
    this check (e.g. when the expected baseline isn't known yet).
    """
    if len(packet) != PLOP_SIZE:
        return False, "SIZE_FAULT"
    ts, base_hash, magic, winding, free_s, _ = struct.unpack(">QIIiII", packet[:28])
    if magic != PLOP_MAGIC:
        return False, "MAGIC_FAULT"
    if free_s != 0:
        return False, "FREE_SCALE_FAULT"
    if winding not in (-1, 0, 1):
        return False, "WINDING_FAULT"
    if expected_hash is not None and base_hash != (expected_hash & 0xFFFFFFFF):
        return False, "BASELINE_FAULT"
    return True, "OK"

# =============================================================================
# RING 1 LISTENER (Simulated)
# =============================================================================

class Ring1Listener:
    """v1.0.7: rejects replayed packets -- validate_plop_packet() checks
    structure/hash but has no memory of what it's already seen, so a
    captured valid packet could be resent indefinitely and each replay
    counted as an independently-verified event (confirmed by red-team
    test: 500 resends of one packet, no detection). Fixed here rather
    than in validate_plop_packet() itself, since replay state belongs to
    the stream a listener observes, not to a single packet in isolation
    -- keeps that function pure/stateless and its existing tests
    untouched. Enforces strictly increasing timestamps: a legitimate
    stream only ever crafts packets with the current wall-clock ts, so
    replaying an already-accepted (or older) ts is rejected as
    REPLAY_FAULT."""

    def __init__(self, host=BIND_HOST, port=BIND_PORT, expected_hash=None):
        self.host = host
        self.port = port
        self.expected_hash = expected_hash
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # v1.0.10: rapid restart (systemd Restart=on-failure) must
        # not race a lingering bind on the same port.
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.settimeout(0.001)
        self.packets_received = 0
        self.packets_dropped = 0
        self.packets_verified = 0
        self.last_accepted_ts = -1  # v1.0.7: replay protection, see class docstring
        # -1, not 0: timestamps are unsigned in the wire format but a
        # legitimate first packet could carry ts=0 (tests use this as a
        # placeholder; real callers always pass a real ns timestamp,
        # which is never 0 in practice) -- -1 ensures ts=0 still counts
        # as newer than "nothing accepted yet" instead of colliding with it.

    def check(self):
        """Non-blocking check for incoming PLOP packets."""
        try:
            data, addr = self.sock.recvfrom(1024)
            self.packets_received += 1
            valid, reason = validate_plop_packet(data, self.expected_hash)
            if valid:
                ts, base_hash, _, winding, _, _ = struct.unpack(">QIIiII", data[:28])
                if ts <= self.last_accepted_ts:
                    self.packets_dropped += 1
                    return False, "REPLAY_FAULT"
                self.last_accepted_ts = ts
                self.packets_verified += 1
                return True, {"ts": ts, "hash": hex(base_hash), "Lk": winding}
            else:
                self.packets_dropped += 1
                return False, reason
        except socket.timeout:
            return None, None
        except Exception as e:
            return False, str(e)

    def close(self):
        self.sock.close()

# =============================================================================
# CHECKPOINT CHAIN (v1.0.5, keyed v1.0.7) -- tamper-evident audit trail
# =============================================================================

CHAIN_GENESIS = "PLOP200-CHAIN-GENESIS"


def _get_chain_key(key_file=None):
    """Resolve the checkpoint-chain HMAC key.

    v1.0.7: chain linkage (_chain_hash) was plain SHA-256 -- a checksum,
    not a signature. Anyone with write access to the checkpoint + its
    .chain journal could recompute matching hashes from scratch with the
    same public, unkeyed function and forge a fully self-consistent
    'verified' audit trail that was never actually produced by a real
    run (confirmed by red-team test: a fabricated 24h-clean-run
    checkpoint passed verify_checkpoint() with flying colors). HMAC-SHA256
    with a key that lives outside the checkpoint file closes that --
    forging a valid self_hash now requires the key, not just the hash
    function.

    Priority: explicit key_file argument (e.g. --chain-key-file) >
    PLOP_CHAIN_KEY environment variable (systemd EnvironmentFile is the
    existing convention for secrets on this substrate, e.g. azure.env).
    No default: refusing to run unkeyed is the point of this fix. Content
    can be hex (preferred, e.g. `python3 -c "import secrets;
    print(secrets.token_hex(32))"`) or any raw string, read as utf-8.
    """
    raw = None
    if key_file:
        with open(key_file) as f:
            raw = f.read().strip()
    if not raw:
        raw = os.environ.get("PLOP_CHAIN_KEY")
    if not raw:
        raise RuntimeError(
            "No checkpoint-chain key found. Set PLOP_CHAIN_KEY (env var) "
            "or pass --chain-key-file <path>. Generate one with: "
            "python3 -c \"import secrets; print(secrets.token_hex(32))\" "
            "-- see docs/CHANGELOG.md v1.0.7."
        )
    try:
        return bytes.fromhex(raw)
    except ValueError:
        return raw.encode()


def _content_hash(results):
    """SHA-256 over everything in a checkpoint except the chain field
    itself, canonicalized (sorted keys, compact separators) so the hash
    is deterministic and re-computable from the file. Not keyed -- this
    is just a body fingerprint; the security boundary is _chain_hash."""
    body = {k: v for k, v in results.items() if k != 'chain'}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()


def _chain_hash(prev_hash, index, sample_idx, complete, content_hash, key=None):
    """HMAC-SHA256 over the chain linkage fields. `key` bytes, or resolved
    from the environment/--chain-key-file if not passed explicitly."""
    if key is None:
        key = _get_chain_key()
    payload = json.dumps({
        'index': index,
        'prev_hash': prev_hash,
        'sample': sample_idx,
        'complete': complete,
        'content': content_hash,
    }, sort_keys=True, separators=(',', ':'))
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def verify_checkpoint(path, key=None, key_file=None):
    """Audit a checkpoint written by the bridge.

    Recomputes content_hash and self_hash from the file itself and, when
    the append-only journal (<path>.chain) exists, requires the journal's
    last line to carry the file's self_hash. Returns (True, "OK") or
    (False, reason).

    v1.0.7: self_hash is now HMAC-keyed (see _get_chain_key) -- pass
    `key` directly, or `key_file`, or set PLOP_CHAIN_KEY. Without the
    correct key this correctly reports SELF_HASH_MISMATCH for anything,
    genuine or forged -- that's the fix, not a bug: a checkpoint that
    can't prove which key signed it isn't verified.

    v1.0.11: the field-access/validation body below used to sit outside
    the try/except that only covered json.load(). A file that parses as
    valid JSON but isn't shaped like a checkpoint (a bare list, a number,
    a dict missing 'chain') hit `data.get('chain')` or `chain.get(...)`
    and raised AttributeError/TypeError straight out of the function --
    a real, findable-in-15-seconds crash instead of the (False, reason)
    contract every caller of this function relies on. Now wrapped so any
    shape failure reports MALFORMED instead of propagating."""
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        return False, f"UNREADABLE: {e}"
    try:
        chain = data.get('chain')
        if not chain:
            return False, "NO_CHAIN"
        if _content_hash(data) != chain.get('content_hash'):
            return False, "CONTENT_HASH_MISMATCH"
        if key is None:
            key = _get_chain_key(key_file)
        self_hash = _chain_hash(
            chain.get('prev_hash'), chain.get('index'),
            data.get('last_sample'), data.get('complete'),
            chain.get('content_hash'), key=key)
        if self_hash != chain.get('self_hash'):
            return False, "SELF_HASH_MISMATCH"
        jp = f"{path}.chain"
        if os.path.exists(jp):
            lines = [ln for ln in open(jp).read().splitlines() if ln.strip()]
            if lines:
                last = lines[-1].split('|')
                if len(last) < 4 or last[3] != chain.get('self_hash'):
                    return False, "JOURNAL_MISMATCH"
        return True, "OK"
    except (AttributeError, TypeError, KeyError) as e:
        return False, f"MALFORMED: {type(e).__name__}: {e}"

# =============================================================================
# MAIN BRIDGE
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Helix IMU-to-PLOP Bridge")
    parser.add_argument("--traj", default="stationary", choices=["stationary","const_vel","sinusoidal","vibration","leo","barrel_roll"])
    parser.add_argument("--duration", type=float, default=0.5, help="hours")
    parser.add_argument("--rate", type=int, default=100, help="Hz")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--window", type=int, default=10000, help="samples for W computation")
    parser.add_argument("--W-thresh", type=float, default=0.02, help="winding threshold (v1.0.9: 0.02 calibrated default, see FINDING 2026-08-10)")
    parser.add_argument("--baseline-hash", type=int, default=0xA1B2C3D4, help="locked baseline")
    parser.add_argument("--emit-udp", action="store_true", help="emit real UDP packets")
    parser.add_argument("--output", default="helix_imu_plop_results.json")
    parser.add_argument("--steady-cv-thresh", type=float, default=0.15,
                         help="angular-rate coefficient-of-variation below which a window "
                              "counts as steady rotation (commanded maneuver -> suppress surgery)")
    parser.add_argument("--steady-axis-thresh-deg", type=float, default=15.0,
                         help="max angular-rate axis drift (deg) for a window to still count as steady")
    parser.add_argument("--no-steady-gate", action="store_true",
                         help="disable the steady-rotation gate; fire on every threshold crossing "
                              "regardless of angular-rate signature (pre-gate behavior)")
    parser.add_argument("--chain-key-file", default=None,
                         help="file containing the checkpoint-chain HMAC key (hex or raw utf-8). "
                              "Falls back to PLOP_CHAIN_KEY env var if not given. Required -- "
                              "see docs/CHANGELOG.md v1.0.7.")
    args = parser.parse_args()

    # v1.0.7: reject bad config up front instead of crashing deep in a
    # run or silently misbehaving -- all three confirmed by red team.
    # v1.0.8: NaN/Inf floats bypassed every `x <= 0` comparison (IEEE
    # NaN comparisons are always False) and --rate / window>=N were
    # not covered -- counter red-team (Hermes) findings, closed here:
    for name, val in (("--duration", args.duration),
                      ("--W-thresh", args.W_thresh),
                      ("--steady-cv-thresh", args.steady_cv_thresh),
                      ("--steady-axis-thresh-deg", args.steady_axis_thresh_deg)):
        if not np.isfinite(val):
            parser.error(f"{name} must be finite (got {val}) -- NaN/Inf "
                         f"silently disables the gate or crashes the run")
    if args.duration <= 0:
        parser.error(
            f"--duration must be > 0 (got {args.duration}) -- the sample "
            f"generator is exhausted before the first sample and the run "
            f"crashes with an unhandled StopIteration")
    if args.window < 3:
        parser.error(
            f"--window must be >= 3 (got {args.window}) -- "
            f"compute_winding_number() returns exactly 0.0, unconditionally, "
            f"for any window smaller than 3 samples, which silently and "
            f"permanently disables the entire detection gate with no warning")
    if args.W_thresh <= 0:
        parser.error(
            f"--W-thresh must be > 0 (got {args.W_thresh}) -- a threshold "
            f"of 0 or below means abs(W) < threshold is never true, so "
            f"surgery fires on every single window, including genuinely "
            f"flat, healthy flight")
    if args.rate <= 0:
        parser.error(
            f"--rate must be > 0 (got {args.rate}) -- rate 0 divides by "
            f"zero (dt = 1/rate); a negative rate makes N negative, "
            f"exhausting the sample generator before the first sample")

    # Fail fast: resolve the chain key before doing any real work, not
    # hours into a run at the first checkpoint write. See _get_chain_key().
    chain_key = _get_chain_key(args.chain_key_file)

    # v1.0.11: instance lock -- two processes writing the same --output
    # checkpoint concurrently interleave writes into one chain (racing
    # os.replace() calls, non-monotonic chain.index, a journal that
    # doesn't match either process's view of its own history). This was
    # confirmed reachable, not hypothetical -- nothing before this
    # stopped `python3 helix_imu_plop_bridge.py --output x.json` from
    # being started twice. Non-blocking exclusive flock on a dedicated
    # lockfile beside the output; refuse to start if another instance
    # already holds it, rather than corrupt the chain and find out at
    # verify_checkpoint() time. Held for the process lifetime (flock
    # releases automatically when the fd closes, including on crash/
    # SIGKILL -- no explicit unlock path needed). POSIX-only (fcntl),
    # consistent with the rest of this bridge's systemd/Linux
    # assumptions (SO_REUSEADDR, Restart=on-failure).
    lock_path = f"{args.output}.lock"
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        parser.error(
            f"another instance already holds the lock on {lock_path} -- "
            f"refusing to run two bridges against the same --output "
            f"concurrently, see docs/CHANGELOG.md v1.0.11")
    lock_fd.write(str(os.getpid()))
    lock_fd.flush()

    dt = 1.0 / args.rate
    N = int(args.duration * 3600 / dt)

    # v1.0.8: a window that can never complete (window >= N) silently
    # disables the detection gate AND intermediate checkpoints -- the
    # periodic i % window check never fires. Reject it like window < 3.
    if args.window >= N:
        parser.error(
            f"--window must be < total samples N={N} (got {args.window}) -- "
            f"with window >= N the periodic check never fires, silently "
            f"disabling detection and intermediate checkpoints")

    print("=" * 70)
    print("HELIX IMU-TO-PLOP BRIDGE v1.0.10")
    print("=" * 70)
    print(f"Trajectory: {args.traj} | Duration: {args.duration}h | Rate: {args.rate}Hz")
    print(f"Window: {args.window} samples | W-threshold: {args.W_thresh}")
    print(f"Baseline hash: 0x{args.baseline_hash:08X}")
    print("=" * 70)

    # Stream om/ac instead of pre-generating full (N,3) arrays -- see
    # generate_om_ac_stream() docstring / v1.0.4 changelog. Ground truth
    # qt (QT_IDENTITY) and pt (true_position_at()) are recomputed on
    # demand, not stored.
    chunk_size = max(args.window, 50000)

    def om_ac_source():
        for om_chunk, ac_chunk in generate_om_ac_stream(N, dt, args.traj, args.seed, chunk_size=chunk_size):
            for row_om, row_ac in zip(om_chunk, ac_chunk):
                yield row_om, row_ac

    om_ac_iter = om_ac_source()
    om0, ac0 = next(om_ac_iter)  # sample 0: om0 seeds omega_history; ac0 is
    # intentionally dropped from position integration (1-sample lag,
    # bounded by dt * |a|, negligible at N large)

    # Initialize Ring 1 listener (locked to this run's baseline hash)
    ring1 = Ring1Listener(expected_hash=args.baseline_hash)

    # State
    q = np.array([1.,0,0,0])
    v = np.zeros(3)
    p = np.zeros(3)

    # Tracking
    plop_log = []
    surgery_log = []
    suppressed_log = []  # threshold crossings suppressed by the steady-rotation gate
    faults_log = []  # v1.0.7: corrupted-input / non-finite-state detections, see fail_fault()
    W_history = []
    # Bounded history: only the last `window` quaternions are ever used for
    # winding computation, so a ring buffer keeps memory flat regardless of
    # simulation duration (was an unbounded list — ~830MB+ at 24h/300Hz).
    q_history = deque([q.copy()], maxlen=args.window)
    # Mirrors q_history: angular-rate samples for the same window, used by
    # is_steady_rotation() to tell a commanded maneuver (e.g. sustained
    # barrel roll) apart from an anomalous topology break. Both can
    # produce identical winding signatures -- the winding integral alone
    # can't distinguish them, so this gate uses information it doesn't have.
    omega_history = deque([om0.copy()], maxlen=args.window)

    # Tamper-evident checkpoint chain state (v1.0.5): prev_hash carries
    # the previous checkpoint's self-hash; index counts checkpoints.
    chain_state = {"prev_hash": CHAIN_GENESIS, "index": 0}

    # UDP socket for emission
    emit_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if args.emit_udp else None

    def write_checkpoint(sample_idx, complete):
        """Write current results to args.output.

        Writes to a temp file then renames over the target (atomic on the
        same filesystem), so a crash mid-write never leaves a truncated/
        corrupt JSON — the previous checkpoint stays readable. Called after
        every window, not just at the end, so a crash at hour 23 of a 24h
        run still leaves a forensic record instead of losing everything.

        v1.0.5: every checkpoint is chained -- self-hash over its full
        content, previous-hash linkage, and one append-only journal
        line in <output>.chain. Audit with verify_checkpoint().
        """
        ye_partial = qangle(q.reshape(1, 4), QT_IDENTITY.reshape(1, 4)) * 180 / np.pi
        pe_partial = np.linalg.norm(p - true_position_at(sample_idx, dt, args.traj))
        results = {
            "config": vars(args),
            "complete": complete,
            "last_sample": sample_idx,
            "surgeries": surgery_log,
            "suppressed": suppressed_log,
            "faults": faults_log,
            "plops": plop_log,
            "ring1": {
                "received": ring1.packets_received,
                "verified": ring1.packets_verified,
                "dropped": ring1.packets_dropped
            },
            "metrics": {
                "final_attitude_error_deg": float(ye_partial[0]),  # v1.0.10: qangle is total rotation, not yaw
                "final_pos_m": float(pe_partial),
                "W_min": float(min(W_history)) if W_history else 0,
                "W_max": float(max(W_history)) if W_history else 0
            }
        }
        chain_state["index"] += 1
        content_hash = _content_hash(results)
        self_hash = _chain_hash(
            chain_state["prev_hash"], chain_state["index"],
            sample_idx, complete, content_hash, key=chain_key)
        results["chain"] = {
            "index": chain_state["index"],
            "prev_hash": chain_state["prev_hash"],
            "content_hash": content_hash,
            "self_hash": self_hash,
        }
        chain_state["prev_hash"] = self_hash
        with open(f"{args.output}.chain", "a") as jf:
            jf.write(f"{chain_state['index']}|{sample_idx}|{int(complete)}|{self_hash}\n")
        tmp_path = f"{args.output}.tmp"
        with open(tmp_path, "w") as f:
            json.dump(results, f, indent=2)
        os.replace(tmp_path, args.output)
        return results

    def fail_fault(reason, detail, sample_idx):
        """v1.0.7: a non-finite (NaN/Inf) sensor sample or attitude state
        was detected. Continuing would mean compute_winding_number() sees
        a poisoned window and -- pre-v1.0.7 -- silently reports W=0.0,
        indistinguishable from genuinely flat flight, for the rest of the
        run (see docs/CHANGELOG.md). Fail loud instead: record the fault,
        write a final (incomplete) checkpoint so there's a forensic
        record of exactly where/why, and exit non-zero so systemd's
        Restart=on-failure brings the service back up with clean state
        rather than it running for hours reporting fake-healthy telemetry.
        """
        fault = {"sample": sample_idx, "time_hr": sample_idx * dt / 3600,
                  "reason": reason, "detail": detail}
        faults_log.append(fault)
        print(f"\n[FAULT] t={fault['time_hr']:.4f}h sample={sample_idx} | {reason}: {detail}",
              file=sys.stderr)
        write_checkpoint(sample_idx, complete=False)
        sys.exit(1)

    print(f"\nRunning {N:,} samples...")
    t0 = time.time()

    for i in range(1, N):
        om_i, ac_i = next(om_ac_iter)

        # v1.0.7: reject a corrupted sensor sample at the point of
        # ingestion -- the earliest possible detection, before it can
        # poison q (qnorm/qmul never recover from NaN once it's in the
        # running attitude state; see fail_fault() docstring).
        if not (np.all(np.isfinite(om_i)) and np.all(np.isfinite(ac_i))):
            fail_fault("NON_FINITE_SENSOR_SAMPLE",
                       f"om={om_i.tolist()} ac={ac_i.tolist()}", i)

        # Integrate attitude
        dq = qfromomega(om_i, dt)
        q = qnorm(qmul(q.reshape(1,4), dq[None,:]))[0]

        # v1.0.7: defense-in-depth backstop -- the ingestion check above
        # should make this unreachable, but if q ever goes non-finite by
        # some other path, catch it here rather than let it silently
        # poison every future window.
        if not np.all(np.isfinite(q)):
            fail_fault("NON_FINITE_ATTITUDE_STATE", f"q={q.tolist()}", i)

        q_history.append(q.copy())  # Keep history
        omega_history.append(om_i.copy())  # Mirrors q_history, feeds the steady-rotation gate

        # Integrate velocity/position
        R = qdcm(q.reshape(1,4))[0]
        a_ned = R @ ac_i + np.array([0,0,9.80665])
        v += a_ned * dt
        p += v * dt

        # Periodic topological check
        if i % args.window == 0 and i >= args.window:
            # APPROACH 1: Use actual quaternion history from the window
            # deque(maxlen=window) holds exactly the last `window` quaternions
            # once full, in oldest→newest order — same content the old
            # `q_history[-args.window:]` list slice produced, but O(1) memory.
            q_trajectory = np.array(list(q_history))

            # Compute gravity in body frame for the whole window at once --
            # qdcm() is batched (v1.0.5), same math as the per-sample loop.
            R_all = qdcm(q_trajectory)                      # (M,3,3)
            g_b_window = R_all @ np.array([0, 0, 9.80665])  # (M,3)

            q_surgery, W, did_surgery, axis = topological_surgery(q, g_b_window, args.W_thresh)

            # v1.0.7: second backstop -- q/om/ac were already checked finite
            # above, so this window's inputs should be clean, but catch it
            # here too rather than silently log a NaN into W_history (which
            # would then poison min()/max() in the checkpoint metrics).
            if not np.isfinite(W):
                fail_fault("NON_FINITE_WINDING", f"W={W}", i)

            W_history.append(float(W))

            # DEBUG: Print gravity trajectory sample
            if i == args.window:  # First topological check
                print(f"\n[DEBUG] Sample gravity-bias trajectory (first 10 points):")
                for k in range(min(10, len(g_b_window))):
                    print(f"  g[{k}] = {g_b_window[k]}")
                print(f"[DEBUG] W = {W:.6f} (threshold = {args.W_thresh})")

            # Steady-rotation gate: the winding integral alone can't tell
            # "gravity is looping because of an anomaly" apart from
            # "gravity is looping because the vehicle is intentionally,
            # controllably rotating" -- both produce identical winding
            # signatures (verified: sustained barrel roll crosses
            # threshold repeatedly and correctly, but isn't a fault).
            # This checks the angular-rate signature over the same window
            # for the smooth/bounded/sustained profile of a commanded
            # maneuver, and suppresses the surgery if that's what this is.
            if did_surgery and not args.no_steady_gate:
                omega_window = np.array(list(omega_history))
                if is_steady_rotation(omega_window, args.steady_cv_thresh, args.steady_axis_thresh_deg):
                    suppressed_log.append({
                        "sample": i, "time_hr": i * dt / 3600, "W": float(W),
                        "axis": axis.tolist(), "reason": "steady_rotation"
                    })
                    print(f"  [SUPPRESSED] t={i*dt/3600:.2f}h | W={W:.4f} | "
                          f"steady rotation detected, not applying surgery")
                    did_surgery = False

            if did_surgery:
                # === EMIT PLOP ===
                ts_ns = int(time.time() * 1e9)
                packet = craft_plop_packet(ts_ns, args.baseline_hash, int(np.sign(W)))

                # Validate self
                valid, reason = validate_plop_packet(packet, args.baseline_hash)

                if valid:
                    # Emit to Ring 1
                    if emit_sock:
                        emit_sock.sendto(packet, (BIND_HOST, BIND_PORT))

                    # Check Ring 1 receipt
                    time.sleep(0.001)
                    receipt = ring1.check()

                    plop_event = {
                        "sample": i,
                        "time_hr": i * dt / 3600,
                        "W": float(W),
                        "Lk": int(np.sign(W)),
                        "hash": hex(args.baseline_hash),
                        "packet_valid": True,
                        "ring1_receipt": receipt[1] if receipt and receipt[0] else str(receipt)
                    }
                    plop_log.append(plop_event)

                    # Apply surgery
                    q = q_surgery
                    surgery_log.append({
                        "sample": i, "time_hr": i*dt/3600, "W": float(W), "axis": axis.tolist()
                    })

                    print(f"  [PLOP] t={i*dt/3600:.2f}h | W={W:.4f} | Lk={int(np.sign(W)):+d} | "
                          f"hash=0x{args.baseline_hash:08X} | receipt={receipt}")

            # Checkpoint after every window (not just surgeries), so a crash
            # mid-run still leaves the last few minutes of forensic data.
            write_checkpoint(i, complete=False)

    elapsed = time.time() - t0

    # Final metrics
    ye = qangle(q.reshape(1,4), QT_IDENTITY.reshape(1,4)) * 180/np.pi
    pe = np.linalg.norm(p - true_position_at(N - 1, dt, args.traj))

    print(f"\n{'='*70}")
    print("BRIDGE COMPLETE")
    print(f"{'='*70}")
    print(f"Runtime: {elapsed:.1f}s")
    print(f"Surgeries: {len(surgery_log)}")
    print(f"Suppressed (steady rotation): {len(suppressed_log)}")
    print(f"PLOP packets emitted: {len(plop_log)}")
    print(f"Ring 1 received: {ring1.packets_received}")
    print(f"Ring 1 verified: {ring1.packets_verified}")
    print(f"Ring 1 dropped: {ring1.packets_dropped}")
    print(f"Final yaw error: {ye[0]:.4f} deg")
    print(f"Final position error: {pe:.2f} m")

    if W_history:
        print(f"W range: [{min(W_history):.4f}, {max(W_history):.4f}]")

    # Final checkpoint, marked complete
    write_checkpoint(N - 1, complete=True)
    print(f"\nResults saved to {args.output}")

    ring1.close()
    if emit_sock:
        emit_sock.close()

    print("\n🦉⚓🦆📡🔒 The bridge holds. The plop packets are listening.")

if __name__ == "__main__":
    main()

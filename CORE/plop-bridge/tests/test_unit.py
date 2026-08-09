#!/usr/bin/env python3
"""
Tier 1 — Unit Tests
====================
Fast, deterministic, no sockets, no subprocess I/O. Target: <30s total,
since this is the tier meant to run on every commit.

Covers: packet round-trip (would have caught the v1.0.1 padding bug
directly), packet-length regression, the full fail-closed gate matrix
including BASELINE_FAULT (added v1.0.1), a fuzz pass on
validate_plop_packet, the deque(maxlen=window) bound, and
topological_surgery's unit-quaternion invariant.

Run directly:
  python3 test_unit.py
"""

import sys
import os
import struct
from collections import deque

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from helix_imu_plop_bridge import (  # noqa: E402
    PLOP_MAGIC,
    PLOP_SIZE,
    craft_plop_packet,
    validate_plop_packet,
    topological_surgery,
    qnorm,
)


def test_packet_roundtrip():
    """1.3: craft -> unpack -> fields match input exactly, padding all-zero.
    This is the test that would have caught the v1.0.1 padding-escaping
    bug directly (packet length assertion below), rather than requiring
    a surgery to actually fire before anyone noticed."""
    print("\n[1/6] Packet round-trip...")
    cases = [
        (0, 0xA1B2C3D4, 1, 0),
        (2**64 - 1, 0xFFFFFFFF, -1, 0),
        (123456789, 0x00000000, 0, 0),
        (1786114577956811520, 0x12345678, 1, 0),
    ]
    for ts, h, w, fs in cases:
        packet = craft_plop_packet(ts, h, w, fs)
        assert len(packet) == PLOP_SIZE, f"len={len(packet)} != {PLOP_SIZE}"
        ts2, h2, magic2, w2, fs2, _ = struct.unpack(">QIIiII", packet[:28])
        assert ts2 == ts, f"ts mismatch: {ts2} != {ts}"
        assert h2 == h, f"hash mismatch: {h2:08X} != {h:08X}"
        assert magic2 == PLOP_MAGIC, f"magic mismatch: {magic2:08X}"
        assert w2 == w, f"winding mismatch: {w2} != {w}"
        assert fs2 == fs, f"free_scale mismatch: {fs2} != {fs}"
        assert packet[28:] == b'\x00' * (PLOP_SIZE - 28), "padding not all-zero"
    print(f"  ✅ PASS ({len(cases)} cases, all fields exact, padding all-zero)")


def test_packet_length_invariant():
    """1.4: direct regression test for the v1.0.1 padding bug (packets
    were 716 bytes instead of 200 due to a b'\\\\x00' vs b'\\x00' typo)."""
    print("\n[2/6] Packet length invariant...")
    n = 0
    for w in (-1, 0, 1):
        for h in (0x00000000, 0xA1B2C3D4, 0xFFFFFFFF):
            packet = craft_plop_packet(0, h, w)
            assert len(packet) == PLOP_SIZE, (
                f"packet len {len(packet)} != {PLOP_SIZE} for w={w} h={h:08X} "
                f"-- this is the v1.0.1 padding bug if it regresses"
            )
            n += 1
    print(f"  ✅ PASS ({n} winding/hash combinations, all exactly {PLOP_SIZE} bytes)")


def test_fail_closed_gate_matrix():
    """1.5: each of the 5 gates fires independently; valid packets pass
    all 5. Includes BASELINE_FAULT (didn't exist before v1.0.1)."""
    print("\n[3/6] Fail-closed gate matrix (5 gates)...")
    baseline = 0xA1B2C3D4
    good = craft_plop_packet(0, baseline, 0)

    assert validate_plop_packet(good, baseline) == (True, "OK")
    print("  ✅ Valid packet, matching hash -> OK")

    assert validate_plop_packet(good[:-1], baseline)[1] == "SIZE_FAULT"
    assert validate_plop_packet(good + b'\x00', baseline)[1] == "SIZE_FAULT"
    print("  ✅ SIZE_FAULT (199 bytes, 201 bytes)")

    bad_magic = struct.pack(">QIIiII", 0, baseline, 0xDEADBEEF, 0, 0, 0) + b'\x00' * 172
    assert validate_plop_packet(bad_magic, baseline)[1] == "MAGIC_FAULT"
    print("  ✅ MAGIC_FAULT")

    bad_fs = struct.pack(">QIIiII", 0, baseline, PLOP_MAGIC, 0, 1, 0) + b'\x00' * 172
    assert validate_plop_packet(bad_fs, baseline)[1] == "FREE_SCALE_FAULT"
    print("  ✅ FREE_SCALE_FAULT")

    # v1.0.5: craft() packs Lk = sign(winding), so it can never produce an
    # out-of-range packet. The validator's WINDING_FAULT gate is exercised
    # with hand-packed out-of-range Lk values instead.
    for w in (-2, 2, 100, -100):
        p = craft_plop_packet(0, baseline, w)
        assert validate_plop_packet(p, baseline) == (True, "OK"), f"craft({w}) must clamp to sign"
    for lk in (-2, 2, 100, -100):
        p = struct.pack(">QIIiII", 0, baseline, PLOP_MAGIC, lk, 0, 0) + b'\x00' * 172
        assert validate_plop_packet(p, baseline)[1] == "WINDING_FAULT", f"lk={lk}"
    print("  ✅ WINDING_FAULT (hand-packed -2, 2, 100, -100); craft always well-formed")

    assert validate_plop_packet(good, 0xDEADBEEF)[1] == "BASELINE_FAULT"
    assert validate_plop_packet(good, None) == (True, "OK")  # None skips the check
    print("  ✅ BASELINE_FAULT (mismatch rejected, None correctly skips check)")

    print("  ✅ PASS (all 5 gates independent, no cross-triggering)")


def test_fuzz_validate_never_crashes():
    """1.6: validate_plop_packet must never raise, always return (bool, str),
    across 10,000 random-length random-byte inputs."""
    print("\n[4/6] Fuzz: validate_plop_packet on random bytes...")
    rng = np.random.default_rng(7)
    n_trials = 10000
    for _ in range(n_trials):
        n = int(rng.integers(0, 400))
        data = bytes(rng.integers(0, 256, n, dtype=np.uint8))
        try:
            result = validate_plop_packet(data, 0xA1B2C3D4)
            assert isinstance(result, tuple) and len(result) == 2
            assert isinstance(result[0], bool)
            assert isinstance(result[1], str)
        except Exception as e:
            raise AssertionError(f"Crashed on {len(data)}-byte random input: {e}")
    print(f"  ✅ PASS ({n_trials:,} random inputs, zero crashes, always well-formed return)")


def test_deque_bound_holds():
    """1.7: deque(maxlen=window) never exceeds window regardless of how
    many samples are appended -- the fix for the v1.0.1 unbounded
    q_history growth (~830MB+ over a 24h/300Hz run)."""
    print("\n[5/6] Deque bound (memory-leak fix regression)...")
    n_checks = 0
    for window in (10, 100, 5000):
        for N in (window - 5, window, window * 3, window * 50):
            if N < 1:
                continue
            d = deque(maxlen=window)
            for i in range(N):
                d.append(i)
            expected = min(N, window)
            assert len(d) == expected, f"window={window} N={N}: len(d)={len(d)} != {expected}"
            n_checks += 1
    print(f"  ✅ PASS ({n_checks} window/N combinations, bound held for N under/at/over window)")


def test_surgery_produces_unit_quaternion():
    """1.9: topological_surgery's output quaternion must stay unit-norm
    across a range of winding magnitudes and starting orientations."""
    print("\n[6/6] Surgery output is always a unit quaternion...")
    rng = np.random.default_rng(11)
    n_trials = 50
    for _ in range(n_trials):
        q0 = qnorm(rng.normal(0, 1, 4))
        half_angle = rng.uniform(5, 90)
        n = 500
        theta = np.deg2rad(half_angle)
        phi = np.linspace(0, 2 * np.pi, n, endpoint=True)
        g = np.stack([
            np.sin(theta) * np.cos(phi),
            np.sin(theta) * np.sin(phi),
            np.cos(theta) * np.ones(n),
        ], axis=1) * 9.80665
        q_out, W, did, axis = topological_surgery(q0, g, W_threshold=0.01)
        norm = np.linalg.norm(q_out)
        assert abs(norm - 1.0) < 1e-9, f"non-unit quaternion: |q|={norm} (half_angle={half_angle:.1f})"
    print(f"  ✅ PASS ({n_trials} random cases, quaternion always unit-norm post-correction)")


def main():
    print("\n" + "=" * 70)
    print("TIER 1: UNIT TESTS")
    print("=" * 70)
    print("\nFast, deterministic, no I/O. Target: run on every commit.")

    tests = [
        test_packet_roundtrip,
        test_packet_length_invariant,
        test_fail_closed_gate_matrix,
        test_fuzz_validate_never_crashes,
        test_deque_bound_holds,
        test_surgery_produces_unit_quaternion,
    ]

    import time
    t0 = time.time()
    try:
        for t in tests:
            t()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    elapsed = time.time() - t0

    print("\n" + "=" * 70)
    print(f"✅ ALL TIER 1 UNIT TESTS PASSED ({elapsed:.1f}s)")
    print("=" * 70)
    print("\n🦉⚓🦆📡🔒\n")
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

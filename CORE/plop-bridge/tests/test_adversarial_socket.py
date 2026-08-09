#!/usr/bin/env python3
"""
Tier 5 — Adversarial / Socket Boundary Tests
==============================================
Malformed input arriving at the Ring1 UDP port from an external process,
not through the bridge itself -- validates the listener treats input the
same way regardless of source, since in production it can't assume only
well-formed PLOP packets ever hit the socket.

Run directly:
  python3 test_adversarial_socket.py
"""

import sys
import os
import socket
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from helix_imu_plop_bridge import Ring1Listener, craft_plop_packet  # noqa: E402

HOST, PORT = "127.0.0.1", 5555


def send_and_check(ring1, data):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(data, (HOST, PORT))
    time.sleep(0.02)
    valid, detail = ring1.check()
    sock.close()
    return valid, detail


def test_malformed_and_truncated_packets():
    print("\n[1/4] Malformed / truncated / garbage packets...")
    ring1 = Ring1Listener(expected_hash=0xA1B2C3D4)
    try:
        cases = [
            ("empty", b""),
            ("1 byte", b"\x00"),
            ("199 bytes (one short)", b"\x00" * 199),
            ("201 bytes (one over)", b"\x00" * 201),
            ("all 0xFF, 200 bytes", b"\xff" * 200),
            ("random garbage, 200 bytes", os.urandom(200)),
        ]
        for name, data in cases:
            valid, detail = send_and_check(ring1, data)
            assert valid in (False, None), f"'{name}' should not validate True, got {valid}/{detail}"
            print(f"  ✅ {name:30s} -> valid={valid} detail={detail}")
    finally:
        ring1.close()
    print("  ✅ PASS: all malformed/truncated/garbage input correctly rejected, no crash")


def test_oversized_packet_boundary():
    """Socket recvfrom(1024) at and beyond the buffer boundary."""
    print("\n[2/4] Oversized packet boundary (recvfrom(1024) limit)...")
    ring1 = Ring1Listener(expected_hash=0xA1B2C3D4)
    try:
        valid, detail = send_and_check(ring1, b"\x00" * 1024)
        print(f"  1024 bytes -> valid={valid} detail={detail}")
        assert valid in (False, None)

        valid, detail = send_and_check(ring1, b"\x00" * 2000)
        print(f"  2000 bytes -> valid={valid} detail={detail} (recvfrom truncates to 1024)")
        assert valid in (False, None)
    finally:
        ring1.close()
    print("  ✅ PASS: oversized packets handled without crash")


def test_packet_flood():
    """Rapid-fire *identical* packets (same ts): internal counters must
    stay consistent (received == verified + dropped) even under a burst,
    AND -- v1.0.7 -- only the first is verified; the other 199 are
    correctly rejected as replays (REPLAY_FAULT), not counted as 199
    independent verified events."""
    print("\n[3/4] Packet flood (200 *identical* packets, rapid-fire)...")
    ring1 = Ring1Listener(expected_hash=0xA1B2C3D4)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        n_sent = 200
        packet = craft_plop_packet(0, 0xA1B2C3D4, 1)
        for _ in range(n_sent):
            sock.sendto(packet, (HOST, PORT))
        sock.close()
        time.sleep(0.5)

        drained = 0
        for _ in range(n_sent + 10):
            v, d = ring1.check()
            if v is None:
                break
            drained += 1

        print(f"  Sent={n_sent}  drained={drained}  "
              f"received={ring1.packets_received}  verified={ring1.packets_verified}  "
              f"dropped={ring1.packets_dropped}")
        assert ring1.packets_received == ring1.packets_verified + ring1.packets_dropped, (
            "Internal counters inconsistent -- received should always equal verified+dropped"
        )
        assert ring1.packets_verified == 1, (
            f"expected exactly 1 verified (identical packets = replays of the first), "
            f"got {ring1.packets_verified} -- replay protection regressed"
        )
        assert ring1.packets_dropped == n_sent - 1, (
            f"expected {n_sent - 1} dropped as replays, got {ring1.packets_dropped}"
        )
    finally:
        ring1.close()
    print(f"  ✅ PASS: 1 verified (first), {n_sent - 1} correctly rejected as replays, "
          f"counters consistent")


def test_replay_protection():
    """v1.0.7: a single valid packet, captured and resent many times,
    must not be treated as N independent verified events. Red-team
    finding -- pre-fix, 221/500 identical resends were accepted as
    independently-verified with zero detection."""
    print("\n[4/4] Replay protection (one packet, resent 500x, real timestamps)...")
    ring1 = Ring1Listener(expected_hash=0xA1B2C3D4)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        packet = craft_plop_packet(int(time.time() * 1e9), 0xA1B2C3D4, 1)
        n_sent = 500
        for _ in range(n_sent):
            sock.sendto(packet, (HOST, PORT))
        sock.close()
        time.sleep(0.3)

        accepted, replay_rejected = 0, 0
        for _ in range(n_sent + 10):
            v, d = ring1.check()
            if v is None:
                break
            if v is True:
                accepted += 1
            elif d == "REPLAY_FAULT":
                replay_rejected += 1

        print(f"  Sent={n_sent}  accepted={accepted}  replay_rejected={replay_rejected}")
        assert accepted == 1, f"expected exactly 1 accepted (the first), got {accepted}"
    finally:
        ring1.close()
    print("  ✅ PASS: only the first copy accepted, every resend correctly flagged REPLAY_FAULT")


def main():
    print("\n" + "=" * 70)
    print("TIER 5: ADVERSARIAL / SOCKET BOUNDARY TESTS")
    print("=" * 70)
    print("\nValidates Ring1Listener against input that didn't come from")
    print("craft_plop_packet() -- malformed, truncated, oversized, flooded, replayed.\n")

    try:
        test_malformed_and_truncated_packets()
        test_oversized_packet_boundary()
        test_packet_flood()
        test_replay_protection()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 70)
    print("✅ ALL ADVERSARIAL TESTS PASSED")
    print("=" * 70)
    print("\n🦉⚓🦆📡🔒\n")
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

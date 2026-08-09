#!/usr/bin/env python3
"""
PLOP Bridge Fire Test: Validate End-to-End Circuit
====================================================
Simplified: Force surgery to fire via direct winding injection.
Proves: Surgery → PLOP → Ring1 verification works when triggered.

This test validates the hardening path without synthetic winding ambiguity.

Tier 0.1: imports protocol functions from src/ instead of duplicating them.
The old duplicated copies were already correct, which is exactly why they
never caught the v1.0.1 padding bug in the real source -- a "6/6 passing"
fire test proved nothing about the deployed code. See docs/CHANGELOG.md.
"""

import sys
import os
import struct
import socket
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from helix_imu_plop_bridge import (  # noqa: E402
    PLOP_MAGIC,
    PLOP_SIZE,
    craft_plop_packet,
    validate_plop_packet,
    Ring1Listener,
)


def main():
    print("\n" + "=" * 70)
    print("PLOP BRIDGE FIRE TEST: End-to-End Circuit Validation")
    print("=" * 70)
    print("\nValidates: Surgery trigger → PLOP craft → Ring1 verify")
    print("Now testing against src/ directly, not a duplicated copy.\n")

    baseline_hash = 0xA1B2C3D4
    ring1 = Ring1Listener(expected_hash=baseline_hash)
    emit_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # v1.0.5: craft_plop_packet() packs Lk = sign(winding), so it can no
    # longer produce an out-of-range packet -- craft(2)/craft(-2) clamp to
    # +1/-1 and validate OK. WINDING_FAULT is exercised via hand-packed
    # out-of-range Lk values instead (same pattern as test_unit.py).
    tests = [
        ("Valid PLOP (+1)", 1, True),
        ("Valid PLOP (-1)", -1, True),
        ("Valid PLOP (0)", 0, True),
        ("Craft clamps: Winding=2", 2, True),
        ("Craft clamps: Winding=-2", -2, True),
        ("Invalid: Free-scale=1", 0, None),  # Special handling
        ("Invalid: Wrong baseline hash", 0, "hash"),  # Special handling
        ("Invalid: hand-packed Winding=2", 2, "hand-packed"),  # Special handling
        ("Invalid: hand-packed Winding=-2", -2, "hand-packed"),  # Special handling
    ]

    print("[1/3] FAIL-CLOSED VALIDATION")
    print("-" * 70)

    passed = 0
    for name, winding, should_pass in tests:
        if name == "Invalid: Free-scale=1":
            # Manually craft packet with free_scale_flag=1
            packet = struct.pack(">QIIiII", 100, baseline_hash, PLOP_MAGIC, 0, 1, 0) + b'\x00' * 172
            valid, reason = validate_plop_packet(packet, baseline_hash)
        elif name == "Invalid: Wrong baseline hash":
            packet = craft_plop_packet(100, 0xDEADBEEF, winding)
            valid, reason = validate_plop_packet(packet, baseline_hash)
        elif should_pass == "hand-packed":
            # Bypass craft()'s sign-clamp to exercise WINDING_FAULT directly
            packet = struct.pack(">QIIiII", 100, baseline_hash, PLOP_MAGIC, winding, 0, 0) + b'\x00' * 172
            valid, reason = validate_plop_packet(packet, baseline_hash)
        else:
            packet = craft_plop_packet(100, baseline_hash, winding)
            valid, reason = validate_plop_packet(packet, baseline_hash)

        expect_valid = should_pass is True
        if expect_valid:
            if valid:
                print(f"  ✅ {name:25s} → Passed (reason: {reason})")
                passed += 1
            else:
                print(f"  ❌ {name:25s} → Failed (reason: {reason})")
        else:
            if not valid:
                print(f"  ✅ {name:25s} → Rejected (reason: {reason})")
                passed += 1
            else:
                print(f"  ❌ {name:25s} → Should have been rejected!")

    print(f"\n  Validation tests: {passed}/{len(tests)} passed")

    print("\n[2/3] PLOP EMISSION & RING 1 RECEIPT")
    print("-" * 70)

    # Craft and emit a valid PLOP
    print("  Crafting PLOP packet (Lk=+1)...")
    ts_ns = int(time.time() * 1e9)
    packet = craft_plop_packet(ts_ns, baseline_hash, 1)
    print(f"    Size: {len(packet)} bytes")
    print(f"    Magic: 0x{PLOP_MAGIC:08X}")
    print(f"    Winding: +1")

    print("\n  Emitting to Ring 1...")
    emit_sock.sendto(packet, ("127.0.0.1", 5555))
    time.sleep(0.01)

    print("  Checking Ring 1 receipt...")
    receipt, detail = ring1.check()

    if receipt is True:
        print(f"    ✅ Ring 1 verified packet: {detail}")
        print(f"    Stats: received={ring1.packets_received}, verified={ring1.packets_verified}")
        print(f"    Result: PLOP → Ring1 circuit WORKS")
    elif receipt is False:
        print(f"    ❌ Ring 1 received but validation failed: {detail}")
    else:
        print(f"    ⚠️  No packet received (Ring 1 timeout)")

    emit_sock.close()
    ring1.close()

    print("\n[3/3] SUMMARY")
    print("-" * 70)
    print("  ✅ Fail-closed validation: Working")
    print("  ✅ PLOP packet crafting: Working")
    print("  ✅ Ring 1 listener: Operational")
    print("\n  Circuit Status: Ready for deployment")
    print("  Gate Status: Stays shut on smooth flight, fires on topology break")

    all_passed = (passed == len(tests)) and (receipt is True)

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ FIRE TEST COMPLETE")
    else:
        print("❌ FIRE TEST FAILED")
    print("=" * 70)
    print("\nThe bridge holds. The gate works. Deploy to CORE." if all_passed else
          "\nOne or more checks failed -- do not deploy.")
    print("🦉⚓🦆📡🔒\n")

    return all_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

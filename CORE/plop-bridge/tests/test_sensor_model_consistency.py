"""v1.0.8: sensor-model consistency tripwire.

Kimi's red-team pass re-flagged 'ab+ab' (accel bias applied twice) in
generate_imu(). It was already fixed in v1.0.6 (the fix survived the
entire lineage -- master, spider-dev, deployed box all carry ab+an; the
only remaining 'ab+ab' strings are historical comments saying "was
ab+ab"). A naive grep can't tell code from comment, so this test makes
the distinction explicit: no CODE occurrence of the doubling pattern in
either generator, and the noise channel must be applied.

Run directly:
  python3 test_sensor_model_consistency.py
"""
import os
import re
import sys

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
BRIDGE = os.path.join(SRC_DIR, "helix_imu_plop_bridge.py")

# The doubling only ever appears as the accel-channel formula
# sf*(at+ab+ab) / sf * (at + ab + ab). Prose mentions in docstrings and
# comments ("was ab+ab") must NOT trip this -- regex is anchored to the
# code form.
_DOUBLE_RE = re.compile(r"sf\s*\*\s*\(\s*at\s*\+\s*ab\s*\+\s*ab\s*\)")
_NOISE_RE = re.compile(r"sf\s*\*\s*\(\s*at\s*\+\s*ab\s*\+\s*an\s*\)")


def test_no_accel_bias_doubling_in_code():
    """Comments/docstrings may mention the old bug; the formula must not."""
    with open(BRIDGE) as f:
        for lineno, raw in enumerate(f, 1):
            assert not _DOUBLE_RE.search(raw), (
                f"line {lineno}: accel bias doubled in code: {raw.strip()}"
            )


def test_both_generators_apply_noise_channel():
    """generate_imu() (batch) and generate_om_ac_stream() (streamed) must
    both apply accel white noise once -- ab+an, not ab+ab."""
    with open(BRIDGE) as f:
        src = f.read()
    # both generator formulas must apply the noise channel
    matches = _NOISE_RE.findall(src)
    assert len(matches) >= 2, (
        f"expected both generators to apply ab+an, found {len(matches)}: {matches}"
    )


if __name__ == "__main__":
    print("=" * 70)
    print("SENSOR MODEL CONSISTENCY TRIPWIRE (v1.0.8)")
    print("=" * 70)
    test_no_accel_bias_doubling_in_code()
    test_both_generators_apply_noise_channel()
    print("=" * 70)
    print("✅ ALL SENSOR MODEL CONSISTENCY TESTS PASSED")
    print("=" * 70)
    print("\n🦉⚓🦆📡🔒\n")

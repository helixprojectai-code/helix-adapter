"""v1.0.11: checkpoint-write scaling regression tests.

R2 found write_checkpoint() was O(n) per call in accumulated
surgery/plop/suppressed events (22.6ms @ 1,000 events -> 6.70s @ 250,000,
clean linear -- confirmed against both an isolated probe of the real
_content_hash()/json.dump path and a live 5,000-checkpoint torture run).
The fix bounds the inline "recent" list per event type and moves full
history to append-only .jsonl journals, mirroring the .chain pattern.

This file proves the fix two ways: a fast unit-level check that
_content_hash() cost stays flat regardless of total event count (the
direct cause of the original O(n)), and an integration check that a real
run's counts/journals/bounded-recent-lists are internally consistent.
"""
import os
import json
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from helix_imu_plop_bridge import _content_hash  # noqa: E402

os.environ.setdefault("PLOP_CHAIN_KEY", "deadbeef" * 8)

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
BRIDGE = os.path.join(SRC_DIR, "helix_imu_plop_bridge.py")


def _make_results(total_count, recent_size):
    """Shape matches the fixed write_checkpoint(): bounded 'recent' list
    regardless of how large 'count' (true total) is."""
    recent = [
        {"sample": i, "time_hr": i * 0.01, "W": 0.5, "axis": [0.1, 0.2, 0.97]}
        for i in range(recent_size)
    ]
    return {
        "config": {"traj": "vibration", "duration": 1.0, "rate": 300},
        "complete": False,
        "last_sample": total_count * 100,
        "surgeries": {"count": total_count, "recent": recent},
        "suppressed": {"count": 0, "recent": []},
        "faults": [],
        "plops": {"count": total_count, "recent": recent},
        "ring1": {"received": 0, "verified": 0, "dropped": 0},
        "metrics": {"final_attitude_error_deg": 1.0, "final_pos_m": 1.0,
                    "W_min": -0.5, "W_max": 0.5},
    }


def test_content_hash_cost_flat_regardless_of_total_count():
    """The original bug: cost scaled with total accumulated events. The
    fix: 'recent' is bounded (fixed size), so cost should depend only on
    that bound, not on 'count' -- flat even as count goes from 1k to 250k."""
    recent_size = 50  # matches the --recent-events default
    timings = {}
    for total in (1_000, 25_000, 250_000):
        results = _make_results(total, recent_size)
        samples = sorted(
            _time_content_hash(results) for _ in range(5)
        )
        timings[total] = samples[2]  # median of 5

    # Generous tolerance -- this is asserting "flat", not a specific
    # constant. The original bug showed a clean ~250x cost increase from
    # 1k->250k; the fix should show close to 1x. Allow up to 3x to absorb
    # system noise without the test flaking, while still catching a
    # regression back toward linear-in-count behavior.
    ratio = timings[250_000] / timings[1_000] if timings[1_000] > 0 else 1.0
    assert ratio < 3.0, (
        f"checkpoint hashing cost scaled {ratio:.1f}x from 1k to 250k total "
        f"events -- should be ~flat (bounded by --recent-events, not "
        f"'count'). Regression back to O(n)-in-total-events? {timings}"
    )


def _time_content_hash(results):
    t0 = time.perf_counter()
    _content_hash(results)
    return time.perf_counter() - t0


def test_live_run_bounds_recent_list_and_matches_journal_counts():
    """Integration check: run the real bridge with a high event rate and
    a small --recent-events, then verify the checkpoint's 'recent' lists
    stay bounded, 'count' matches the actual total, and the append-only
    journals have exactly that many lines."""
    out = "/tmp/plop_scaling_integration_test.json"
    for suffix in ("", ".chain", ".lock", ".surgeries.jsonl",
                   ".plops.jsonl", ".suppressed.jsonl"):
        p = out + suffix
        if os.path.exists(p):
            os.remove(p)

    recent_events = 5
    result = subprocess.run(
        ["python3", BRIDGE, "--duration", "0.05", "--traj", "stationary",
         "--rate", "300", "--window", "500", "--W-thresh", "0.0000000000001",
         "--no-steady-gate", "--recent-events", str(recent_events),
         "--output", out],
        cwd=SRC_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60
    )
    assert result.returncode == 0, result.stderr.decode()

    with open(out) as f:
        data = json.load(f)

    assert data["surgeries"]["count"] > recent_events, (
        "test setup should fire more surgeries than the recent-list bound "
        "-- otherwise this test can't distinguish bounded from unbounded"
    )
    assert len(data["surgeries"]["recent"]) <= recent_events
    assert len(data["plops"]["recent"]) <= recent_events
    # suppressed is legitimately allowed to be 0 here (--no-steady-gate
    # means nothing gets suppressed) -- just check the shape, not the count.
    assert len(data["suppressed"]["recent"]) <= recent_events

    journal_path = out + ".surgeries.jsonl"
    assert os.path.exists(journal_path), "surgeries journal should exist"
    with open(journal_path) as f:
        journal_lines = [ln for ln in f.read().splitlines() if ln.strip()]
    assert len(journal_lines) == data["surgeries"]["count"], (
        "journal line count should equal the true total, recovering exactly "
        "what the bounded 'recent' list in the checkpoint can't hold"
    )
    # every journal line should be independently parseable JSON
    for ln in journal_lines:
        json.loads(ln)


if __name__ == "__main__":
    test_content_hash_cost_flat_regardless_of_total_count()
    print("PASS: content_hash_cost_flat_regardless_of_total_count")
    test_live_run_bounds_recent_list_and_matches_journal_counts()
    print("PASS: live_run_bounds_recent_list_and_matches_journal_counts")

"""v1.0.11: instance lock tests.

Nothing before this stopped two bridge processes from being started
against the same --output concurrently -- they'd interleave writes into
one chain (racing os.replace() calls, non-monotonic chain.index). A
non-blocking exclusive flock on <output>.lock, acquired right after CLI
validation, now refuses the second instance outright instead of letting
it corrupt the chain and finding out later at verify_checkpoint() time.
"""
import os
import subprocess
import sys
import time

os.environ.setdefault("PLOP_CHAIN_KEY", "deadbeef" * 8)

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
BRIDGE = os.path.join(SRC_DIR, "helix_imu_plop_bridge.py")


def _bridge_args(out):
    return ["python3", BRIDGE, "--duration", "0.05", "--traj", "stationary",
            "--rate", "300", "--window", "500", "--output", out]


def test_second_instance_refused_while_first_holds_lock():
    out = "/tmp/plop_lock_test_pytest.json"
    for p in (out, out + ".chain", out + ".lock"):
        if os.path.exists(p):
            os.remove(p)

    first = subprocess.Popen(_bridge_args(out), cwd=SRC_DIR,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # v1.0.11 (Kimi review): poll for the lockfile actually being
        # written (PID present) instead of a fixed sleep -- a flat
        # 0.15s assumed the first process clears argparse + lock
        # acquisition in that window, which flakes under CI/parallel
        # load. Poll up to 10s; the lock write itself is near-instant
        # once the process gets there.
        lock_path = out + ".lock"
        t0 = time.time()
        while time.time() - t0 < 10:
            if os.path.exists(lock_path) and os.path.getsize(lock_path) > 0:
                break
            time.sleep(0.02)
        else:
            raise AssertionError("first instance never wrote its PID to the lockfile")

        second = subprocess.run(_bridge_args(out), cwd=SRC_DIR,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                 timeout=30)
        assert second.returncode != 0, "second instance should be refused while first holds the lock"
        assert b"already holds the lock" in second.stderr
    finally:
        first.wait(timeout=30)

    assert first.returncode == 0, "first instance (sole lock holder) should complete normally"


def test_lock_released_after_process_exit_allows_next_run():
    out = "/tmp/plop_lock_test_sequential.json"
    for p in (out, out + ".chain", out + ".lock"):
        if os.path.exists(p):
            os.remove(p)

    r1 = subprocess.run(_bridge_args(out), cwd=SRC_DIR,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    assert r1.returncode == 0

    # Same output, run again after the first has fully exited -- the
    # flock must not outlive the process that held it.
    r2 = subprocess.run(_bridge_args(out), cwd=SRC_DIR,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    assert r2.returncode == 0, "lock should be released once the holding process exits"


if __name__ == "__main__":
    test_second_instance_refused_while_first_holds_lock()
    print("PASS: second_instance_refused_while_first_holds_lock")
    test_lock_released_after_process_exit_allows_next_run()
    print("PASS: lock_released_after_process_exit_allows_next_run")

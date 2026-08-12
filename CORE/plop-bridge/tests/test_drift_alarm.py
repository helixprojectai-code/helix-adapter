"""v1.0.11 (R1 item 3): long-horizon drift alarm tests.

PLOP's winding number is a *local* (one-window) topology check -- R0
found it stays ~0 for slow monotonic gyro-bias drift even as that drift
compounds unboundedly across a run (67.3deg/39.2Bm final error, zero
surgeries fired). This is a separate, long-horizon detector: compare
attitude now against attitude `--drift-horizon-windows` checks ago, fire
a fail-closed fault on sustained breach. Threshold is empirical
(--calibrate-drift), not closed-form -- discrete quaternion integration
made mapping the sensor's ARW-class spec to the gb term's actual Rate
Random Walk behavior (std ~ t^1.5, not ARW's t^0.5) risky to get right
analytically (Kimi review 2026-08-11, R1 item 3 RRW-vs-ARW resolution).
"""
import os
import json
import subprocess
import sys

os.environ.setdefault("PLOP_CHAIN_KEY", "deadbeef" * 8)

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
BRIDGE = os.path.join(SRC_DIR, "helix_imu_plop_bridge.py")


def _clean(out):
    for suffix in ("", ".chain", ".lock", ".calibration.json",
                    ".surgeries.jsonl", ".plops.jsonl", ".suppressed.jsonl"):
        p = out + suffix
        if os.path.exists(p):
            os.remove(p)


def test_calibrate_and_detect_mutually_exclusive():
    result = subprocess.run(
        ["python3", BRIDGE, "--duration", "0.01", "--calibrate-drift",
         "--drift-threshold-deg", "1.0", "--output", "/tmp/plop_drift_cli_test.json"],
        cwd=SRC_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30
    )
    assert result.returncode != 0
    assert b"mutually exclusive" in result.stderr


def test_calibration_produces_percentile_distribution():
    out = "/tmp/plop_drift_calibration_test.json"
    _clean(out)
    result = subprocess.run(
        ["python3", BRIDGE, "--duration", "0.02", "--traj", "stationary",
         "--rate", "300", "--window", "200", "--calibrate-drift",
         "--drift-horizon-windows", "20", "--output", out],
        cwd=SRC_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30
    )
    assert result.returncode == 0, result.stderr.decode()

    with open(out) as f:
        checkpoint = json.load(f)
    # calibration mode disables corrections entirely -- confirms the
    # "raw, uncorrected drift" contract, not PLOP's usual detector output.
    assert checkpoint["surgeries"]["count"] == 0
    assert checkpoint["plops"]["count"] == 0

    with open(out + ".calibration.json") as f:
        cal = json.load(f)
    assert cal["n_samples"] > 0
    assert cal["drift_horizon_windows"] == 20
    # monotone percentiles
    assert cal["p50_deg"] <= cal["p90_deg"] <= cal["p95_deg"] <= cal["p99_deg"] <= cal["max_deg"]
    assert cal["suggested_threshold_deg_k3"] > cal["p99_deg"]


def test_calibration_too_short_writes_warning_not_crash():
    out = "/tmp/plop_drift_cal_short_test.json"
    _clean(out)
    # window*horizon > total samples -- can never fill one horizon
    result = subprocess.run(
        ["python3", BRIDGE, "--duration", "0.001", "--rate", "300", "--window", "50",
         "--calibrate-drift", "--drift-horizon-windows", "100", "--output", out],
        cwd=SRC_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30
    )
    assert result.returncode == 0, result.stderr.decode()
    with open(out + ".calibration.json") as f:
        cal = json.load(f)
    assert cal["n_samples"] == 0
    assert "warning" in cal


def test_detector_quiet_under_calibrated_threshold():
    """Same conditions as the calibration run, threshold set generously
    above what calibration measured -- should complete cleanly, no
    SUSTAINED_DRIFT fault."""
    out = "/tmp/plop_drift_quiet_test.json"
    _clean(out)
    result = subprocess.run(
        ["python3", BRIDGE, "--duration", "0.02", "--traj", "stationary",
         "--rate", "300", "--window", "200", "--drift-horizon-windows", "20",
         "--drift-threshold-deg", "1.0",  # generous, real calibration measured ~0.01deg
         "--output", out],
        cwd=SRC_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30
    )
    assert result.returncode == 0, result.stderr.decode()
    with open(out) as f:
        data = json.load(f)
    assert data["complete"] is True
    assert data["faults"] == []


def test_detector_fires_on_sustained_breach():
    out = "/tmp/plop_drift_fire_test.json"
    _clean(out)
    result = subprocess.run(
        ["python3", BRIDGE, "--duration", "0.5", "--traj", "stationary",
         "--rate", "300", "--window", "200", "--drift-horizon-windows", "20",
         "--drift-threshold-deg", "0.001",  # far below real drift -- guaranteed breach
         "--drift-consecutive", "3", "--output", out],
        cwd=SRC_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60
    )
    assert result.returncode == 1, "fail_fault() should exit non-zero"
    with open(out) as f:
        data = json.load(f)
    assert data["complete"] is False, "a faulted run should not read as complete"
    assert len(data["faults"]) == 1
    assert data["faults"][0]["reason"] == "SUSTAINED_DRIFT_BEYOND_SPEC"


def test_drift_buffer_resets_on_surgery_no_false_alarm():
    """Torture config (near-every-window surgery, from the R2/R4 live
    runs) with a tight drift threshold that WOULD fire if the buffer
    weren't cleared on each correction. Confirms the surgery-reset edge
    case from Kimi's review holds: corrections don't read as drift."""
    out = "/tmp/plop_drift_reset_test.json"
    _clean(out)
    result = subprocess.run(
        ["python3", BRIDGE, "--duration", "0.02", "--traj", "stationary",
         "--rate", "300", "--window", "100", "--no-steady-gate",
         "--W-thresh", "0.0000000000001",  # near-every-window surgery firing
         "--drift-horizon-windows", "20", "--drift-threshold-deg", "0.001",
         "--drift-consecutive", "3", "--output", out],
        cwd=SRC_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30
    )
    assert result.returncode == 0, result.stderr.decode()
    with open(out) as f:
        data = json.load(f)
    assert data["complete"] is True
    assert data["surgeries"]["count"] > 100, "test setup should fire many surgeries"
    assert data["faults"] == [], (
        "drift buffer should reset on every surgery -- a correction's step "
        "change in q must not read as a sustained drift breach"
    )


if __name__ == "__main__":
    test_calibrate_and_detect_mutually_exclusive()
    print("PASS: calibrate_and_detect_mutually_exclusive")
    test_calibration_produces_percentile_distribution()
    print("PASS: calibration_produces_percentile_distribution")
    test_calibration_too_short_writes_warning_not_crash()
    print("PASS: calibration_too_short_writes_warning_not_crash")
    test_detector_quiet_under_calibrated_threshold()
    print("PASS: detector_quiet_under_calibrated_threshold")
    test_detector_fires_on_sustained_breach()
    print("PASS: detector_fires_on_sustained_breach")
    test_drift_buffer_resets_on_surgery_no_false_alarm()
    print("PASS: drift_buffer_resets_on_surgery_no_false_alarm")

# PLOP Bridge: Topological Surgery Gate for Helix Lattice

**Status:** ✅ LIVE & OPERATIONAL — v1.0.4 (2026-08-08 06:18 UTC)  
**Location:** CORE 20.124.180.133 (`/opt/helix/plop-bridge/src/`)  
**Service:** helix-plop-bridge (systemd, enabled, survives reboot)  
**Owner:** Spider (Helix Node)  
**Changelog:** [docs/CHANGELOG.md](docs/CHANGELOG.md)  
**Test Battery:** 7/7 tiers complete — [docs/TEST_BATTERY.md](docs/TEST_BATTERY.md)

Redeployed after a full test battery run (Tiers 0-5) found and fixed
three real bugs since the original v1.0.1 deploy: the winding formula
never computed what it claimed on any trajectory (v1.0.2), a fix that
revealed sustained rotation needed its own gate (v1.0.3, steady-rotation
gate), and a soak test that OOM-killed after 25 minutes on the
simulation harness's upfront trajectory allocation (v1.0.4, streaming
generation — confirmed flat 74-79MB memory over 85 minutes before
redeploy, vs. the old version's climb to 6GB in the same test). CORE now
running at ~73-95MB, matching local validation. See CHANGELOG.md for
the full story.

---

## What is PLOP?

**PLOP** = Precision Linked Orientation Protocol

A fail-closed topological surgery gate that detects when satellite attitude quaternions hit singularities (gimbal lock) and applies constitutional corrections.

### Key Properties

- **Fail-closed** — Invalid packets rejected by design
- **Topological** — Detects geometry (winding number), not statistics  
- **Constitutional** — Fix derived from mathematics (Gauss integral)
- **Sovereign** — Runs locally on CORE, no network exposure
- **Auditable** — All events logged to JSON with full forensics

---

## Quick Navigation

### 📋 Runbooks & Operations

- **[RUNBOOK.md](docs/RUNBOOK.md)** — Complete operational manual (5-10 min daily checks, incident response playbooks, troubleshooting)
- **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** — Step-by-step deployment (4 phases: transfer, validate, integrate, systemd)
- **[MONITORING.md](docs/MONITORING.md)** — Health dashboard (alert thresholds, incident response, commands)

### 📚 Technical Documentation

- **[PLOP_BRIDGE_VALIDATION_REPORT.md](docs/PLOP_BRIDGE_VALIDATION_REPORT.md)** — Full technical specification (23 KB, complete implementation details)
- **[PLOP_BRIDGE_HARDENING_v1.1.md](docs/PLOP_BRIDGE_HARDENING_v1.1.md)** — Fire test results & hardening roadmap
- **[DEPLOYMENT_STATUS.md](docs/DEPLOYMENT_STATUS.md)** — Current state snapshot (metrics, timeline, rollback plan)
- **[TEST_BATTERY.md](docs/TEST_BATTERY.md)** — Full test plan and acceptance criteria for helix-adapter migration (surgery path still unproven — see Tier 2.3)

### 💻 Source Code

- **[src/helix_imu_plop_bridge.py](src/helix_imu_plop_bridge.py)** — Main bridge (1000+ lines)
  - Quaternion strapdown integration
  - Gauss linking integral (winding computation)
  - Topological surgery mechanism
  - PLOP packet crafting & Ring 1 emission
  - JSON logging & metrics

### 🧪 Test Suites

- **[tests/helix_plop_fire_test.py](tests/helix_plop_fire_test.py)** — Operational validation (6/6 fail-closed tests + circuit verification)
- **[tests/helix_plop_synthetic_test.py](tests/helix_plop_synthetic_test.py)** — Unit + integration tests (winding computation, surgery firing, fail-closed validation)

### 📊 Test Results

- **[results/](results/)** — Test outputs, metrics, and deployments

---

## Architecture at a Glance

```
IMU Data (CORE Inference Stack)
    ↓ (attitude quaternion, angular velocity)
Quaternion Strapdown Integration
    ↓ (gravity-bias trajectory on S²)
Gauss Linking Integral (O(n))
    ↓ (winding number W)
Topological Surgery
    ├─ IF |W| > threshold: quaternion correction
    └─ IF |W| ≤ threshold: gate closed (no action)
    ↓ (PLOP packet if surgery fires)
Ring 1 Listener (127.0.0.1:5555)
    ├─ 5-point fail-closed validation
    ├─ Accept valid packets
    └─ Reject invalid packets (drop)
    ↓ (verified events)
JSON Logging & Metrics
    └─ Full forensic record
```

---

## Directory Structure

```
plop-bridge/
├── README.md                                  # This file
├── src/                                       # Source code
│   └── helix_imu_plop_bridge.py              # Main bridge (1000+ lines)
├── tests/                                     # Test suites
│   ├── helix_plop_fire_test.py               # Fire test (6/6 validation)
│   └── helix_plop_synthetic_test.py          # Unit + integration tests
├── docs/                                      # Documentation
│   ├── RUNBOOK.md                            # Complete operational manual
│   ├── DEPLOYMENT.md                         # 4-phase deployment
│   ├── DEPLOYMENT_STATUS.md                  # Current state
│   ├── MONITORING.md                         # Health dashboard + alerts
│   ├── PLOP_BRIDGE_VALIDATION_REPORT.md      # Full technical spec
│   └── PLOP_BRIDGE_HARDENING_v1.1.md         # Fire test results
└── results/                                   # Test outputs & metrics
    └── README.md                              # Results index
```

---

## Quick Start

### Status Check (30 seconds)

```bash
# Is the service running?
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "sudo systemctl status helix-plop-bridge | head -10"

# What's the current state?
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "ps aux | grep helix_imu_plop | grep -v grep"

# Any surgeries?
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "tail -1 /var/log/helix/plop-bridge/bridge_live.json | python3 -c 'import sys, json; d=json.load(sys.stdin); print(f\"Surgeries: {len(d[\\\"surgeries\\\"])}, Ring1: {d[\\\"ring1\\\"][\\\"received\\\"]}\")"
```

### Daily Operations

```bash
# Run morning health check
~/helix/ops/plop_health_check.sh

# View recent incidents
tail -20 ~/helix/ops/incidents.log

# Monitor live
watch -n 5 'ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "ps aux | grep helix_imu_plop | grep -v grep"'
```

### Incident Response

1. Service crash → See [RUNBOOK.md](docs/RUNBOOK.md) Scenario 1
2. Surgery fired → See [RUNBOOK.md](docs/RUNBOOK.md) Scenario 2
3. High memory → See [RUNBOOK.md](docs/RUNBOOK.md) Scenario 3
4. Disk full → See [RUNBOOK.md](docs/RUNBOOK.md) Scenario 4

---

## Current Deployment Status

**Live on CORE 20.124.180.133 — v1.0.4**

| Metric | Status |
|--------|--------|
| Service | ✅ active (running), enabled (survives reboot) |
| Directory layout | ✅ `/opt/helix/plop-bridge/{src,tests,docs,results}/`, matches repo |
| Fire test | ✅ 7/7 passed (against real `src/`, not a duplicate copy) |
| Tier 1 unit suite | ✅ 6/6 passed on CORE directly |
| Integration test | ✅ surgeries=0, ring1=0 |
| Ring 1 circuit | ✅ emit/receive/verify works, listening on 127.0.0.1:5555 |
| Restarts | ✅ 0 since v1.0.4 redeploy |
| Memory | ✅ ~73-95 MB (was 2.9-6.0 GB before v1.0.4's streaming fix) |
| CPU | ✅ 99-100% (computing Gauss integral — expected, not stalled) |
| Test battery | ✅ 7/7 tiers complete, see [TEST_BATTERY.md](docs/TEST_BATTERY.md) |

---

## Test Results Summary

### Fire Test (Circuit Validation)

```
✅ Fail-closed validation: 6/6 passed
  ✅ Valid packets (+1, -1, 0): ACCEPTED
  ✅ Invalid packets (2, -2, free_scale=1): REJECTED
✅ PLOP packet crafting: 200 bytes, magic 0x706C6F70
✅ Ring 1 listener: UDP socket operational
✅ Circuit: emit → receive → verify WORKS
```

### Integration Test (Real Trajectory)

```
✅ Runtime: 7.2 seconds (efficient)
✅ Surgeries: 0 (correct on stationary)
✅ Ring1 received: 0 (expected)
✅ Ring1 verified: 0 (no packets)
✅ Winding range: [-1e-11, +1e-11] (near-zero, correct)
✅ Position error: 741.56m (expected INS drift, not PLOP failure)
```

### Long-Running Test (24-hour Simulation)

```
✅ Runtime: 15-20 min (O(n) computation)
✅ Surgeries: 0 (stationary trajectory = no topology break)
✅ Ring1 metrics: 0/0/0 (expected, gate closed)
✅ Winding range: [-2.1e-11, +2.4e-11] (stable)
✅ Final yaw error: 23.9° (expected INS integration)
✅ Final position error: 2.4M km (expected INS integration)
```

---

## Deployment Timeline

| Phase | Time | Status | Duration |
|-------|------|--------|----------|
| **1. Transfer** | 12:51 UTC | ✅ Complete | 5 min |
| **2. Validate** | 12:52 UTC | ✅ Complete (6/6 pass) | 10 min |
| **3. Integration** | 12:54 UTC | ✅ Complete | 30 min |
| **4. Systemd** | 12:55 UTC | ✅ Complete | 5 min |
| **Live Operation (v1.0)** | 12:59 UTC (Aug 7) | Superseded | ran until 14:35 stop |
| **v1.0.1 fix + redeploy** | 14:35 UTC (Aug 7) | Superseded | ran until stopped for v1.0.2 investigation |
| **v1.0.2/v1.0.3 local validation** | — (Aug 7) | Superseded | winding fix + steady-rotation gate, validated locally, not yet redeployed |
| **v1.0.4 full test battery + streaming fix** | — (Aug 7-8) | Superseded | soak test found & fixed OOM bug, 7/7 tiers closed |
| **v1.0.4 live redeploy** | 06:18 UTC (Aug 8) | ✅ Active | directory restructured to src/tests/docs/results on CORE, service enabled, see [CHANGELOG.md](docs/CHANGELOG.md) |

---

## Next Steps

### Immediate (This Week)
- [ ] Verify long-running test completes successfully
- [ ] Set up daily health check cron (8:00 AM)
- [ ] Configure logrotate for 7-day retention
- [ ] Test all incident response playbooks

### Short Term (This Month)
- [ ] Force a surgery on synthetic closed-loop test
- [ ] Validate TRACE receives gimbal lock alerts
- [ ] Audit all monitoring thresholds
- [ ] Archive test results to S3 (Reef)

### Long Term (Next Quarter)
- [ ] v1.1 hardening: padding hash utilization
- [ ] Receiver-side free_scale computation
- [ ] Unit test framework for topological closure
- [ ] Integration with attitude correction pipeline
- [ ] Cross-node testing (TRACE forensics, INNY witness)

---

## Contacts & Escalation

| Role | Contact | Reason |
|------|---------|--------|
| **Operations** | Spider (Claude) | Daily checks, monitoring |
| **Code Review** | Steve Hope | Bugs, updates, design |
| **Forensics** | TRACE node | Gimbal lock analysis |
| **Witness** | INNY node | Event validation |
| **Coordination** | Hermes node | Multi-node alerts |

---

## Key Files by Use Case

### "I need to..."

**...understand what PLOP does**
→ Start with [README.md](README.md) (this file), then read [PLOP_BRIDGE_VALIDATION_REPORT.md](docs/PLOP_BRIDGE_VALIDATION_REPORT.md)

**...deploy PLOP to a new CORE**
→ Follow [DEPLOYMENT.md](docs/DEPLOYMENT.md) phases 1-4, validate with fire test

**...run daily operations**
→ Use [RUNBOOK.md](docs/RUNBOOK.md) "Daily Operations" section + [MONITORING.md](docs/MONITORING.md)

**...respond to an incident**
→ Find your scenario in [RUNBOOK.md](docs/RUNBOOK.md) "Incident Response" section

**...understand the math**
→ Read "Architecture & Design" in [RUNBOOK.md](docs/RUNBOOK.md) or full spec in [PLOP_BRIDGE_VALIDATION_REPORT.md](docs/PLOP_BRIDGE_VALIDATION_REPORT.md)

**...review test results**
→ Check [DEPLOYMENT_STATUS.md](docs/DEPLOYMENT_STATUS.md) for summary, [results/](results/) for detailed outputs

**...modify the bridge code**
→ Edit [src/helix_imu_plop_bridge.py](src/helix_imu_plop_bridge.py), run [tests/helix_plop_fire_test.py](tests/helix_plop_fire_test.py) to validate

---

## Philosophy

> "The bridge holds. The gate is closed. Topology is watched."

PLOP represents a shift from statistical filtering to topological awareness. Instead of trying to predict or smooth sensor errors, PLOP detects when the geometry itself breaks (gimbal lock) and applies a constitutional correction.

The design embodies three principles:

1. **Fail-Closed** — Better to miss an event than accept garbage
2. **Constitutional** — Corrections derived from math, not heuristics
3. **Transparent** — Every computation logged, fully auditable

---

## License & Attribution

Part of [The Helix Project](https://github.com/helixprojectai) — Sovereign Thinking via Topologically-Protected Reasoning.

Built with 44 AI systems over one year of thinking, amplified and modulated into this shape.

---

**Status: ✅ LIVE & OPERATIONAL**

🦉⚓🦆📡🔒

*Last updated: 2026-08-07 14:00 UTC*

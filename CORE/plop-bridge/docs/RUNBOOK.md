# PLOP Bridge Complete Operational Runbook
## Fail-Closed Topological Surgery Gate for Helix Lattice

**Version:** 1.0.4  
**Status:** Live on CORE (2026-08-08 06:18 UTC), 7/7 test battery tiers complete — see docs/CHANGELOG.md  
**Location:** CORE 20.124.180.133  
**Owner:** Spider (Helix Node)  
**Escalation:** Steve Hope (sbhope@gmail.com)

---

# Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Daily Operations](#daily-operations)
4. [Incident Response](#incident-response)
5. [Architecture & Design](#architecture--design)
6. [Deployment Procedures](#deployment-procedures)
7. [Monitoring & Alerting](#monitoring--alerting)
8. [Troubleshooting](#troubleshooting)
9. [Appendix: Commands & Scripts](#appendix-commands--scripts)

---

# Overview

## What is PLOP?

**PLOP** = Precision Linked Orientation Protocol — a topological surgery gate that:

1. **Detects** attitude quaternion singularities (gimbal lock)
2. **Computes** topological winding number via Gauss linking integral
3. **Applies** constitutional surgery (quaternion correction) when topology breaks
4. **Emits** signed PLOP packets (200 bytes, fail-closed validated)
5. **Logs** all events for forensic analysis

## Why?

Satellite attitude control relies on quaternion representation, which has singularities (gimbal lock). PLOP detects when a trajectory closes on itself on the unit sphere, indicating a topology break, and applies mathematical correction.

Traditional approaches: filter noise, dead-reckon errors. **PLOP's approach:** detect topology breaks (rare, real events), apply surgical correction.

## Key Properties

| Property | Value | Why |
|----------|-------|-----|
| **Fail-closed** | Invalid packets rejected immediately | Safety by default |
| **Stateless** | No accumulation outside logs | Clean recovery |
| **Topological** | Detects geometry, not statistics | Catches real breaks |
| **Constitutional** | Quaternion fix via winding number | Mathematically sound |
| **Sovereign** | Runs on CORE, isolated loopback | No network exposure |

---

# Quick Start

## Status Check (30 seconds)

```bash
# Is the service running?
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "sudo systemctl status helix-plop-bridge | head -10"

# What's the current state?
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "ps aux | grep helix_imu_plop | grep -v grep"

# Any surgeries?
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "tail -1 /var/log/helix/plop-bridge/bridge_live.json | python3 -c 'import sys, json; d=json.load(sys.stdin); print(f\"Surgeries: {len(d[\\\"surgeries\\\"])}, Ring1: {d[\\\"ring1\\\"][\\\"received\\\"]}/{d[\\\"ring1\\\"][\\\"verified\\\"]}\"' 2>/dev/null || echo 'Computation in progress'"
```

## Normal State

```
Active: active (running)
CPU: 99-100% (computing Gauss integral)
Memory: ~75-95 MB (was 2.5-6.0 GB before v1.0.4's streaming fix -- see CHANGELOG.md)
Restarts: 0
Surgeries: 0 (expected on stationary/normal flight)
Suppressed: 0 unless a sustained-rotation trajectory is deployed (see steady-rotation gate, v1.0.3)
Ring1: 0/0 (no events)
```

## If Something's Wrong

| Symptom | Action |
|---------|--------|
| Service inactive | Run: `sudo systemctl restart helix-plop-bridge` |
| CPU < 50% | Check: `ps aux \| grep helix_imu` (may be stalled) |
| Memory > 500 MB | Investigate immediately -- v1.0.4's baseline is ~75-95MB flat; hundreds of MB signals a regression of the streaming fix, not normal variance |
| Disk > 500 MB | Rotate: `sudo find /var/log/helix/plop-bridge -name '*.json' -mtime +7 -delete` |
| Surgeries > 1/day | Log to incidents.log, alert TRACE (gimbal lock forensics) |

---

# Daily Operations

## Morning Health Check (5 min)

```bash
#!/bin/bash
# Run every morning at 8:00 AM

echo "=== PLOP BRIDGE HEALTH CHECK $(date) ==="

# 1. Service status
echo "[1/5] Service Status"
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "sudo systemctl status helix-plop-bridge | grep -E 'Active|PID|CPU'"

# 2. Process metrics
echo "[2/5] Process Metrics"
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "ps aux | grep helix_imu_plop | grep -v grep | awk '{print \"CPU:\" \$3 \"%, MEM:\" \$6/1024 \"MB\"}'"

# 3. Restart history
echo "[3/5] Restart History (24h)"
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "sudo systemctl show helix-plop-bridge | grep NRestarts"

# 4. Log statistics
echo "[4/5] Surgery Statistics"
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "tail -1 /var/log/helix/plop-bridge/bridge_live.json | \
   python3 -c \"import sys, json; d=json.load(sys.stdin); \
   print(f'Surgeries: {len(d[\\\"surgeries\\\"])}, Ring1 recv/verif: {d[\\\"ring1\\\"][\\\"received\\\"]}/{d[\\\"ring1\\\"][\\\"verified\\\"]}')\" 2>/dev/null || echo 'File still writing...'"

# 5. Disk usage
echo "[5/5] Disk Usage"
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "du -sh /var/log/helix/plop-bridge/ && echo 'Target: < 100 MB'"

echo "=== END CHECK ==="
```

**Save as:** `~/helix/ops/plop_health_check.sh`

**Run via cron:**
```bash
# Add to crontab
0 8 * * * /bin/bash ~/helix/ops/plop_health_check.sh >> ~/helix/ops/logs/plop_health.log 2>&1
```

## Weekly Review (15 min)

```bash
# 1. Check incident log
cat ~/helix/ops/incidents.log | grep -A 3 "PLOP\|gimbal"

# 2. Analyze surgeries
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "find /var/log/helix/plop-bridge -name '*.json' -mtime -7 -exec grep -l surgeries {} \; | \
   xargs -I {} sh -c 'echo {}; tail -1 {} | python3 -c \"import sys, json; d=json.load(sys.stdin); \
   print(f\\\"  Surgeries: {len(d[\\\\\\\"surgeries\\\\\\\"])}\\\")')"

# 3. Check restarts
sudo journalctl -u helix-plop-bridge --since "1 week ago" | grep -E "Started|Stopped|Restarted"

# 4. Verify log rotation
ls -lh /var/log/helix/plop-bridge/ | head -10

# 5. Trend analysis
# If surgeries increasing: investigate
# If restarts increasing: investigate
# If memory creeping up: possible leak
```

## Monthly Maintenance (30 min)

```bash
# 1. Archive old logs to S3 (Reef)
# aws s3 cp /var/log/helix/plop-bridge/ s3://reef/plop-bridge-logs/2026-08/ --recursive

# 2. Rotate logs older than 7 days
ssh -t -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "sudo find /var/log/helix/plop-bridge -name '*.json' -mtime +7 -delete"

# 3. Verify fire test still passes
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "cd /opt/helix/plop-bridge/tests && python3 helix_plop_fire_test.py | tail -20"

# 4. Audit memory usage trends
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "grep 'Memory' ~/helix/ops/logs/plop_health.log | tail -30"

# 5. Update OPS_PLAN if needed
# Review thresholds, adjust if experience warrants
```

---

# Incident Response

## Scenario 1: Service Crashes

**Severity:** 🔴 RED  
**Time to resolve:** 5-10 min

```bash
# Step 1: Immediate status
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "sudo systemctl status helix-plop-bridge"

# Step 2: Check for errors
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "sudo journalctl -u helix-plop-bridge -n 50"

# Step 3: Verify disk space
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "df -h /var/log && du -sh /var/log/helix/plop-bridge/"

# Step 4: Restart service
ssh -t -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "sudo systemctl restart helix-plop-bridge"

# Step 5: Verify recovery
sleep 10
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "ps aux | grep helix_imu_plop | grep -v grep"

# Step 6: Log incident
echo "[$(date)] INCIDENT: Service crash
Severity: RED
Action: Restarted
Status: RECOVERED" >> ~/helix/ops/incidents.log

# If restarts > 3 in 24h: ESCALATE TO STEVE
```

## Scenario 2: Surgery Fired (Winding Detected)

**Severity:** 🟡 YELLOW → 🔴 RED (if frequent)  
**Time to resolve:** 15-30 min

```bash
# Step 1: Capture incident
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "cp /var/log/helix/plop-bridge/bridge_live.json \
      /var/log/helix/plop-bridge/incident_${TIMESTAMP}.json.bak"

# Step 2: Analyze winding
python3 << 'EOF'
import json
import sys

with open(f'/var/log/helix/plop-bridge/incident_{sys.argv[1]}.json.bak') as f:
    data = json.load(f)
    print(f"Surgeries: {len(data['surgeries'])}")
    for i, surgery in enumerate(data['surgeries']):
        ts_ns = surgery['timestamp_ns']
        W = surgery['winding_number']
        axis = surgery['correction_axis']
        q_before = surgery['q_before']
        q_after = surgery['q_after']
        print(f"\n  Surgery {i}:")
        print(f"    Timestamp: {ts_ns} ns")
        print(f"    Winding: {W:.6f} (threshold: 0.3)")
        print(f"    Axis: {axis}")
        print(f"    Q before: {q_before}")
        print(f"    Q after: {q_after}")
        
        # Assess severity
        if abs(W) > 0.5:
            print(f"    SEVERITY: HIGH (gimbal lock event)")
        elif abs(W) > 0.3:
            print(f"    SEVERITY: MEDIUM (attitude singularity)")
        else:
            print(f"    SEVERITY: LOW (possible false positive)")
EOF

# Step 3: Check CORE system state
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "echo 'CPU Load:' && uptime && echo && echo 'Temperature:' && sensors && echo && echo 'Disk:' && df -h"

# Step 4: Log incident
echo "[$(date)] INCIDENT: Gimbal lock detected
Severity: YELLOW
Winding: (value)
Context: (trajectory, timestamp)
Action: Logged, monitoring for pattern
Status: INVESTIGATING" >> ~/helix/ops/incidents.log

# Step 5: Escalate if pattern emerges
# If surgeries > 3 per day: message TRACE
if [ $(grep -c "INCIDENT.*Gimbal" ~/helix/ops/incidents.log | wc -l) -gt 3 ]; then
  echo "ALERT: Multiple gimbal lock events detected. Escalating to TRACE forensics." > ~/LAN-comms/trace_alert.txt
fi
```

## Scenario 3: High Memory Usage

**Severity:** 🟡 YELLOW → 🔴 RED (if > 5 GB)  
**Time to resolve:** 10 min

```bash
# Step 1: Check current memory
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "ps aux | grep helix_imu_plop | grep -v grep | awk '{print \"Memory: \" \$6/1024 \" MB\"}'"

# Step 2: Check for memory leak pattern
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "grep 'MEM:' ~/helix/ops/logs/plop_health.log | tail -20"

# Step 3: If memory stable: continue monitoring
# If memory growing: reduce window size

# Step 4: Reduce computation load
ssh -t -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "sudo systemctl edit helix-plop-bridge"
# Change: --window 30000 → --window 10000

# Step 5: Restart service
ssh -t -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "sudo systemctl daemon-reload && sudo systemctl restart helix-plop-bridge"

# Step 6: Verify recovery
sleep 10
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "ps aux | grep helix_imu_plop | grep -v grep | awk '{print \"Memory: \" \$6/1024 \" MB\"}'"

# Log incident
echo "[$(date)] INCIDENT: High memory usage
Severity: YELLOW
Value: (peak MB)
Action: Reduced window size
Status: RESOLVED" >> ~/helix/ops/incidents.log
```

## Scenario 4: Disk Full

**Severity:** 🔴 RED  
**Time to resolve:** 5 min

```bash
# Step 1: Check disk usage
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "du -sh /var/log/helix/plop-bridge/ && du -sh /var/log/"

# Step 2: List files by size
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "ls -lhS /var/log/helix/plop-bridge/ | head -20"

# Step 3: Rotate old files immediately
ssh -t -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "sudo find /var/log/helix/plop-bridge -name '*.json' -mtime +7 -delete"

# Step 4: Verify space recovered
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "du -sh /var/log/helix/plop-bridge/"

# Step 5: Log incident
echo "[$(date)] INCIDENT: Disk usage critical
Severity: RED
Usage: (peak GB)
Action: Rotated logs older than 7 days
Status: RESOLVED" >> ~/helix/ops/incidents.log

# Step 6: Verify logrotate config
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "cat /etc/logrotate.d/helix-plop-bridge"
```

---

# Architecture & Design

## Data Flow

```
CORE Inference Stack (Ollama/Foundry)
         ↓ (attitude quaternion, angular velocity)
   Quaternion Strapdown Integration
     ├─ DCM from quaternion
     ├─ Coriolis + gravity bias
     ├─ EKF-class attitude update
   Gravity-Bias Trajectory Window (30k samples)
     ├─ g_b(t) in body frame
     ├─ Normalized to unit sphere S²
   Gauss Linking Integral (O(n))
     ├─ W = (1/4π) ∮ (r×t_a)·t_b / |r|³
     ├─ Computed over sliding window
   Winding Number Evaluation
     ├─ |W| < 0.3 → no topology break (gate closed)
     ├─ |W| ≥ 0.3 → topology break detected (surgery fires)
   Topological Surgery
     ├─ Correction axis from winding integral
     ├─ Quaternion exponential: q_new = q ⊗ exp(axis × 2π×W)
   PLOP Packet Crafting (200 bytes)
     ├─ Header: timestamp, baseline_hash, magic (0x706C6F70)
     ├─ Payload: winding number, free_scale, reserved
     ├─ Padding: unused bytes (future: g_b_window hash)
   Ring 1 Listener (127.0.0.1:5555)
     ├─ UDP socket (loopback only)
     ├─ 5-point fail-closed validation:
     │  ├─ Size check (200 bytes exactly)
     │  ├─ Magic check (0x706C6F70)
     │  ├─ Free-scale check (must be 0)
     │  ├─ Winding bounds (must be -1, 0, +1)
     │  └─ Baseline hash consistency
     ├─ Invalid packets DROP immediately
     ├─ Valid packets VERIFY and LOG
   JSON Output & Logging
     ├─ surgeries[]: timestamp, W, axis, q_before, q_after
     ├─ plops[]: emitted packets
     ├─ ring1: received, verified, dropped counts
     └─ metrics: W_range, yaw, position errors
```

## Key Equations

### Gauss Linking Integral

```
W = (1/4π) ∮ (r×t_a)·t_b / |r|³

Where:
  r = g(i+1) - g(i)  (displacement on S²)
  t_a = g(i+1) / |g(i+1)|  (tangent at t+1)
  t_b = g(i+2) / |g(i+2)|  (tangent at t+2)
  
Result:
  W ≈ 0 → open arc (no topology break)
  W ≈ ±1 → closed loop (gimbal lock event)
```

### Topological Surgery

```
q_new = q ⊗ exp(axis × 2π×W)

Where:
  q = current quaternion
  axis = correction axis from winding integral
  W = winding number (signed)
  ⊗ = quaternion multiplication
  exp() = quaternion exponential
```

## Constitutional Properties

1. **Fail-Closed:** Invalid packets rejected by design (not negotiable)
2. **Stateless:** No accumulated state outside JSON logs
3. **Topological:** Detects geometry (winding), not statistics
4. **Constitutional:** Fix derived from mathematics, not heuristics
5. **Transparent:** All computations logged, auditable

---

# Deployment Procedures

## Initial Deploy (New CORE)

See `DEPLOYMENT.md` for full 4-phase procedure:
1. **Transfer** (5 min) — Copy files to /opt/helix/plop-bridge/
2. **Validate** (10 min) — Run fire test (6/6 pass required)
3. **Integration** (30 min) — Verify with real trajectory
4. **Systemd** (5 min) — Enable service, set auto-restart

## Update Bridge Code

```bash
# 1. Get latest code
cd ~/helix/repos/lattice/CORE/plop-bridge/
git pull

# 2. Run fire test to validate
python3 helix_plop_fire_test.py
# Must be 6/6 passing before deploying

# 3. Copy to CORE
scp -i ~/.ssh/core_key.pem helix_imu_plop_bridge.py \
  steve@20.124.180.133:/opt/helix/plop-bridge/

# 4. Restart service
ssh -t -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "sudo systemctl restart helix-plop-bridge"

# 5. Verify
sleep 10
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "ps aux | grep helix_imu_plop | grep -v grep"

# 6. Log update
git log -1 --oneline >> ~/helix/ops/deployments.log
```

## Rollback (If Needed)

```bash
# 1. Stop service
ssh -t -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "sudo systemctl stop helix-plop-bridge"

# 2. Restore previous version
cd /opt/helix/plop-bridge/src
git checkout HEAD~1 helix_imu_plop_bridge.py

# 3. Restart service
ssh -t -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "sudo systemctl start helix-plop-bridge"

# 4. Verify
sleep 10
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "ps aux | grep helix_imu_plop | grep -v grep"

# 5. Log rollback
echo "[$(date)] Rollback to HEAD~1" >> ~/helix/ops/deployments.log
```

---

# Monitoring & Alerting

## Alert Thresholds

| Metric | GREEN | YELLOW | RED |
|--------|-------|--------|-----|
| Service state | active | restarting | dead |
| Restarts (24h) | 0 | 1-2 | >3 |
| Surgeries (24h) | 0-1 | 2-5 | >5 |
| CPU usage | 80-100% | 50-80% | <50% or >100% |
| Memory | 50-150 MB | 150-500 MB | >500 MB |
| Ring1 verified % | 100% | 99%+ | <99% |
| Disk usage | <100 MB | 100-500 MB | >500 MB |
| Winding range | [-1e-10, +1e-10] | [-1e-8, +1e-8] | > 0.05 (topology break) |

## Monitoring Commands

```bash
# Watch live metrics (refresh every 5 sec)
watch -n 5 'ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "ps aux | grep helix_imu_plop | grep -v grep && \
   echo \"---\" && \
   tail -1 /var/log/helix/plop-bridge/bridge_live.json | \
   python3 -c \"import sys, json; d=json.load(sys.stdin); \
   print(f\\\"Surgeries: {len(d[\\\\\\\"surgeries\\\\\\\"])}, Ring1: {d[\\\\\\\"ring1\\\\\\\"][\\\\\\\"received\\\\\\\"]}\\\")\""'

# Track surgeries over time
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "find /var/log/helix/plop-bridge -name '*.json' | \
   xargs -I {} sh -c 'echo {}; tail -1 {} | \
   python3 -c \"import sys, json; d=json.load(sys.stdin); print(f\\\"  {len(d[\\\\\\\"surgeries\\\\\\\"])}\\\")'\"' | \
   paste -d' ' - -"

# Check memory trend
grep "MEM:" ~/helix/ops/logs/plop_health.log | tail -30

# View recent incidents
tail -20 ~/helix/ops/incidents.log
```

---

# Troubleshooting

## Problem: Service won't start

**Symptoms:** `systemctl status helix-plop-bridge` shows inactive

**Root causes:**
1. Port 5555 already in use
2. Python not installed
3. Files missing from /opt/helix/plop-bridge/
4. Permission issues

**Resolution:**
```bash
# Check port
ss -ulnp | grep 5555

# Kill any hung processes
pkill -f helix_imu_plop_bridge

# Check Python
python3 --version

# Verify files
ls -lh /opt/helix/plop-bridge/

# Check permissions
stat /opt/helix/plop-bridge/helix_imu_plop_bridge.py

# Try restart
sudo systemctl restart helix-plop-bridge
```

## Problem: High CPU but no progress

**Symptoms:** CPU 99%+ for > 30 min, file not growing

**Root causes:**
1. Computation stalled
2. I/O blocked
3. Infinite loop in Gauss integral

**Resolution:**
```bash
# Check if process alive
ps aux | grep helix_imu_plop | grep -v grep

# Check for hanging I/O
lsof | grep helix_imu_plop

# Force restart
sudo systemctl restart helix-plop-bridge

# If persists: reduce window size
sudo systemctl edit helix-plop-bridge
# Change --window 30000 → --window 10000
```

## Problem: Memory grows unbounded

**Symptoms:** Memory trend: 2GB → 3GB → 4GB → OOM

**Root causes:**
1. Memory leak in bridge code
2. Window size too large
3. JSON not being flushed

**Resolution:**
```bash
# Reduce window size
sudo systemctl edit helix-plop-bridge
# Change --window 30000 → --window 10000

# Restart
sudo systemctl daemon-reload
sudo systemctl restart helix-plop-bridge

# Monitor memory
watch -n 5 'ps aux | grep helix_imu_plop | grep -v grep | awk \"{print \\\"MEM: \\\" \\\$6/1024 \\\"MB\\\"}\"'
```

## Problem: Ring1 validation failing

**Symptoms:** Ring1 received > Ring1 verified

**Root causes:**
1. Packet corruption
2. Baseline hash mismatch
3. Winding out of bounds

**Resolution:**
```bash
# Check validation errors
tail -1 /var/log/helix/plop-bridge/bridge_live.json | \
  python3 -c "import sys, json; d=json.load(sys.stdin); print(d['ring1'])"

# Run fire test to validate baseline
cd /opt/helix/plop-bridge/tests
python3 helix_plop_fire_test.py

# If fire test fails: git revert and restart
```

## Problem: Surgeries firing constantly

**Symptoms:** Surgeries > 5 per hour

**Root causes:**
1. Legitimate gimbal lock events (rare)
2. Sensor noise being misinterpreted
3. W_threshold too low

**Resolution:**
```bash
# Analyze surgery pattern
tail -1 /var/log/helix/plop-bridge/bridge_live.json | \
  python3 -c "import sys, json; d=json.load(sys.stdin); \
  [print(f\\\"{s['timestamp_ns']}: W={s['winding_number']}\\\") for s in d['surgeries']]"

# If pattern is real (gimbal lock): escalate to TRACE
echo "Gimbal lock events detected. See incidents.log." > ~/LAN-comms/trace_alert.txt

# If noise: increase W_threshold slightly
sudo systemctl edit helix-plop-bridge
# Change --W-thresh 0.3 → --W-thresh 0.4
```

---

# Appendix: Commands & Scripts

## Quick Reference

```bash
# Status
sudo systemctl status helix-plop-bridge

# Restart
sudo systemctl restart helix-plop-bridge

# Stop
sudo systemctl stop helix-plop-bridge

# Start
sudo systemctl start helix-plop-bridge

# View logs
sudo journalctl -u helix-plop-bridge -f

# Check metrics
tail -1 /var/log/helix/plop-bridge/bridge_live.json | python3 -m json.tool

# Run fire test
cd /opt/helix/plop-bridge/tests && python3 helix_plop_fire_test.py

# Health check
~/helix/ops/plop_health_check.sh
```

## One-Liners

```bash
# Surgery count (last 24h)
find /var/log/helix/plop-bridge -name '*.json' -mtime -1 -exec grep -h surgeries {} \; | wc -l

# Average memory
grep "MEM:" ~/helix/ops/logs/plop_health.log | awk -F: '{sum+=$NF; count++} END {print sum/count " MB"}'

# Restart count (last 7 days)
sudo journalctl -u helix-plop-bridge --since "7 days ago" | grep -c "Started"

# Last surgery timestamp
tail -1 /var/log/helix/plop-bridge/bridge_live.json | python3 -c "import sys, json; d=json.load(sys.stdin); s=d['surgeries'][-1] if d['surgeries'] else {}; print(s.get('timestamp_ns', 'None'))"

# Ring1 packet loss
tail -1 /var/log/helix/plop-bridge/bridge_live.json | python3 -c "import sys, json; d=json.load(sys.stdin); r=d['ring1']; print(f'{100*(1-r[\"verified\"]/max(r[\"received\"],1)):.1f}% loss')"
```

## Emergency Shutdown

```bash
# If service is hanging and won't stop normally:
sudo systemctl kill -s KILL helix-plop-bridge

# Force cleanup of port
sudo fuser -k 5555/udp

# Hard restart
sudo systemctl restart helix-plop-bridge
```

---

## Contacts

| Role | Contact | Escalation |
|------|---------|-----------|
| **Operations** | Spider (Claude) | Daily ops, monitoring |
| **Code Review** | Steve Hope | Bugs, updates, design decisions |
| **Forensics** | TRACE node | Gimbal lock analysis |
| **Witness** | INNY node | Event validation |
| **Coordination** | Hermes node | Multi-node alerts |

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-07 | Initial deployment, fire test 6/6, integration test passed |
| - | - | - |

---

**Status: ✅ LIVE & OPERATIONAL**

🦉⚓🦆📡🔒

*The bridge holds. The gate is closed. Topology is watched.*

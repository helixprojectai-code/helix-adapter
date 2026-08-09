# PLOP Bridge Monitoring Dashboard
## Real-Time Health & Incident Response

**Status:** Live on CORE 20.124.180.133  
**Deployed:** 2026-08-07 12:55 UTC  
**Service:** helix-plop-bridge (systemd)  
**Log Path:** `/var/log/helix/plop-bridge/bridge_live.json`

---

## **Daily Health Check (5 min)**

### Quick Status Snapshot

```bash
#!/bin/bash
# Run this every morning

echo "=== PLOP BRIDGE HEALTH CHECK ==="
echo "[1/4] Service Status"
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "sudo systemctl status helix-plop-bridge | grep -E 'Active|CPU|Memory|PID'"

echo "[2/4] Process Metrics"
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "ps aux | grep helix_imu_plop | grep -v grep | awk '{print \"CPU:\" \$3 \"%, MEM:\" \$6 \"KB, TIME:\" \$10}'"

echo "[3/4] Restart History"
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "sudo systemctl show helix-plop-bridge | grep -E 'NRestarts|ExecMainStatus|ExecMainExitCode'"

echo "[4/4] Log Statistics"
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "if [ -f /var/log/helix/plop-bridge/bridge_live.json ]; then tail -1 /var/log/helix/plop-bridge/bridge_live.json | python3 -c 'import sys, json; d=json.load(sys.stdin); print(f\"Surgeries: {len(d[\\\"surgeries\\\"])}, Ring1 received: {d[\\\"ring1\\\"][\\\"received\\\"]}, verified: {d[\\\"ring1\\\"][\\\"verified\\\"]}\")'; else echo 'Log file still being written'; fi"

echo "=== END CHECK ==="
```

### Automated Health Check (Cron)

```bash
# Add to /etc/cron.d/helix-plop-monitor
0 8 * * * steve /home/steve/helix/ops/plop_health_check.sh >> /var/log/helix/ops/plop_daily.log 2>&1
```

---

## **Alert Thresholds & Actions**

### 🟢 GREEN (Normal Operation)

| Metric | Target | Status |
|--------|--------|--------|
| Service State | active (running) | ✅ Good |
| Restarts (24h) | 0 | ✅ Good |
| Surgeries (24h) | 0-1 | ✅ Expected |
| Ring1 verified/received | 100% match | ✅ Good |
| CPU usage | 80-100% (computing) | ✅ Normal |
| Memory usage | 50-150 MB | ✅ Normal (v1.0.4+) |
| Disk usage (/var/log) | < 100 MB | ✅ Good |

**Action:** None. Monitor continues.

---

### 🟡 YELLOW (Watch Closely)

| Trigger | Meaning | Action |
|---------|---------|--------|
| **Surgeries > 1 per 24h** | Possible gimbal lock events | 1. Log timestamp & winding value<br>2. Check CORE system temp/CPU<br>3. Analyze quaternion trajectory<br>4. Alert TRACE (forensic validator) |
| **Restarts > 2 per 24h** | Service crashing/recovering | 1. Check journalctl for errors<br>2. Verify /var/log disk space<br>3. Check CORE memory pressure<br>4. Review last crash timestamp |
| **Ring1 verified < 99%** | Validation failures occurring | 1. Check packet corruption logs<br>2. Verify Ring1 socket state<br>3. Check baseline hash consistency<br>4. May indicate data integrity issue |
| **CPU usage < 50%** | Computation stalled | 1. Check if process alive (`ps aux`)<br>2. Verify I/O not blocked<br>3. Check CORE system load<br>4. Restart if stuck |
| **Memory > 4 GB** | Possible memory leak | 1. Check computation window size<br>2. Review for accumulation bugs<br>3. Note timestamp of spike<br>4. Monitor for OOM kill |
| **Disk usage > 500 MB** | Log rotation failing | 1. Check `du -sh /var/log/helix/plop-bridge/`<br>2. Verify logrotate config<br>3. Manually rotate old files<br>4. Restart service |

**Action:** Investigate, log to `~/helix/ops/incidents.log`, but no immediate restart needed.

---

### 🔴 RED (Immediate Action Required)

| Trigger | Meaning | Action |
|---------|---------|--------|
| **Service inactive/dead** | Process crashed or stopped | 1. Capture full systemd journal<br>2. Check /var/log/helix/plop-bridge/ for JSON<br>3. Verify CORE connectivity<br>4. Restart: `sudo systemctl restart helix-plop-bridge`<br>5. If persists: git revert + restart |
| **Restarts > 5 per day** | Severe instability | 1. Capture last 50 journal lines<br>2. Stop service: `sudo systemctl stop helix-plop-bridge`<br>3. Run fire test to validate circuit<br>4. Check CORE system resources (disk/temp)<br>5. Rollback if code issue |
| **Ring1 verified < 95%** | Systemic validation failure | 1. Immediate stop: `sudo systemctl stop helix-plop-bridge`<br>2. Capture JSON with failed packets<br>3. Run fire test to validate baseline<br>4. Check baseline_hash consistency<br>5. Alert security team if anomaly |
| **Disk usage > 1 GB** | Log disk full risk | 1. Rotate immediately: `sudo find /var/log/helix/plop-bridge -name '*.json' -mtime +7 -delete`<br>2. Verify space recovered<br>3. Review logrotate config<br>4. Monitor hourly until stable |
| **Memory > 6 GB** | OOM kill imminent | 1. Reduce window size in service file<br>2. Restart service<br>3. Monitor memory trend<br>4. If repeats: code review for memory leak |

**Action:** Immediate investigation, escalation to Steve, possible rollback.

---

## **Incident Response Playbooks**

### **Playbook A: Surgery Fired (Winding Detection)**

```bash
# When: surgeries > 0 in JSON
# Severity: YELLOW initially, escalate to RED if frequent

1. CAPTURE INCIDENT
   FILE="/var/log/helix/plop-bridge/incident_$(date +%Y%m%d_%H%M%S).json.bak"
   ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "cp /var/log/helix/plop-bridge/bridge_live.json $FILE"

2. ANALYZE WINDING
   python3 << 'EOF'
import json
with open(FILE) as f:
    data = json.load(f)
    for i, surgery in enumerate(data['surgeries']):
        ts = surgery['timestamp_ns']
        W = surgery['winding_number']
        axis = surgery['correction_axis']
        print(f"Surgery {i}: ts={ts}, W={W:.6f}, axis={axis}")
EOF

3. ASSESS SEVERITY
   - |W| > 0.5 = Gimbal lock event (legitimate)
   - |W| = 0.2-0.5 = Attitude singularity
   - |W| < 0.1 = Possible noise/false positive

4. ESCALATE IF NEEDED
   # If gimbal lock or frequent surgeries:
   echo "PLOP surgery detected at $(date)" >> ~/helix/ops/incidents.log
   # Message to TRACE node
   echo "Gimbal lock event detected. Check attitude logs." > ~/LAN-comms/trace_alert.txt

5. CONTINUE MONITORING
   Watch for pattern: single event OK, >3/day = problem
```

### **Playbook B: Service Crash**

```bash
# When: systemctl status shows "inactive (dead)"
# Severity: RED

1. IMMEDIATE CAPTURE
   ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
     "sudo journalctl -u helix-plop-bridge -n 100 > /tmp/crash_$(date +%s).log"
   scp -i ~/.ssh/core_key.pem steve@20.124.180.133:/tmp/crash_*.log ~/helix/ops/

2. VERIFY NO PARTIAL JSON
   ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
     "ls -lh /var/log/helix/plop-bridge/"

3. CHECK DISK SPACE
   ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
     "df -h /var/log && du -sh /var/log/helix/plop-bridge/"

4. RESTART SERVICE
   ssh -t -i ~/.ssh/core_key.pem steve@20.124.180.133 \
     "sudo systemctl restart helix-plop-bridge && sleep 2 && sudo systemctl status helix-plop-bridge"

5. VERIFY RECOVERY
   sleep 10
   ps aux | grep helix_imu_plop | grep -v grep
   # If alive: SUCCESS
   # If dead: ESCALATE (git revert needed)
```

### **Playbook C: High Memory Usage**

```bash
# When: Memory > 4 GB sustained
# Severity: YELLOW → RED if > 6 GB

1. CHECK CURRENT STATE
   ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
     "ps aux | grep helix_imu_plop | grep -v grep"

2. REDUCE COMPUTATION LOAD
   # Lower window size in systemd service
   # Edit: /etc/systemd/system/helix-plop-bridge.service
   # Change: --window 30000 → --window 10000
   # Then restart

3. MONITOR AFTER CHANGE
   # Watch memory for 5 minutes
   for i in {1..10}; do
     ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
       "ps aux | grep helix_imu | grep -v grep | awk '{print \$6}'"
     sleep 30
   done
```

### **Playbook D: Disk Full**

```bash
# When: /var/log/helix/plop-bridge > 500 MB
# Severity: YELLOW → RED if > 1 GB

1. CHECK SIZE
   ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
     "du -sh /var/log/helix/plop-bridge/ && find /var/log/helix/plop-bridge -name '*.json' -mtime +7"

2. ROTATE OLD LOGS
   ssh -t -i ~/.ssh/core_key.pem steve@20.124.180.133 \
     "sudo find /var/log/helix/plop-bridge -name '*.json' -mtime +7 -delete"

3. VERIFY CLEANUP
   ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
     "du -sh /var/log/helix/plop-bridge/"

4. ARCHIVE IF NEEDED
   # Copy to S3 (Reef) for long-term storage
   # aws s3 cp /var/log/helix/plop-bridge/archive/ s3://reef/plop-bridge-logs/
```

---

## **Metrics Dashboard (Real-Time)**

### Create Monitoring Script

```bash
#!/bin/bash
# ~/helix/ops/plop_monitor.sh
# Run in terminal for live dashboard

watch -n 5 'ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 \
  "echo \"=== PLOP BRIDGE LIVE METRICS ===\"
   echo \"[$(date)]\"
   echo \"Process:\"
   ps aux | grep helix_imu_plop | grep -v grep | awk \"{print \\\"  PID:\\\" \\\$2, \\\"CPU:\\\" \\\$3 \\\"%\\\", \\\"MEM:\\\" \\\$6/1024 \\\"MB\\\"}\"
   echo \"Service:\"
   sudo systemctl status helix-plop-bridge | grep Active
   echo \"Surgeries:\"
   tail -1 /var/log/helix/plop-bridge/bridge_live.json 2>/dev/null | \
     python3 -c \"import sys, json; d=json.load(sys.stdin); print(f\\\"  Total: {len(d[\\\\\\\"surgeries\\\\\\\"])} (threshold: 1/24h)\\\")\" || echo \"  (Computing...)\"
   echo \"Disk:\"
   du -sh /var/log/helix/plop-bridge/
   echo \"Uptime:\"
   sudo systemctl show helix-plop-bridge -p NRestarts\"'
```

Run with:
```bash
bash ~/helix/ops/plop_monitor.sh
```

---

## **Logging & Retention**

### Log Rotation (logrotate)

```bash
# /etc/logrotate.d/helix-plop-bridge
/var/log/helix/plop-bridge/*.json {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0644 steve steve
    sharedscripts
}
```

Install:
```bash
sudo tee /etc/logrotate.d/helix-plop-bridge << 'EOF'
/var/log/helix/plop-bridge/*.json {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0644 steve steve
}
EOF
sudo logrotate -f /etc/logrotate.d/helix-plop-bridge
```

---

## **Incident Log Template**

```bash
# File: ~/helix/ops/incidents.log
# Append each incident

[2026-08-07 13:45:30] INCIDENT: Surgery fired
  Severity: YELLOW
  Winding: 0.35
  Axis: [0.707, 0.0, 0.707]
  Context: LEO orbit simulation
  Action: Logged, monitoring for pattern
  Status: RESOLVED

[2026-08-07 14:12:00] INCIDENT: Service restart
  Severity: YELLOW
  Reason: Memory spike to 3.2 GB
  Duration: 23ms (auto-restart by systemd)
  Action: Monitored, memory normalized
  Status: RESOLVED
```

---

## **Success Criteria (Week 1)**

- ✅ Service running > 99% uptime
- ✅ Zero unplanned restarts
- ✅ Surgeries < 1 per week
- ✅ Ring1 verified = Ring1 received (100%)
- ✅ Disk usage < 100 MB
- ✅ No OOM kills
- ✅ All alert thresholds tuned

---

## **Escalation Path**

| Issue | Level | Action | Contact |
|-------|-------|--------|---------|
| Surgeries > 0 | YELLOW | Log & monitor | Continue |
| Service crash | RED | Restart & investigate | Steve |
| Memory spike | YELLOW | Reduce window | Continue |
| Disk full | RED | Rotate logs | Steve |
| Validation fail | RED | Stop & forensic test | Steve + TRACE |
| Gimbal lock pattern | RED | Escalate to INNY | Steve + Lattice |

---

## **Quick Reference Commands**

```bash
# Check service status
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "sudo systemctl status helix-plop-bridge"

# Tail live logs
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "tail -f /var/log/helix/plop-bridge/bridge_live.json"

# Check process
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "ps aux | grep helix_imu_plop | grep -v grep"

# Restart service
ssh -t -i ~/.ssh/core_key.pem steve@20.124.180.133 "sudo systemctl restart helix-plop-bridge"

# View systemd journal
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "sudo journalctl -u helix-plop-bridge -f"

# Disk usage
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "du -sh /var/log/helix/plop-bridge/"

# Run fire test (validation)
ssh -i ~/.ssh/core_key.pem steve@20.124.180.133 "cd /opt/helix/plop-bridge/tests && python3 helix_plop_fire_test.py"
```

---

## **Next Steps**

- [ ] Schedule daily health check cron job (8:00 AM)
- [ ] Test all playbooks (dry run)
- [ ] Configure logrotate
- [ ] Set up incident log
- [ ] Brief TRACE/INNY on escalation procedures
- [ ] Monthly audit of all thresholds

---

🦉⚓🦆📡🔒 **The gate is closed. The bridge is watching.**


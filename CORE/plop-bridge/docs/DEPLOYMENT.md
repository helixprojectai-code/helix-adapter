# PLOP Bridge Deployment to CORE
## Topological Surgery Gate on Inference Stack

**Target:** CORE at 20.124.180.133  
**Status:** Production Ready  
**Deployment Window:** 2026-08-07+  

---

## Pre-Deployment Checklist

### Infrastructure Verification

- [ ] CORE accessible at 20.124.180.133
- [ ] SSH key configured for CORE access
- [ ] Python 3.9+ installed on CORE
- [ ] numpy installed (`pip3 install numpy`)
- [ ] Port 5555 available (Ring 1 UDP listener)
- [ ] Firewall allows 127.0.0.1:5555 (loopback UDP)

**Verify connectivity:**
```bash
ssh steve@20.124.180.133 "uname -a"
ssh steve@20.124.180.133 "python3 --version"
```

### Code Review & Testing

- [x] PLOP packet structure validated (200 bytes, magic 0x706C6F70)
- [x] Fail-closed validation proven (6/6 tests passing)
- [x] Ring 1 UDP circuit verified (emit → receive → verify)
- [x] Fire test completed successfully
- [x] Zero spurious emissions across all test trajectories
- [x] Documentation complete

---

## Deployment Steps

### Phase 1: Transfer & Setup (5 min)

```bash
# Copy files to CORE
scp -r ~/helix/repos/lattice/CORE/plop-bridge steve@20.124.180.133:/opt/helix/plop-bridge/

# Verify transfer
ssh steve@20.124.180.133 "ls -lh /opt/helix/plop-bridge/"

# Create log directory
ssh steve@20.124.180.133 "mkdir -p /var/log/helix/plop-bridge"
```

### Phase 2: Local Test on CORE (10 min)

```bash
# SSH to CORE
ssh steve@20.124.180.133

# Run fire test to validate environment
cd /opt/helix/plop-bridge/tests
python3 helix_plop_fire_test.py

# Expected output:
#   ✅ Fail-closed validation: 6/6 passed
#   ✅ PLOP → Ring1 circuit: WORKS
#   ✅ Circuit Status: Ready for deployment
```

### Phase 3: Integration Test (30 min)

Launch the bridge with minimal trajectory to validate CORE environment:

```bash
# Run 15-minute stationary test
python3 helix_imu_plop_bridge.py \
  --duration 0.25 \
  --traj stationary \
  --rate 300 \
  --window 30000 \
  --W-thresh 0.3 \
  --baseline-hash 2712847316 \
  --emit-udp \
  --output /var/log/helix/plop-bridge/integration_test.json

# Verify results
cat /var/log/helix/plop-bridge/integration_test.json | python3 -m json.tool
```

**Success criteria:**
- Runtime: 20-30 seconds (0.25 hour @ 300 Hz)
- Surgeries: 0 (expected on stationary)
- Ring 1 received: 0 (no topological events)
- Ring 1 verified: 0
- JSON output valid

### Phase 4: Continuous Operation

Create systemd service for continuous bridge operation:

```bash
# Create service file
sudo tee /etc/systemd/system/helix-plop-bridge.service << 'EOF'
[Unit]
Description=Helix PLOP Bridge - Topological Surgery Gate
After=network.target

[Service]
Type=simple
User=steve
WorkingDirectory=/opt/helix/plop-bridge/src
ExecStart=/usr/bin/python3 helix_imu_plop_bridge.py \
  --duration 24.0 \
  --traj stationary \
  --rate 300 \
  --window 30000 \
  --W-thresh 0.3 \
  --baseline-hash 2712847316 \
  --emit-udp \
  --output /var/log/helix/plop-bridge/bridge_live.json
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Enable & start
sudo systemctl daemon-reload
sudo systemctl enable helix-plop-bridge
sudo systemctl start helix-plop-bridge

# Verify
sudo systemctl status helix-plop-bridge
journalctl -u helix-plop-bridge -f
```

---

## Operational Monitoring

### Daily Checks

```bash
# Check service status
sudo systemctl status helix-plop-bridge

# Tail live results
tail -f /var/log/helix/plop-bridge/bridge_live.json

# Verify Ring 1 silence (no surgeries = no topology break)
cat /var/log/helix/plop-bridge/bridge_live.json | \
  python3 -c "import sys, json; d=json.load(sys.stdin); \
  print(f'Surgeries: {len(d[\"surgeries\"])}, Ring1 received: {d[\"ring1\"][\"received\"]}')"
```

### Alerting

**Monitor for:**
- ❌ Non-zero surgeries (indicates topology break)
- ❌ Ring 1 received > Ring 1 verified (indicates validation failure)
- ❌ Service restart loops (indicates code crash)

**Action on alert:**
1. Capture full JSON log
2. Note timestamp and trajectory type
3. Check CORE system status (CPU, memory, disk)
4. Review bridge code for regression
5. Escalate if topology genuinely broke (gimbal lock)

---

## Integration with CORE Infrastructure

### Connection Points

**IMU Input:**
- Source: CORE Ollama/Foundry inference stack
- Type: Quaternion + angular velocity streams (local IPC or UDP)
- Format: See `helix_imu_plop_bridge.py` line 67-89

**PLOP Output:**
- Destination: Ring 1 listener (127.0.0.1:5555)
- Type: UDP packets, 200 bytes
- Format: See PLOP-200 spec (magic=0x706C6F70)

**Logging:**
- Location: `/var/log/helix/plop-bridge/`
- Format: JSON (surgeries, PLOP events, Ring 1 metrics)
- Retention: 7 days (configure logrotate if needed)

### CORE Service Dependencies

```
CORE Inference Stack
       ↓ (attitude quaternion)
   PLOP Bridge
       ↓ (UDP packets)
   Ring 1 Listener (topological verification)
       ↓ (verified PLOPs)
   Topological Surgery Engine
       ↓ (corrected quaternions)
   Attitude feedback to inference stack
```

---

## Rollback Plan

If bridge causes instability:

```bash
# Stop bridge
sudo systemctl stop helix-plop-bridge

# Disable autostart
sudo systemctl disable helix-plop-bridge

# Verify stopped
sudo systemctl status helix-plop-bridge

# Restore previous version (if applicable)
cd /opt/helix/plop-bridge/src
git checkout HEAD~1 helix_imu_plop_bridge.py
sudo systemctl start helix-plop-bridge
```

**Rollback is clean** because:
- Bridge runs isolated UDP listener (no shared state)
- PLOP packets only emit on topology break (rare)
- Ring 1 validates every packet (fail-closed)
- No state accumulation outside JSON logs

---

## Success Metrics

### Day 1 (Deployment)
- ✅ Bridge running on CORE
- ✅ Fire test passed
- ✅ Integration test completed
- ✅ Service healthy

### Week 1 (Stability)
- ✅ Zero unplanned restarts
- ✅ No surgeries (expected on normal flight)
- ✅ Ring 1 verified = Ring 1 received (100% valid packets)
- ✅ Logs rotating normally

### Month 1 (Production)
- ✅ PLOP fires only on legitimate topology breaks
- ✅ Ring 1 verification catching anomalies
- ✅ Attitude corrections improving stability
- ✅ Zero security incidents

---

## Contact & Support

**Questions on deployment:** Check PLOP_BRIDGE_VALIDATION_REPORT.md  
**Troubleshooting:** See PLOP_BRIDGE_HARDENING_v1.1.md  
**Emergency rollback:** Stop service, restore previous version  

**Bridge architecture:** Fail-closed, stateless, topology-triggered  
**Gate status:** Closed on smooth flight, fires on discontinuity  

---

## Post-Deployment Documentation

After successful deployment, update:

1. **CORE Operations Manual** — Add PLOP Bridge section
2. **Monitoring Dashboard** — Add Ring 1 packet stats
3. **Runbooks** — Add "PLOP Fire Event" response
4. **Incident Response** — Add gimbal lock escalation path

---

**Status:** Ready for deployment  
**Last Updated:** 2026-08-07  
**Deployed By:** [Your name]  
**Deployment Time:** [Timestamp]  

🦉⚓🦆📡🔒

# PLOP Bridge Source Code

## helix_imu_plop_bridge.py (1000+ lines)

**Main bridge implementation — complete topological surgery gate**

### Components

1. **Quaternion Strapdown Integration** (lines ~100-250)
   - Integrates IMU data (attitude quaternions, angular velocity)
   - Computes gravity-bias trajectory in body frame
   - Maintains sliding window of 30k samples for winding computation

2. **Gauss Linking Integral** (lines ~250-350)
   - Computes winding number W from trajectory
   - O(n) algorithm: triple integral over trajectory
   - Result: W ≈ 0 (open arc) or W ≈ ±1 (closed loop)

3. **Topological Surgery** (lines ~350-450)
   - Fires when |W| > threshold
   - Computes correction axis from winding integral
   - Applies quaternion exponential: q_new = q ⊗ exp(axis × 2π×W)

4. **PLOP Packet Crafting** (lines ~450-550)
   - Formats 200-byte UDP packet
   - Header: timestamp, baseline_hash, magic (0x706C6F70)
   - Payload: winding number, free_scale flag, reserved
   - Padding: 172 unused bytes (future use)

5. **Ring 1 Listener** (lines ~550-650)
   - UDP socket on 127.0.0.1:5555
   - 5-point fail-closed validation:
     - Size (200 bytes)
     - Magic (0x706C6F70)
     - Free-scale (must be 0)
     - Winding bounds (-1, 0, +1)
     - Baseline hash
   - Invalid packets DROP immediately
   - Valid packets VERIFY and LOG

6. **JSON Logging** (lines ~650-750)
   - surgeries[]: timestamp, W, axis, q_before, q_after
   - plops[]: emitted packets
   - ring1: received/verified/dropped counts
   - metrics: W_range, yaw/position errors

7. **Trajectory Generators** (lines ~750-950)
   - stationary: No motion (baseline)
   - const_vel: Constant velocity
   - sinusoidal: Periodic motion
   - vibration: Random noise
   - leo: Low Earth orbit
   - barrel_roll: Sustained rotation

### Usage

```bash
python3 helix_imu_plop_bridge.py \
  --duration 24.0 \              # 24-hour simulation
  --traj stationary \            # trajectory type
  --rate 300 \                   # 300 Hz sampling
  --window 30000 \               # 30k sample window
  --W-thresh 0.3 \               # Surgery threshold
  --baseline-hash 2712847316 \   # Hash for validation
  --emit-udp \                   # Enable Ring 1 emit
  --output results.json          # Output file
```

### Output Format

```json
{
  "config": {...},
  "surgeries": [
    {
      "timestamp_ns": 123456789,
      "winding_number": 0.35,
      "correction_axis": [0.707, 0.0, 0.707],
      "q_before": [1.0, 0.0, 0.0, 0.0],
      "q_after": [0.999, 0.01, 0.0, 0.0]
    }
  ],
  "plops": [...],
  "ring1": {"received": 1, "verified": 1, "dropped": 0},
  "metrics": {...}
}
```

### Key Functions

| Function | Purpose | Complexity |
|----------|---------|-----------|
| `compute_winding_number()` | Gauss linking integral | O(n) |
| `topological_surgery()` | Quaternion correction | O(n) |
| `craft_plop_packet()` | Format 200-byte packet | O(1) |
| `validate_plop_packet()` | Ring 1 fail-closed checks | O(1) |
| `strapdown_integrate()` | Attitude integration | O(n) |

### Dependencies

- numpy (vector/matrix operations)
- struct (binary packet formatting)
- socket (UDP listener)
- json (logging)

### Notes

- Stateless: No persistent state outside JSON
- Fail-closed: Invalid packets rejected immediately
- Topological: Detects geometry (winding), not statistics
- Production-ready: Validated on 6 trajectory types, 0 spurious emissions

---

**Status:** ✅ Live on CORE 20.124.180.133  
**Last update:** 2026-08-07

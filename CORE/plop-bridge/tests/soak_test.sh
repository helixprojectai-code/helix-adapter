#!/usr/bin/env bash
# Tier 4.1 + 4.2 soak test: launches the bridge for a genuinely
# multi-hour wall-clock run (--duration chosen so real compute time is
# several hours, not the simulated flight-duration), samples memory and
# disk usage every 5 minutes, logs to soak_test.log.
#
# Proves: the v1.0.1 deque(maxlen=window) fix keeps memory flat over real
# elapsed time, and the checkpoint-overwrite design keeps disk usage flat
# (not accumulating) -- both were previously only claimed, not measured
# over a real multi-hour run.

set -uo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../src" && pwd)"
OUT="/tmp/plop_soak_test.json"
LOG="/tmp/plop_soak_test.log"
SAMPLE_INTERVAL=300  # 5 minutes

rm -f "$OUT" "$LOG"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Soak test starting" | tee -a "$LOG"
echo "  duration=50h (simulated) rate=300Hz window=30000 -- targets ~3h wall-clock" | tee -a "$LOG"

cd "$SRC_DIR"
python3 helix_imu_plop_bridge.py \
  --duration 50.0 --traj stationary --rate 300 --window 30000 \
  --W-thresh 0.3 --baseline-hash 2712847316 --output "$OUT" \
  > /tmp/plop_soak_test_stdout.log 2>&1 &
BRIDGE_PID=$!

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bridge launched, PID=$BRIDGE_PID" | tee -a "$LOG"

SAMPLE_NUM=0
while kill -0 "$BRIDGE_PID" 2>/dev/null; do
  sleep "$SAMPLE_INTERVAL"
  SAMPLE_NUM=$((SAMPLE_NUM + 1))
  if kill -0 "$BRIDGE_PID" 2>/dev/null; then
    MEM_KB=$(ps -o rss= -p "$BRIDGE_PID" 2>/dev/null | tr -d ' ')
    MEM_MB=$(awk "BEGIN {printf \"%.1f\", $MEM_KB/1024}")
    DISK_BYTES=$(stat -c%s "$OUT" 2>/dev/null || echo 0)
    CV=$(ps -o pcpu= -p "$BRIDGE_PID" 2>/dev/null | tr -d ' ')
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] sample=$SAMPLE_NUM mem_mb=$MEM_MB disk_bytes=$DISK_BYTES cpu_pct=$CV" | tee -a "$LOG"
  fi
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bridge process exited after $SAMPLE_NUM samples ($(($SAMPLE_NUM * SAMPLE_INTERVAL / 60)) min observed)" | tee -a "$LOG"

wait "$BRIDGE_PID" 2>/dev/null
EXIT_CODE=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bridge exit code: $EXIT_CODE" | tee -a "$LOG"

if [ -f "$OUT" ]; then
  python3 -c "
import json
with open('$OUT') as f:
    d = json.load(f)
print(f'Final: complete={d[\"complete\"]}, last_sample={d[\"last_sample\"]}, surgeries={len(d[\"surgeries\"])}, suppressed={len(d[\"suppressed\"])}')
" | tee -a "$LOG"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Soak test complete" | tee -a "$LOG"

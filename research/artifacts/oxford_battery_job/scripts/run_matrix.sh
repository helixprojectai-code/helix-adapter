#!/usr/bin/env bash
# Oxford Battery — Long-Horizon Matrix Launcher
# Target: Azure Standard_E16ads_v7 (16 vCPU, 128 GiB) or any Linux box
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/src"
RESULTS="$ROOT/results"
LOG="$RESULTS/run_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$RESULTS/profiles" "$RESULTS/timeseries"

echo "============================================================"
echo " Oxford Battery Long-Horizon Job"
echo " Root   : $ROOT"
echo " Log    : $LOG"
echo " Start  : $(date -u)"
echo "============================================================"

cd "$SRC"

# --- smoke test (optional, ~2-4 min) ---
if [[ "${1:-}" == "--smoke" ]]; then
  echo "[smoke] quick subset..."
  python3 oxford_long_horizon_matrix.py --quick 2>&1 | tee -a "$LOG"
  echo "[smoke] done"
  exit 0
fi

# --- single severe point (good first long run) ---
if [[ "${1:-}" == "--severe" ]]; then
  echo "[severe] D=5e-16  C=5  both arms..."
  python3 oxford_long_horizon_matrix.py --D 5e-16 --C 5 2>&1 | tee -a "$LOG"
  echo "[severe] done"
  exit 0
fi

# --- full matrix (default) ---
echo "[full] running complete D × C × arm matrix..."
python3 oxford_long_horizon_matrix.py 2>&1 | tee -a "$LOG"

echo "============================================================"
echo " Finished: $(date -u)"
echo " Summary : $RESULTS/long_horizon_summary.csv"
echo "============================================================"

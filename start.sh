#!/bin/bash
cd "$(dirname "$0")"

LOG_FILE="overnight_run_$(date +%Y%m%d_%H%M%S).log"

echo "Starting warehouse simulation batch run..."
echo "Log file: $LOG_FILE"
echo ""

source venv/bin/activate

{
  echo "======================================"
  echo "Batch run started at $(date)"
  echo "======================================"
  echo ""
  
  echo "[$(date +%H:%M:%S)] Starting SMALL configs (50-100 agents)..."
  python experiments/run.py --config experiments/configs/small.yaml
  
  echo ""
  echo "[$(date +%H:%M:%S)] Starting MEDIUM configs (200-500 agents)..."
  python experiments/run.py --config experiments/configs/medium.yaml
  
  echo ""
  echo "[$(date +%H:%M:%S)] Starting LARGE configs (600-1000 agents)..."
  python experiments/run.py --config experiments/configs/large.yaml
  
  echo ""
  echo "======================================"
  echo "All runs complete at $(date)"
  echo "======================================"
} > "$LOG_FILE" 2>&1 &

BATCH_PID=$!
echo "Batch process started with PID: $BATCH_PID"
echo "To monitor: tail -f $LOG_FILE"
echo "To check status: ps -p $BATCH_PID"


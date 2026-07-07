#!/usr/bin/env bash
# Restarts crawl if dead OR stalled (no progress file update in 90s).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONUNBUFFERED=1
PROG_FILE="$ROOT/data/crawl_progress.json"
STALE_SEC=90

is_stale() {
  [[ ! -f "$PROG_FILE" ]] && return 0
  python3 - <<'PY'
import json, sys, time
from pathlib import Path
p = Path("data/crawl_progress.json")
try:
    d = json.loads(p.read_text())
except Exception:
    sys.exit(0)
if d.get("status") != "running":
    sys.exit(1)
u = d.get("updated_at", "")
if not u:
    sys.exit(0)
from datetime import datetime
ts = datetime.fromisoformat(u.replace("Z", "+00:00")).timestamp()
sys.exit(0 if (time.time() - ts) > 90 else 1)
PY
}

start_crawl() {
  echo "$(date -u +%H:%M:%S) starting crawl..."
  python -u scripts/crawl_from_list.py >> crawl.log 2>&1 &
}

while true; do
  status=$(curl -sf http://127.0.0.1:8000/api/crawl-progress 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','idle'))" 2>/dev/null || echo idle)
  if [[ "$status" == "done" ]]; then
    echo "$(date -u +%H:%M:%S) crawl complete"
    exit 0
  fi
  running=$(pgrep -f "scripts/crawl_from_list.py" || true)
  if [[ -z "$running" ]]; then
    start_crawl
  elif is_stale; then
    echo "$(date -u +%H:%M:%S) crawl stalled — restarting"
    pkill -f "scripts/crawl_from_list.py" 2>/dev/null || true
    sleep 2
    start_crawl
  fi
  sleep 15
done

#!/usr/bin/env bash
# Full crawl inside Docker — keeps Mac awake. Logs to crawl.log
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="/Users/Andes/bin:$PATH"
LOG="$ROOT/crawl.log"
echo "=== Crawl started $(date -u +"%Y-%m-%dT%H:%M:%SZ") ===" | tee "$LOG"
caffeinate -dims docker compose exec -T api python scripts/full_reindex.py 2>&1 | tee -a "$LOG"
echo "=== Crawl finished $(date -u +"%Y-%m-%dT%H:%M:%SZ") ===" | tee -a "$LOG"

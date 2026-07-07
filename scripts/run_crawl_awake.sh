#!/usr/bin/env bash
# Full-site crawl — keeps Mac awake until finished.
# Logs to crawl.log in project root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
LOG="$ROOT/crawl.log"
echo "=== Crawl started $(date -u +"%Y-%m-%dT%H:%M:%SZ") ===" | tee "$LOG"
exec caffeinate -dims python scripts/full_reindex.py 2>&1 | tee -a "$LOG"

#!/usr/bin/env bash
# Full crawl from data/crawl_urls.txt (no caffeinate — use Mac sleep settings).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="/Users/Andes/bin:$PATH"
LOG="$ROOT/crawl.log"

chmod +x scripts/build_url_list.sh
./scripts/build_url_list.sh

docker compose build -q
docker compose up -d

CID=$(docker compose ps -q api)
docker cp "$ROOT/data/crawl_urls.txt" "$CID:/app/data/crawl_urls.txt"

echo "=== Crawl started $(date -u +"%Y-%m-%dT%H:%M:%SZ") ===" | tee "$LOG"
docker compose exec -T -e PYTHONUNBUFFERED=1 api \
  python -u scripts/crawl_from_list.py 2>&1 | tee -a "$LOG"
echo "=== Finished $(date -u +"%Y-%m-%dT%H:%M:%SZ") ===" | tee -a "$LOG"

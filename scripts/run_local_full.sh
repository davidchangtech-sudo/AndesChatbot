#!/bin/bash
# Local full stack: Python API + Gemini RAG + sample WordPress site on :8080
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8000}"
WP_PORT="${WP_PORT:-8080}"
SEED_KB="${SEED_KB:-auto}"
RUN_CRAWL=false

usage() {
  cat <<EOF
Usage: ./scripts/run_local_full.sh [options]

  Starts the full local chatbot stack:
    - FastAPI on http://localhost:${API_PORT}  (Gemini + local SQLite KB)
    - Sample WordPress page on http://localhost:${WP_PORT}

Options:
  --seed          Force re-seed knowledge base from data/seed_chunks.json (uses Gemini)
  --crawl         Run full site crawl/reindex before start (slow; needs network + Wordfence OK)
  --api-port N    API port (default 8000)
  --wp-port N     WordPress sample port (default 8080)
  -h, --help      Show this help

Examples:
  ./scripts/run_local_full.sh
  ./scripts/run_local_full.sh --seed
  ./scripts/run_local_full.sh --crawl

EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED_KB=force; shift ;;
    --crawl) RUN_CRAWL=true; shift ;;
    --api-port) API_PORT="$2"; shift 2 ;;
    --wp-port) WP_PORT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  ;;
  esac
done

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Missing .env — copy .env.example and set GOOGLE_API_KEY + CRON_SECRET"
  exit 1
fi

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "Missing .venv — run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

# Local overrides (do not require editing .env for daily dev)
export PUBLIC_API_URL="http://127.0.0.1:${API_PORT}"
export ALLOWED_ORIGINS="http://localhost:${WP_PORT},http://127.0.0.1:${WP_PORT},http://localhost:${API_PORT},http://127.0.0.1:${API_PORT}"
export RAG_STORAGE="${RAG_STORAGE:-local}"
export PORT="${API_PORT}"

if ! python -c "from app.config import get_settings; s=get_settings(); assert s.google_api_key and not s.google_api_key.startswith('your_')" 2>/dev/null; then
  echo "Set a real GOOGLE_API_KEY in .env before running."
  exit 1
fi

chunk_count() {
  python - <<'PY' 2>/dev/null || echo 0
from app.config import get_settings
from app.store import get_store
store = get_store(get_settings())
print(getattr(store, "chunk_count", lambda: 0)())
PY
}

if $RUN_CRAWL; then
  echo "==> Full crawl/reindex (this can take a long time)..."
  python scripts/full_reindex.py
elif [[ "$SEED_KB" == "force" ]]; then
  echo "==> Seeding knowledge base from seed_chunks.json (Gemini embeddings)..."
  python scripts/seed_kb.py
else
  count="$(chunk_count)"
  if [[ "${count:-0}" -eq 0 ]]; then
    echo "==> Knowledge base empty — seeding from seed_chunks.json..."
    python scripts/seed_kb.py
  else
    echo "==> Knowledge base ready (${count} chunks). Use --seed to rebuild or --crawl for full site."
  fi
fi

cleanup() {
  echo ""
  echo "Stopping local stack..."
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "${WP_PID:-}" ]] && kill "$WP_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> Starting API on http://127.0.0.1:${API_PORT}"
uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" --reload &
API_PID=$!

for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
  echo "API failed to start. Check errors above."
  exit 1
fi

health="$(curl -s "http://127.0.0.1:${API_PORT}/health")"
echo "    Health: $health"

echo "==> Starting sample WordPress site on http://127.0.0.1:${WP_PORT}"
python -m http.server "$WP_PORT" --directory "$ROOT/local-wordpress" &
WP_PID=$!

sleep 0.5

cat <<EOF

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Local stack is running

  Sample WordPress (embed test):  http://localhost:${WP_PORT}
  Chatbot API:                    http://localhost:${API_PORT}
  API health:                     http://localhost:${API_PORT}/health
  Same-origin test page:          http://localhost:${API_PORT}/test?v=50
  Leads admin:                    http://localhost:${API_PORT}/admin/leads

  Open the WordPress sample and use the chat bubble (bottom-right).
  Press Ctrl+C to stop both servers.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EOF

wait

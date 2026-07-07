#!/usr/bin/env bash
# Local Docker smoke test — build, start, seed KB, hit key endpoints.
# Usage:
#   export GOOGLE_API_KEY="your-key"
#   chmod +x scripts/test_docker_local.sh && ./scripts/test_docker_local.sh
#
# Or put GOOGLE_API_KEY + CRON_SECRET in .env first (see .env.example).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}→${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}!${NC} $*"; }
fail()  { echo -e "${RED}✗${NC} $*"; exit 1; }

PORT="${PORT:-8000}"
ENV_FILE="${ENV_FILE:-.env}"
COMPOSE=(docker compose -f docker-compose.yml)

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing: $1"
}

ensure_env() {
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
  fi

  if [[ -z "${GOOGLE_API_KEY:-}" || "$GOOGLE_API_KEY" == "your_google_api_key_here" ]]; then
    fail "Set GOOGLE_API_KEY in $ENV_FILE or export it before running this script."
  fi

  if [[ ! -f "$ENV_FILE" ]]; then
    info "Creating $ENV_FILE for local Docker test..."
    CRON_SECRET="${CRON_SECRET:-$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | xxd -p -c 64)}"
    cat >"$ENV_FILE" <<EOF
PORT=8000
PUBLIC_API_URL=http://localhost:${PORT}
ALLOWED_ORIGINS=http://localhost:${PORT},http://127.0.0.1:${PORT},https://www.andestech.com,https://andestech.com

GOOGLE_API_KEY=${GOOGLE_API_KEY}
CRON_SECRET=${CRON_SECRET}

RAG_STORAGE=local

GEMINI_CHAT_MODEL=gemini-2.5-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=768

HTTP_SSL_VERIFY=true
ENABLE_DEV_ROUTES=true
EOF
    chmod 600 "$ENV_FILE"
    ok "Wrote $ENV_FILE"
  fi

  # shellcheck disable=SC1090
  source "$ENV_FILE"
  [[ -n "${CRON_SECRET:-}" ]] || fail "CRON_SECRET missing in $ENV_FILE"
}

wait_for_health() {
  local url="http://127.0.0.1:${PORT}/health"
  info "Waiting for $url ..."
  local i
  for i in $(seq 1 45); do
    if curl -sf "$url" >/dev/null 2>&1; then
      ok "API healthy"
      curl -s "$url" | python3 -m json.tool 2>/dev/null || curl -s "$url"
      echo ""
      return 0
    fi
    sleep 2
  done
  fail "API did not start. Logs: ${COMPOSE[*]} logs"
}

test_endpoint() {
  local name="$1"
  local method="$2"
  local url="$3"
  shift 3
  info "Testing $name ..."
  local code
  code="$(curl -s -o /tmp/andes_test_body.json -w '%{http_code}' -X "$method" "$url" "$@")"
  if [[ "$code" =~ ^2 ]]; then
    ok "$name → HTTP $code"
    head -c 400 /tmp/andes_test_body.json | tr '\n' ' '
    echo ""
  else
    echo "--- response body ---"
    cat /tmp/andes_test_body.json
    echo ""
    fail "$name → HTTP $code"
  fi
}

main() {
  echo ""
  echo "  Andes Chatbot — Docker local smoke test"
  echo "  ========================================"
  echo ""

  require_cmd docker
  docker compose version >/dev/null 2>&1 || fail "Need Docker Compose v2 (docker compose)"
  require_cmd curl

  ensure_env

  info "Stopping any existing stack..."
  "${COMPOSE[@]}" down --remove-orphans 2>/dev/null || true

  info "Building and starting container..."
  "${COMPOSE[@]}" up -d --build
  ok "Container started on port ${PORT}"

  wait_for_health

  info "Seeding knowledge base (Gemini embeddings — ~1–2 min)..."
  "${COMPOSE[@]}" exec -T api python scripts/seed_kb.py
  ok "KB seeded"

  wait_for_health

  test_endpoint "widget.js" GET "http://127.0.0.1:${PORT}/widget.js"
  test_endpoint "test page" GET "http://127.0.0.1:${PORT}/test"
  test_endpoint "kb-status" GET "http://127.0.0.1:${PORT}/api/kb-status" \
    -H "X-Cron-Secret: ${CRON_SECRET}"

  test_endpoint "chat" POST "http://127.0.0.1:${PORT}/chat" \
    -H "Content-Type: application/json" \
    -H "Origin: http://localhost:${PORT}" \
    -d '{"message":"What is AndesCore?","session_id":"docker-test-1"}'

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  ok "All Docker smoke tests passed"
  echo ""
  echo "  Open in browser:  http://127.0.0.1:${PORT}/test"
  echo "  Health:           http://127.0.0.1:${PORT}/health"
  echo "  Logs:             ${COMPOSE[*]} logs -f"
  echo "  Stop:             ${COMPOSE[*]} down"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
}

main "$@"

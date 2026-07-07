#!/usr/bin/env bash
# Andes Chatbot — one-command setup (on-prem server)
# Usage: chmod +x start.sh && ./start.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${BLUE}→${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}!${NC} $*"; }

MODE="${1:-staging}"
if [[ "$MODE" == "prod" || "$MODE" == "production" ]]; then
  ENV_FILE=".env"
  COMPOSE="docker-compose.yml"
  PORT="8000"
  DEFAULT_URL="https://chatbot.andestech.com"
else
  ENV_FILE=".env.staging"
  COMPOSE="docker-compose.staging.yml"
  PORT="8001"
  DEFAULT_URL="https://chatbot-staging.andestech.com"
fi

banner() {
  cat <<'EOF'

  ANDES CHATBOT — ./start.sh
  Staging now | ./start.sh prod after UAT

EOF
}

check_docker() {
  command -v docker >/dev/null 2>&1 || { echo "Docker not installed"; exit 1; }
  docker compose version >/dev/null 2>&1 || { echo "Need: docker compose"; exit 1; }
}

setup_env() {
  local example=""
  if [[ "$ENV_FILE" == ".env.staging" ]]; then
    example=".env.staging.example"
  else
    example=".env.production.example"
  fi

  if [[ ! -f "$ENV_FILE" ]]; then
    info "Creating ${ENV_FILE} from ${example}"
    cp "$example" "$ENV_FILE"
  fi

  if ! grep -q '^GOOGLE_API_KEY=.\+' "$ENV_FILE" 2>/dev/null; then
    echo ""
    read -r -s -p "GOOGLE_API_KEY: " KEY
    echo ""
    [[ -n "$KEY" ]] || { echo "GOOGLE_API_KEY required"; exit 1; }
    if grep -q '^GOOGLE_API_KEY=' "$ENV_FILE"; then
      sed -i.bak "s|^GOOGLE_API_KEY=.*|GOOGLE_API_KEY=${KEY}|" "$ENV_FILE"
    else
      echo "GOOGLE_API_KEY=${KEY}" >>"$ENV_FILE"
    fi
  fi

  if ! grep -q '^CRON_SECRET=.\+' "$ENV_FILE" 2>/dev/null; then
    SECRET="Andes11!"
    if grep -q '^CRON_SECRET=' "$ENV_FILE"; then
      sed -i.bak "s|^CRON_SECRET=.*|CRON_SECRET=${SECRET}|" "$ENV_FILE"
    else
      echo "CRON_SECRET=${SECRET}" >>"$ENV_FILE"
    fi
    ok "Generated CRON_SECRET"
  fi

  chmod 600 "$ENV_FILE"
  ok "Environment file ready: ${ENV_FILE}"
}

start_stack() {
  if [[ -f "${ROOT}/andeschatbot.tar" ]] && ! docker image inspect andeschatbot:latest >/dev/null 2>&1; then
    info "Loading pre-built image from andeschatbot.tar..."
    docker load -i "${ROOT}/andeschatbot.tar"
    ok "Image loaded"
  fi

  local build_flag="--build"
  if docker image inspect andeschatbot:latest >/dev/null 2>&1; then
    build_flag=""
    info "Using pre-built image andeschatbot:latest"
  fi

  info "Starting (${MODE})..."
  if [[ -n "$build_flag" ]]; then
    docker compose -f "$COMPOSE" up -d --build
  else
    docker compose -f "$COMPOSE" up -d
  fi
  ok "Containers running"
}

wait_health() {
  info "Waiting for API on port ${PORT}..."
  local i
  for i in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
      ok "API healthy"
      curl -s "http://127.0.0.1:${PORT}/health" | python3 -m json.tool 2>/dev/null || true
      echo ""
      return 0
    fi
    sleep 2
  done
  warn "Health check timed out — run: docker compose -f ${COMPOSE} logs"
}

print_next() {
  cat <<EOF

DONE — see START.txt

  health  http://127.0.0.1:${PORT}/health
  nginx   ${DEFAULT_URL} → 127.0.0.1:${PORT}
  admin   ${DEFAULT_URL}/admin  (Andes11!)
  WP      upload andes-ai-chatbot.zip → API ${DEFAULT_URL}

EOF
}

main() {
  banner
  check_docker
  setup_env
  start_stack
  wait_health
  print_next
}

main "$@"

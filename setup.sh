#!/usr/bin/env bash
# Andes Chatbot — interactive one-shot setup (IT / on-prem)
# Run: chmod +x setup.sh && ./setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
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

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

prompt() {
  local var_name="$1"
  local question="$2"
  local default="${3:-}"
  local value=""
  if [[ -n "$default" ]]; then
    read -r -p "$question [$default]: " value
    value="${value:-$default}"
  else
    read -r -p "$question: " value
  fi
  printf -v "$var_name" '%s' "$value"
}

prompt_secret() {
  local var_name="$1"
  local question="$2"
  local value=""
  read -r -s -p "$question: " value
  echo ""
  printf -v "$var_name" '%s' "$value"
}

prompt_yn() {
  local question="$1"
  local default="${2:-y}"
  local hint="Y/n"
  [[ "$default" == "n" ]] && hint="y/N"
  local ans=""
  read -r -p "$question ($hint): " ans
  ans="${ans:-$default}"
  [[ "$ans" =~ ^[Yy] ]]
}

normalize_url() {
  local u="$1"
  u="${u%/}"
  echo "$u"
}

validate_https_url() {
  local u="$1"
  [[ "$u" =~ ^https://[^/]+ ]] || fail "URL must start with https:// — got: $u"
}

banner() {
  cat <<'EOF'

  ============================================================
    ANDES CHATBOT INSTALLER
  ============================================================

    This program will:
      1. Ask you a few questions (API URL, WordPress URL, API key)
      2. Start the chatbot server in Docker
      3. Print the code to paste into WordPress

    WordPress does NOT get software installed — only a copy-paste.

    Full guide: START.txt

EOF
}

check_prereqs() {
  info "Checking prerequisites..."
  require_cmd docker
  docker compose version >/dev/null 2>&1 || fail "Need 'docker compose' (Docker Compose v2)"
  ok "Docker is available"
}

choose_environment() {
  echo ""
  echo "  Where is this install for?"
  echo ""
  echo "  1) TEST / staging   (do this first)"
  echo "  2) LIVE / production   (only after testing passes)"
  echo ""
  local choice=""
  while [[ ! "$choice" =~ ^[12]$ ]]; do
    read -r -p "Enter 1 or 2 [1]: " choice
    choice="${choice:-1}"
  done
  if [[ "$choice" == "1" ]]; then
    ENV_NAME="staging"
    COMPOSE_FILE="docker-compose.staging.yml"
    ENV_FILE=".env.staging"
    DEFAULT_PORT="8001"
    DEFAULT_API_URL="https://chatbot-staging.andestech.com"
  else
    ENV_NAME="production"
    COMPOSE_FILE="docker-compose.yml"
    ENV_FILE=".env"
    DEFAULT_PORT="8000"
    DEFAULT_API_URL="https://chatbot.andestech.com"
  fi
  ok "Selected: $ENV_NAME"
}

collect_answers() {
  echo ""
  info "Answer the questions below. Press Enter to accept [defaults]."
  echo ""

  prompt API_PUBLIC_URL "Chatbot web address (must be https://)" "$DEFAULT_API_URL"
  API_PUBLIC_URL="$(normalize_url "$API_PUBLIC_URL")"
  validate_https_url "$API_PUBLIC_URL"

  prompt WP_SITE_URL "WordPress site address (where visitors see the chat)" "https://www.andestech.com"
  WP_SITE_URL="$(normalize_url "$WP_SITE_URL")"
  validate_https_url "$WP_SITE_URL"

  local extra_origins=""
  if prompt_yn "Also allow www.andestech.com?" "y"; then
    extra_origins=",https://www.andestech.com,https://andestech.com"
  fi
  ALLOWED_ORIGINS="${WP_SITE_URL}${extra_origins}"

  prompt HOST_PORT "Server port (IT uses this behind nginx)" "$DEFAULT_PORT"
  [[ "$HOST_PORT" =~ ^[0-9]+$ ]] || fail "Port must be a number"

  echo ""
  info "GOOGLE_API_KEY (input hidden):"
  if [[ -f "$ENV_FILE" ]] && prompt_yn "$ENV_FILE already exists. Re-enter secrets?" "n"; then
    :
  elif [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE" 2>/dev/null || true
    GOOGLE_API_KEY="${GOOGLE_API_KEY:-}"
    CRON_SECRET="${CRON_SECRET:-}"
    ok "Keeping existing secrets from $ENV_FILE"
  fi

  if [[ -z "${GOOGLE_API_KEY:-}" ]]; then
    prompt_secret GOOGLE_API_KEY "GOOGLE_API_KEY"
    [[ -n "$GOOGLE_API_KEY" ]] || fail "GOOGLE_API_KEY is required"
  fi

  if [[ -z "${CRON_SECRET:-}" ]]; then
    if prompt_yn "Auto-generate CRON_SECRET?" "y"; then
      CRON_SECRET="$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | xxd -p -c 64)"
      ok "Generated CRON_SECRET"
    else
      prompt_secret CRON_SECRET "CRON_SECRET"
      [[ -n "$CRON_SECRET" ]] || fail "CRON_SECRET is required"
    fi
  fi

  SEED_KB=false
  BUNDLED_KB=false
  if [[ -f data/rag.db ]]; then
    local chunks
    chunks="$(python3 - <<'PY' 2>/dev/null || echo 0
import sqlite3
try:
    c = sqlite3.connect("data/rag.db")
    print(c.execute("select count(*) from website_chunks").fetchone()[0])
except Exception:
    print(0)
PY
)"
    if [[ "${chunks:-0}" -ge 80 ]]; then
      BUNDLED_KB=true
      ok "Found bundled knowledge base ($chunks chunks in data/rag.db)"
      if prompt_yn "Use bundled knowledge base (recommended — no seed step)?" "y"; then
        SEED_KB=false
      else
        SEED_KB=true
      fi
    elif prompt_yn "Load knowledge base from seed catalog (small — ~34 pages)?" "y"; then
      SEED_KB=true
    fi
  elif prompt_yn "Load knowledge base from seed catalog?" "y"; then
    SEED_KB=true
  fi

  if prompt_yn "Run full website crawl now? (slow — usually wait until after UAT)" "n"; then
    RUN_CRAWL=true
  else
    RUN_CRAWL=false
  fi
}

write_env_file() {
  info "Writing $ENV_FILE ..."
  cat >"$ENV_FILE" <<EOF
# Generated by setup.sh on $(date -u +"%Y-%m-%dT%H:%M:%SZ")
PORT=8000
PUBLIC_API_URL=${API_PUBLIC_URL}
ALLOWED_ORIGINS=${ALLOWED_ORIGINS}

GOOGLE_API_KEY=${GOOGLE_API_KEY}
CRON_SECRET=${CRON_SECRET}

RAG_STORAGE=local

GEMINI_CHAT_MODEL=gemini-2.5-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=768

HTTP_SSL_VERIFY=true
ENABLE_DEV_ROUTES=false

CRAWL_BASE_URL=https://www.andestech.com/en/
SITEMAP_URLS=https://www.andestech.com/sitemap.xml,https://www.andestech.com/sitemap_index.xml
MAX_CRAWL_PAGES=2000
CRAWL_DELAY_SECONDS=2.5
CRAWL_CONCURRENCY=1
CRAWL_WORDFENCE_COOLDOWN=120
EOF
  chmod 600 "$ENV_FILE"
  ok "Wrote $ENV_FILE (permissions 600)"
}

patch_compose_port() {
  # Staging compose defaults to 8001; allow override via generated override file
  local override="docker-compose.${ENV_NAME}.override.yml"
  cat >"$override" <<EOF
# Auto-generated by setup.sh — host port ${HOST_PORT}
services:
  api:
    ports:
      - "${HOST_PORT}:8000"
EOF
  COMPOSE_ARGS=(-f "$COMPOSE_FILE" -f "$override")
}

start_docker() {
  info "Building and starting Docker ($ENV_NAME)..."
  docker compose "${COMPOSE_ARGS[@]}" up -d --build
  ok "Container started"
}

wait_for_health() {
  info "Waiting for API to respond on port ${HOST_PORT}..."
  local i
  for i in $(seq 1 40); do
    if curl -sf "http://127.0.0.1:${HOST_PORT}/health" >/dev/null 2>&1; then
      ok "API is healthy"
      curl -s "http://127.0.0.1:${HOST_PORT}/health" | python3 -m json.tool 2>/dev/null || curl -s "http://127.0.0.1:${HOST_PORT}/health"
      echo ""
      return 0
    fi
    sleep 2
  done
  fail "API did not become healthy. Check: docker compose ${COMPOSE_ARGS[*]} logs"
}

seed_knowledge_base() {
  info "Seeding knowledge base (Gemini embeddings — may take 1–2 minutes)..."
  docker compose "${COMPOSE_ARGS[@]}" exec -T api python scripts/seed_kb.py
  ok "Knowledge base seeded"
}

run_crawl() {
  warn "Full crawl can take hours and may be blocked by Wordfence."
  docker compose "${COMPOSE_ARGS[@]}" exec -T api python scripts/full_reindex.py
}

print_nginx_hint() {
  cat <<EOF

${YELLOW}nginx (IT)${NC}
  Point ${API_PUBLIC_URL} → http://127.0.0.1:${HOST_PORT} with SSL.

EOF
}

print_wordpress_snippet() {
  cat <<EOF
${GREEN}WordPress footer snippet${NC}
  Add via Insert Headers and Footers → Footer on: ${WP_SITE_URL}

<script>
  window.ANDES_CHAT_CONFIG = {
    apiUrl: "${API_PUBLIC_URL}",
    launcherTooltip: "Chat with the Andes AI Assistant"
  };
</script>
<script src="${API_PUBLIC_URL}/widget.js"></script>

EOF
}

print_summary() {
  echo ""
  echo "============================================================"
  ok "CHATBOT SERVER IS RUNNING"
  echo "============================================================"
  echo ""
  echo "  HTTPS: certbot, or Cloudflare on DNS (see START.txt)"
  echo "          Cloudflare = easiest | or: sudo certbot --nginx -d your-domain"
  echo ""
  echo "------------------------------------------------------------"
  echo "  NOW DO WORDPRESS (copy everything below into WP footer)"
  echo "  Settings -> Insert Headers and Footers -> Footer"
  echo "------------------------------------------------------------"
  echo ""
  cat <<WPEOF
<script>
  window.ANDES_CHAT_CONFIG = {
    apiUrl: "${API_PUBLIC_URL}",
    launcherTooltip: "Chat with the Andes AI Assistant"
  };
</script>
<script src="${API_PUBLIC_URL}/widget.js"></script>
WPEOF
  echo ""
  echo "------------------------------------------------------------"
  echo "  Then: clear WP cache, open ${WP_SITE_URL}, click the bubble"
  echo "  Ask: What is AndesCore?"
  echo ""
  echo "  More help: START.txt"
  echo "  Stop server: docker compose ${COMPOSE_ARGS[*]} down"
  echo "============================================================"
}

main() {
  banner
  check_prereqs
  choose_environment
  collect_answers
  write_env_file
  patch_compose_port
  start_docker
  wait_for_health
  if $SEED_KB; then
    seed_knowledge_base
    wait_for_health
  fi
  if $RUN_CRAWL; then
    run_crawl
  fi
  print_summary
}

main "$@"

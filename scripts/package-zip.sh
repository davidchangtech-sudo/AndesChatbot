#!/usr/bin/env bash
# Build andeschatbot.zip — lean handoff (pre-built image + deploy files only)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ZIP="andeschatbot.zip"
OUT="${1:-$ROOT/$ZIP}"

echo "→ Knowledge base (for Docker image)..."
mkdir -p data/bundled
if [[ ! -f data/rag.db ]]; then
  echo "ERROR: data/rag.db missing" >&2
  exit 1
fi
cp data/rag.db data/bundled/rag.db
echo "  ✓ rag.db ($(du -h data/bundled/rag.db | cut -f1))"

echo "→ WordPress plugin..."
./scripts/package-wp-plugin.sh

if command -v docker >/dev/null 2>&1; then
  echo "→ Building Docker image..."
  docker build -t andeschatbot:latest .
  echo "→ Exporting andeschatbot.tar..."
  docker save -o andeschatbot.tar andeschatbot:latest
  echo "  ✓ andeschatbot.tar ($(du -h andeschatbot.tar | cut -f1))"
else
  echo "  ! Docker not installed — building source-only zip (server must build)"
  rm -f andeschatbot.tar
fi

echo "→ Writing ${OUT}..."
rm -f "${OUT}"

if [[ -f andeschatbot.tar ]]; then
  # Deploy package — no source tree (image already has app + KB)
  zip -r "${OUT}" \
    andeschatbot.tar \
    start.sh \
    docker-compose.yml \
    docker-compose.staging.yml \
    .env.staging.example \
    .env.production.example \
    START.txt \
    nginx-chatbot-staging.conf \
    andes-ai-chatbot.zip \
    -x "*.DS_Store"
else
  # Fallback: full source if Docker missing on build machine
  zip -r "${OUT}" \
    start.sh Dockerfile docker-entrypoint.sh \
    docker-compose.yml docker-compose.staging.yml \
    requirements.txt app static \
    scripts/seed_kb.py scripts/run_scheduled_reindex.py \
    data/bundled/rag.db data/seed_chunks.json \
    .env.staging.example .env.production.example \
    START.txt nginx-chatbot-staging.conf andes-ai-chatbot.zip \
    -x "*.pyc" "*__pycache__*" "*.DS_Store"
fi

echo ""
echo "✓ ${OUT} ($(du -h "${OUT}" | cut -f1))"
echo "  Send zip + GOOGLE_API_KEY (separate). IT reads START.txt inside."

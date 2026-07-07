#!/usr/bin/env bash
# Build pre-built Docker image (run once on any machine with Docker)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IMAGE="andeschatbot:latest"
TAR="andeschatbot.tar"

command -v docker >/dev/null 2>&1 || { echo "Install Docker Desktop first"; exit 1; }

mkdir -p data/bundled
cp -f data/rag.db data/bundled/rag.db

echo "→ Building image (may take 5–10 min first time)..."
docker build -t "${IMAGE}" .

echo "→ Exporting ${TAR}..."
docker save -o "${TAR}" "${IMAGE}"

echo ""
echo "✓ ${ROOT}/${TAR} ($(du -h "${TAR}" | cut -f1))"
echo "  Now run: ./scripts/package-zip.sh"
echo "  The .tar will be included in andeschatbot.zip automatically."

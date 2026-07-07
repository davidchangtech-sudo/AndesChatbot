#!/usr/bin/env bash
# Build handoff zip — needs Docker running
set -euo pipefail
cd "$(dirname "$0")"
chmod +x scripts/package-zip.sh
OUT="${1:-$HOME/Downloads/andeschatbot-handoff.zip}"
./scripts/package-zip.sh "$OUT"
echo ""
echo "Send: $OUT + GOOGLE_API_KEY (separate)"

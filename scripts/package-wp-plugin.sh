#!/usr/bin/env bash
# Build andes-ai-chatbot.zip for WordPress upload
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/andes-ai-chatbot.zip"
cd "${ROOT}/wordpress-plugin"
rm -f "$OUT"
zip -r "$OUT" andes-ai-chatbot -x "*.DS_Store"
echo "Created: $OUT"

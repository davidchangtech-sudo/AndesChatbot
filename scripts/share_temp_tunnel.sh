#!/bin/bash
# Temporary public URL — run in a dedicated Terminal window; keep it open.
set -euo pipefail
PORT="${PORT:-8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Tunnel → http://127.0.0.1:$PORT"
echo "Start the API in another window if needed:"
echo "  cd $ROOT && source .venv/bin/activate"
echo "  uvicorn app.main:app --host 127.0.0.1 --port $PORT --reload"
echo ""
echo "Waiting for localhost.run to assign your public HTTPS URL..."
echo ""

exec ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=60 \
  -T -R "80:127.0.0.1:${PORT}" nokey@localhost.run

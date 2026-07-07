#!/bin/sh
set -e

DATA_DIR="/app/data"
mkdir -p "$DATA_DIR"

# First run: copy bundled knowledge base into the named volume (persists across updates)
if [ ! -f "$DATA_DIR/rag.db" ] && [ -f /app/data_seed/rag.db ]; then
  echo "→ Seeding knowledge base into Docker volume (first start)..."
  cp /app/data_seed/rag.db "$DATA_DIR/rag.db"
  echo "✓ rag.db ready (~405 pages)"
fi

# Background scheduler — weekly knowledge base refresh (default: Sunday 03:00)
if [ "${ENABLE_SCHEDULED_REINDEX:-true}" = "true" ]; then
  SCHEDULE="${REINDEX_CRON_SCHEDULE:-0 3 * * 0}"
  cat >/etc/cron.d/andes-reindex <<EOF
SHELL=/bin/sh
PATH=/usr/local/bin:/usr/bin:/bin
${SCHEDULE} root cd /app && /usr/local/bin/python scripts/run_scheduled_reindex.py >> /var/log/andes-reindex.log 2>&1
EOF
  chmod 0644 /etc/cron.d/andes-reindex
  cron
  echo "✓ Scheduled reindex enabled (${SCHEDULE}) — log: /var/log/andes-reindex.log"
fi

# Optional one-time reindex after startup (off by default — slow, may hit Wordfence)
if [ "${REINDEX_ON_STARTUP:-false}" = "true" ]; then
  echo "→ REINDEX_ON_STARTUP=true — running background reindex..."
  /usr/local/bin/python scripts/run_scheduled_reindex.py >> /var/log/andes-reindex.log 2>&1 &
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

#!/bin/bash
# Refresh carbon-copy/ from the live /test page source.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cp "$ROOT/static/test.html" "$ROOT/carbon-copy/index.html"
cp "$ROOT/static/test.html" "$ROOT/carbon-copy/test.html"
echo "Synced carbon-copy/ from static/test.html"

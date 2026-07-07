#!/usr/bin/env bash
# Terminal loading bar for crawl progress (polls API).
API="${1:-http://127.0.0.1:8000}"
while true; do
  json=$(curl -sf "$API/api/crawl-progress" 2>/dev/null) || { echo "API unreachable"; sleep 3; continue; }
  status=$(echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','idle'))")
  pct=$(echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('percent',0))")
  pages=$(echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"{d.get('pages_indexed',0)}/{d.get('total_urls',0)}\")")
  chunks=$(echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('kb_chunks',0))")
  filled=$(python3 -c "print(int(float('$pct')/100*30))")
  bar=$(printf '%*s' "$filled" '' | tr ' ' '█')
  empty=$(printf '%*s' "$((30-filled))" '' | tr ' ' '░')
  printf "\r[%s%s] %5.1f%%  %s pages  %s chunks  (%s)   " "$bar" "$empty" "$pct" "$pages" "$chunks" "$status"
  [[ "$status" == "done" || "$status" == "failed" ]] && echo && break
  sleep 2
done

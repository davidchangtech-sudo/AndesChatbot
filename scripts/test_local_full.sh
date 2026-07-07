#!/usr/bin/env bash
# Quick local smoke test for API + streaming + images + follow-ups
set -euo pipefail
API="${API_URL:-http://127.0.0.1:8000}"

echo "==> Health"
curl -sf "$API/health" | python3 -m json.tool

echo ""
echo "==> AndesCore (accuracy + source)"
curl -sf -X POST "$API/chat" -H 'Content-Type: application/json' \
  -d '{"message":"What is AndesCore?","history":[],"conversation_summary":null}' \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('reply:', d['reply'][:200].replace(chr(10),' '))
print('source:', d['sources'][0]['url'] if d.get('sources') else 'none')
print('media:', d.get('media'))
print('uncertain:', d.get('uncertain'))
"

echo ""
echo "==> Diagram question (image metadata)"
curl -sf -X POST "$API/chat" -H 'Content-Type: application/json' \
  -d '{"message":"Show me the AndesCore N705 block diagram","history":[],"conversation_summary":null}' \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
m=d.get('media')
print('reply:', d['reply'][:160].replace(chr(10),' '))
print('media url:', m['url'][:80] if m else 'none')
print('media alt:', (m.get('alt') or '')[:100] if m else 'none')
"

echo ""
echo "==> Follow-up"
curl -sf -X POST "$API/chat" -H 'Content-Type: application/json' \
  -d '{"message":"tell me more about it","history":[{"role":"user","content":"What is AndesCore?"},{"role":"assistant","content":"AndesCore is our RISC-V processor IP family."}],"conversation_summary":"Products/topics: AndesCore"}' \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('reply:', d['reply'][:200].replace(chr(10),' '))
print('source:', d['sources'][0]['url'] if d.get('sources') else 'none')
"

echo ""
echo "==> Streaming (first token)"
curl -sf -N -X POST "$API/chat/stream" -H 'Content-Type: application/json' \
  -d '{"message":"What is AndeSight?","history":[],"conversation_summary":null}' \
  | python3 -c "
import sys,json,time
t0=time.time()
first=None
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    ev=json.loads(line)
    if ev.get('type')=='token' and first is None:
        first=time.time()-t0
        print('first token:', round(first,2),'s')
    if ev.get('type')=='done':
        print('reply:', ev['reply'][:160].replace(chr(10),' '))
        print('total:', round(time.time()-t0,2),'s')
        break
"

echo ""
echo "==> All checks passed"

#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/data/crawl_urls.txt"
tmp=$(mktemp)
for sm in post-sitemap post-sitemap2 post-sitemap3 page-sitemap category-sitemap; do
  curl -fsSL --max-time 30 "https://www.andestech.com/${sm}.xml" || true
done | grep -o '<loc>[^<]*</loc>' | sed 's/<[^>]*>//g' | grep '/en/' | sed 's|http://|https://|' | sort -u | while read -r u; do
  case "$u" in
    */) echo "$u" ;;
    *.*/*) echo "${u}/" ;;
    *) echo "$u/" ;;
  esac
done > "$tmp"
mv "$tmp" "$OUT"
echo "Wrote $(wc -l < "$OUT" | tr -d ' ') URLs to $OUT"

#!/bin/bash
# Capture a live site for migration: every page in its sitemap (and the pages they link to), with the stylesheets,
# scripts, fonts and images they use, as static files. Polite by default: one request at a time, a pause between
# requests, a normal browser user agent. Some hosts' firewalls (Wordfence, Cloudflare bot rules) block crawlers part
# way through: if pages start failing, STOP, and capture the rest through the browser instead (see SKILL.md).
#
#   bash capture.sh https://example.com <out dir> [wait seconds, default 1] [max pages, for a trial run]
#
# Output: <out>/site/<host>/... (pages as <path>/index.html, or <path>.html for URLs without a trailing slash), <out>/urls.txt (the sitemap URLs), <out>/wget.log.
# Then check the page count against urls.txt, and look in wget.log for 403/429/503 answers.
set -u
SITE="${1:?site URL}"; SITE="${SITE%/}"; OUT="${2:?out dir}"; WAIT="${3:-1}"
mkdir -p "$OUT" && OUT=$(cd "$OUT" && pwd)
HOST=$(echo "$SITE" | sed -E 's#https?://([^/]+).*#\1#')
mkdir -p "$OUT/site"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
# Sitemap URLs (sitemap index files are followed one level).
fetch() { curl -sSL -A "$UA" --max-time 60 "$1"; }
: > "$OUT/urls.txt"
for sm in "$SITE/sitemap.xml" "$SITE/sitemap_index.xml" "$SITE/wp-sitemap.xml"; do
  body=$(fetch "$sm") || continue
  echo "$body" | grep -q "<loc>" || continue
  for loc in $(echo "$body" | grep -oE "<loc>[^<]+</loc>" | sed -E 's#</?loc>##g'); do
    case "$loc" in
      *.xml) fetch "$loc" | grep -oE "<loc>[^<]+</loc>" | sed -E 's#</?loc>##g' | grep -vE '\.(jpe?g|png|gif|webp)$' >> "$OUT/urls.txt" ;;
      *) echo "$loc" >> "$OUT/urls.txt" ;;
    esac
  done
  break
done
sort -u -o "$OUT/urls.txt" "$OUT/urls.txt"
echo "$SITE/" >> "$OUT/urls.txt"
if [ -n "${4:-}" ]; then head -n "$4" "$OUT/urls.txt" > "$OUT/urls.tmp" && mv "$OUT/urls.tmp" "$OUT/urls.txt"; fi
echo "sitemap pages: $(wc -l < "$OUT/urls.txt")"
cd "$OUT/site" && wget --input-file="$OUT/urls.txt" --recursive --level=1 --page-requisites --span-hosts \
  --domains="$HOST,www.$HOST,fonts.googleapis.com,fonts.gstatic.com" --no-parent --adjust-extension \
  --restrict-file-names=windows --wait="$WAIT" --random-wait --tries=2 --timeout=60 -e robots=off \
  --user-agent="$UA" --reject-regex '/(wp-admin|wp-login|feed|xmlrpc|cart|checkout|my-account)|\?(replytocom|share|add-to-cart)=' \
  -o "$OUT/wget.log"
echo "pages captured: $(find "$OUT/site/$HOST" -name '*.html' -not -path '*/wp-content/*' -not -path '*/wp-includes/*' | wc -l)"
echo "(sites whose URLs have no trailing slash are saved as <path>.html; with a trailing slash as <path>/index.html)"
echo "refused (403/429/503): $(grep -cE 'ERROR (403|429|503)' "$OUT/wget.log")"

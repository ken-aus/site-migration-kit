#!/usr/bin/env python3
"""Is every image, video and document the site uses stored in the client's HighLevel Media Storage?

Reads the site's pages (crawled from a running site, or files in a folder), its stylesheets and scripts, collects
every media URL (HighLevel image-service URLs are unwrapped to the original file), and sorts them into:
  OK            in this location's Media Storage listing
  NOT LISTED    under this location's media path but not in the listing (deleted, or the listing is incomplete)
  OTHER LOCATION  a HighLevel file from another sub-account (it can be deleted there without warning)
  OTHER HOST    anywhere else (old site, stock sites, HighLevel's own icon CDN)
  DATA URI      images written into the code itself (small icons; fine, listed for completeness)

Media Storage listing: save the GHL connector's fetch-media-content results to JSON files (see media_match.py). The
listing caps at 1000 files per call: sort by updatedAt and page with offset, and fetch the oldest files too (sortOrder
asc), or older files look missing.

Usage:
  python3 -I media_audit.py --location <locationId> --listing l1.json [--listing l2.json ...] \
      (--url http://localhost:4321 [--sitemap /sitemap.xml] [--paths paths.txt] | --folder public/)
"""
import argparse
import collections
import json
import os
import re
import urllib.parse
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--location", required=True)
ap.add_argument("--listing", action="append", default=[])
ap.add_argument("--url")
ap.add_argument("--sitemap")
ap.add_argument("--paths")
ap.add_argument("--folder", action="append", default=[])
A = ap.parse_args()

MEDIA_EXT = r"(?:jpe?g|png|gif|webp|svg|ico|x-icon|avif|mp4|webm|mov|mp3|pdf|docx?|xlsx?)"
URL_RE = re.compile(r"https?:\\?/\\?/[^\s\"'<>()\\,`]+?\." + MEDIA_EXT + r"(?:\?[^\s\"'<>()\\,`]*)?(?=[\s\"'<>()\\,`]|$)", re.I)
DATA_RE = re.compile(r"data:(image/[a-z+.-]+|font/[a-z0-9]+|application/font[a-z-]*)(?:;base64|;charset|,)", re.I)


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception:
        return ""


def sources():
    """(label, text) for every page, stylesheet and script."""
    if A.url:
        base = A.url.rstrip("/")
        paths = ["/"]
        if A.paths:
            paths = [l.strip() for l in open(A.paths) if l.strip()]
        elif A.sitemap:
            paths = [urllib.parse.urlparse(u).path or "/" for u in re.findall(r"<loc>([^<]+)</loc>", get(base + A.sitemap))]
        seen_assets = set()
        for p in paths:
            html = get(base + p)
            yield p, html
            for m in re.finditer(r"<(?:link|script)\b[^>]*(?:href|src)=[\"']([^\"']+\.(?:css|js)(?:\?[^\"']*)?)[\"']", html, re.I):
                u = urllib.parse.urljoin(base + p, m.group(1))
                if urllib.parse.urlparse(u).netloc == urllib.parse.urlparse(base).netloc and u not in seen_assets:
                    seen_assets.add(u)
                    yield u[len(base):], get(u)
    for folder in A.folder:
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git")]
            for n in files:
                if re.search(r"\.(html?|css|m?js|tsx?)$", n):
                    f = os.path.join(root, n)
                    yield os.path.relpath(f, folder), open(f, encoding="utf-8", errors="ignore").read()


def original(u):
    u = u.replace("\\/", "/")
    i = u.find("/u_http")
    if "images.leadconnectorhq.com/image/" in u and i > 0:
        u = u[i + 3:]
    return urllib.parse.unquote(u.split("?")[0])


def main():
    ids = set()
    for f in A.listing:
        s = open(f, encoding="utf-8").read()
        d = json.loads(s[s.find("{"):] if s.lstrip()[0] == "{" else s)
        d = d.get("data", d) if isinstance(d, dict) else d
        for x in (d.get("files", []) if isinstance(d, dict) else d):
            if x.get("deleted"):
                continue
            ids.add(x.get("_id"))
            for k in ("path", "url"):
                m = re.search(r"/([^/]+?)(\.[a-z0-9-]+)?$", x.get(k) or "")
                if m:
                    ids.add(m.group(1))
    used = collections.defaultdict(set)
    data_uris = collections.Counter()
    for label, text in sources():
        text = re.sub(r"<link\b[^>]*rel=[\"']canonical[\"'][^>]*>", " ", text)
        for m in URL_RE.finditer(text):
            used[original(m.group(0))].add(label)
        for m in DATA_RE.finditer(text):
            data_uris[m.group(1).lower()] += 1
    loc = A.location
    groups = collections.defaultdict(dict)
    for u, where in used.items():
        if re.search(r"/(?:location%2F|location/)?" + loc + r"(?:/|%2F)", u):
            fid = re.search(r"([^/]+?)(?:\.[a-z0-9-]+)?$", u).group(1)
            groups["OK" if fid in ids else "NOT LISTED"][u] = where
        elif re.search(r"(filesafe\.space|storage\.googleapis\.com/msgsndr|leadconnectorhq\.com|msgsndr)", u) and re.search(r"/[A-Za-z0-9]{20}(?:/|%2F)", u):
            groups["OTHER LOCATION"][u] = where
        else:
            groups["OTHER HOST"][u] = where
    print("Media files used: %d (listing has %d ids)" % (len(used), len(ids)))
    for g in ("NOT LISTED", "OTHER LOCATION", "OTHER HOST", "OK"):
        items = groups.get(g, {})
        print("\n%s: %d" % (g, len(items)))
        if g == "OK":
            continue
        for u, where in sorted(items.items(), key=lambda kv: -len(kv[1]))[:50]:
            w = sorted(where)
            print("  %s   on %d: %s%s" % (u, len(w), ", ".join(w[:3]), " ..." if len(w) > 3 else ""))
    if data_uris:
        print("\nDATA URI (in the code itself): " + ", ".join("%s x%d" % kv for kv in data_uris.most_common()))


if __name__ == "__main__":
    main()

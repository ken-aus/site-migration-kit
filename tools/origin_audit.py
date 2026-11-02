#!/usr/bin/env python3
"""What does the new site still load from the old site (or any other host)? Scans the built project files.

Before go-live the answer must be "nothing" except the deliberate pass-throughs (form posts, booking widgets):
if the old site goes down or is rebuilt, anything still loaded from it breaks the new site. On one past migration the first
version still took 90 stylesheets, 33 scripts and nearly every image from the old site.

Scans .html, .css, .js, .ts, .tsx and .json files under the given folders (public/, src/, or a build output), and
lists every URL on the given hosts by kind (stylesheet, script, image, font, video, document, page link), with the
files that use it. Canonical tags, og:/twitter: meta tags and JSON-LD are skipped: they keep the production domain
on purpose. Page links to the old domain are listed separately (on a dev copy they are usually the same site).

Usage:
  python3 -I origin_audit.py --hosts oldsite.com,www.oldsite.com <folder> [<folder> ...] [--all-hosts]
  --all-hosts  also summarise every other external host the pages load files from (fonts, CDNs, widgets).
"""
import argparse
import collections
import os
import re

ap = argparse.ArgumentParser()
ap.add_argument("folders", nargs="+")
ap.add_argument("--hosts", default="")
ap.add_argument("--all-hosts", action="store_true")
A = ap.parse_args()
HOSTS = [h.strip().lower() for h in A.hosts.split(",") if h.strip()]

KINDS = {"css": "stylesheet", "js": "script", "mjs": "script", "woff": "font", "woff2": "font", "ttf": "font", "otf": "font", "eot": "font",
         "jpg": "image", "jpeg": "image", "png": "image", "gif": "image", "webp": "image", "svg": "image", "ico": "image", "avif": "image",
         "mp4": "video", "webm": "video", "mov": "video", "mp3": "audio", "pdf": "document", "doc": "document", "docx": "document",
         "xls": "document", "xlsx": "document", "zip": "document"}
SKIP = re.compile(r"<link\b[^>]*rel=[\"']canonical[\"'][^>]*>|<meta\b[^>]*(?:og:|twitter:|itemprop)[^>]*>|<script[^>]+application/ld\+json[^>]*>.*?</script>", re.S | re.I)
URL = re.compile(r"(?:https?:)?\\?/\\?/([a-z0-9.-]+\.[a-z]{2,})((?:\\?/[^\s\"'<>()\\,`]*)?)", re.I)


def kind(path):
    ext = path.split("?")[0].rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    return KINDS.get(ext, "page link / other")


def main():
    hits = collections.defaultdict(lambda: collections.defaultdict(set))  # kind -> url -> files
    others = collections.Counter()
    nfiles = 0
    for folder in A.folders:
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", ".output", ".vinxi")]
            for n in files:
                if not re.search(r"\.(html?|css|m?js|tsx?|json)$", n) or n in ("package.json", "package-lock.json", "bun.lock"):
                    continue
                f = os.path.join(root, n)
                s = open(f, encoding="utf-8", errors="ignore").read()
                s = SKIP.sub(" ", s)
                nfiles += 1
                for m in URL.finditer(s):
                    host, path = m.group(1).lower(), m.group(2).replace("\\/", "/")
                    if host in HOSTS:
                        hits[kind(path)][host + path.split("?")[0]].add(os.path.relpath(f, folder))
                    elif A.all_hosts and kind(path) != "page link / other":
                        others[host] += 1
    print("Scanned %d files" % nfiles)
    total = 0
    for k in sorted(hits, key=lambda k: (k == "page link / other", k)):
        urls = hits[k]
        total += len(urls)
        print("\n%s: %d from %s" % (k.upper(), len(urls), ", ".join(HOSTS)))
        for u, fs in sorted(urls.items())[:40]:
            fs = sorted(fs)
            print("  %s   in %s%s" % (u, ", ".join(fs[:3]), " (+%d)" % (len(fs) - 3) if len(fs) > 3 else ""))
        if len(urls) > 40:
            print("  ... and %d more" % (len(urls) - 40))
    if not total and HOSTS:
        print("Nothing loads from " + ", ".join(HOSTS) + ".")
    if A.all_hosts:
        print("\nOther hosts files load from (references):")
        for h, c in others.most_common(40):
            print("  %-45s %d" % (h, c))


if __name__ == "__main__":
    main()

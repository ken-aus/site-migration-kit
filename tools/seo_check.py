#!/usr/bin/env python3
"""On-page SEO check of every page: the straightforward fixes a migration should make, before and after.

Per page: status, title (missing, over 60 characters, duplicated, platform defaults like "Archive"), meta description
(missing, over 160, duplicated), H1 count (should be exactly one, not empty), canonical (missing, or pointing
elsewhere), robots (noindex), lang attribute, og:image, schema types present, images without alt text and without
width/height. Site-wide: duplicate titles and descriptions, and which schema types appear nowhere.

Run it on the old site first (the baseline and the fix list) and on the new build after (proof of the fixes).

Usage:
  python3 -I seo_check.py <base URL> (--sitemap /sitemap.xml | --paths paths.txt | --start /) [--production-host example.com]
      [--csv report.csv]
  --production-host: canonicals on this host count as self-canonical when checking a dev copy.
"""
import argparse
import collections
import concurrent.futures as cf
import csv
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import html_tools as H  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("base")
ap.add_argument("--sitemap")
ap.add_argument("--paths")
ap.add_argument("--start", default="/")
ap.add_argument("--production-host")
ap.add_argument("--csv")
A = ap.parse_args()
BASE = A.base.rstrip("/")
# Checking a dev copy (base host isn't the production host): noindex is expected there, so it isn't reported.
DEV = bool(A.production_host) and urllib.parse.urlparse(BASE).netloc.lower() not in (A.production_host, "www." + A.production_host)
DEFAULT_TITLES = re.compile(r"\b(archives?|uncategori[sz]ed|untitled|home page|just another wordpress site|my site|page \d+)\b", re.I)
WANTED = ["Organization", "LocalBusiness", "WebSite", "WebPage", "BreadcrumbList", "BlogPosting", "Article", "Person", "Service", "FAQPage", "ItemList"]


def get(url):
    p = urllib.parse.urlsplit(url)
    url = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(urllib.parse.unquote(p.path)), p.query, ""))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
            return r.status, r.read().decode("utf-8", "ignore"), r.headers.get("x-robots-tag", "")
    except urllib.error.HTTPError as e:
        return e.code, "", ""
    except Exception:
        return 0, "", ""


def page_list():
    if A.paths:
        return [l.strip() for l in open(A.paths) if l.strip()]
    if A.sitemap:
        _s, body, _x = get(BASE + A.sitemap)
        locs = re.findall(r"<loc>([^<]+)</loc>", body)
        out = []
        for loc in locs:
            if loc.endswith(".xml"):  # sitemap index
                out += [urllib.parse.urlparse(u).path for u in re.findall(r"<loc>([^<]+)</loc>", get(loc)[1])]
            else:
                out.append(urllib.parse.urlparse(loc).path or "/")
        return out
    return A.start.split(",")


def check(path):
    st, html, xrobots = get(BASE + path)
    r = {"path": path, "status": st}
    if st != 200 or not html:
        r["issues"] = ["status %s" % st]
        return r
    title = H.title_of(html)
    desc = H.meta(html, "description")
    h1s = [H.text_of(m) for m in re.findall(r"<h1\b[^>]*>(.*?)</h1>", html, re.S | re.I)]
    canon = H.canonical(html)
    robots = (H.meta(html, "robots") or "") + " " + xrobots
    types = sorted(H.schema_types(html))
    imgs = re.findall(r"<img\b[^>]*>", re.sub(r"<noscript\b.*?</noscript>", "", html, flags=re.S | re.I), re.I)
    no_alt = sum(1 for t in imgs if not re.search(r"\balt=", t, re.I))
    no_dims = sum(1 for t in imgs if not (re.search(r"\bwidth=", t, re.I) and re.search(r"\bheight=", t, re.I)))
    issues = []
    if not title:
        issues.append("no title")
    elif len(title) > 60:
        issues.append("title %d chars" % len(title))
    if title and DEFAULT_TITLES.search(title):
        issues.append("default-looking title")
    if not desc:
        issues.append("no meta description")
    elif len(desc) > 160:
        issues.append("description %d chars" % len(desc))
    if len(h1s) != 1:
        issues.append("%d H1s" % len(h1s))
    if any(not h for h in h1s):
        issues.append("empty H1")
    cp = urllib.parse.urlparse(canon)
    if not canon:
        issues.append("no canonical")
    elif cp.path.rstrip("/") != path.rstrip("/") or (A.production_host and cp.netloc not in (A.production_host, "www." + A.production_host, urllib.parse.urlparse(BASE).netloc)):
        issues.append("canonical -> " + canon)
    if "noindex" in robots.lower() and not DEV:
        issues.append("noindex")
    if not re.search(r"<html\b[^>]*\blang=", html, re.I):
        issues.append("no lang")
    if not H.meta(html, "og:image", prop=True):
        issues.append("no og:image")
    if not types:
        issues.append("no schema")
    if no_alt:
        issues.append("%d img no alt" % no_alt)
    r.update(title=title, description=desc or "", h1=len(h1s), canonical=canon, schema=" ".join(types),
             imgs=len(imgs), no_dims=no_dims, issues=issues)
    return r


def main():
    paths = list(dict.fromkeys(page_list()))
    with cf.ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(check, paths))
    titles = collections.Counter(r.get("title") for r in rows if r.get("title"))
    descs = collections.Counter(r.get("description") for r in rows if r.get("description"))
    for r in rows:
        if r.get("title") and titles[r["title"]] > 1:
            r["issues"].append("duplicate title (x%d)" % titles[r["title"]])
        if r.get("description") and descs[r["description"]] > 1:
            r["issues"].append("duplicate description (x%d)" % descs[r["description"]])
    counts = collections.Counter(re.sub(r"\d+", "N", i).split(" -> ")[0] for r in rows for i in r["issues"])
    print("Checked %d pages on %s\n" % (len(rows), BASE))
    print("Issues across the site:")
    for k, v in counts.most_common():
        print("  %-36s %d page(s)" % (k, v))
    seen = collections.Counter(t for r in rows for t in (r.get("schema") or "").split())
    print("\nSchema types: " + (", ".join("%s x%d" % kv for kv in seen.most_common()) or "none"))
    print("Common types not used anywhere: " + ", ".join(t for t in WANTED if t not in seen))
    print("Images without width/height: %d of %d" % (sum(r.get("no_dims", 0) for r in rows), sum(r.get("imgs", 0) for r in rows)))
    print("\nPer page:")
    for r in sorted(rows, key=lambda r: r["path"]):
        if r["issues"]:
            print("  %-50s %s" % (r["path"][:50], "; ".join(r["issues"])))
    if A.csv:
        with open(A.csv, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["path", "status", "title", "description", "h1", "canonical", "schema", "issues"])
            for r in rows:
                w.writerow([r["path"], r["status"], r.get("title", ""), r.get("description", ""), r.get("h1", ""), r.get("canonical", ""), r.get("schema", ""), "; ".join(r["issues"])])


if __name__ == "__main__":
    main()

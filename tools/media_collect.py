#!/usr/bin/env python3
"""Collect every image, video, audio file and document a captured site uses, ready to upload to HighLevel Media Storage.

Works on any captured site (WordPress, Wix, Squarespace, Webflow, HighLevel, hand-built): it reads the saved pages,
stylesheets and scripts under --site, finds every reference to a media file on the --hosts, and makes ONE file per
picture. Platforms list many sizes of each photo (WordPress -300x200 suffixes, EWWW .jpg.webp copies, Wix /v1/fill/
transforms, Squarespace ?format=) and every size points at the same new file, at the largest size any page uses.
Crops with a different shape (square thumbnails) stay separate.

No WebP set is made: pages serve photos through HighLevel's image service, which converts to WebP itself
(lib/hl_images.py). A photo that only exists as WebP is uploaded as WebP.

File names say which page each file belongs to, and are unique, so uploaded files can be matched back by name:
    <prefix>--<page>--<original name>.<ext>      e.g. ab--services_physiotherapy--treatment-room.jpg
<page> is the page path with "/" as "_", "home", or "site-wide" (logos and backgrounds used on many pages or by the
stylesheets).

Outputs in --out:
    images/, videos/, documents/ and one zip of each (<prefix>-images.zip ...), for the user to upload
    media-map.json    every original reference -> new file name, plus each file's pages, size and pixel dimensions
    media-manifest.csv  file, kind, original URL, pages using it (for the user and the client)

Usage:
    python3 -I media_collect.py --site <folder of the captured site root> --hosts example.com,www.example.com,cdn.example.net \
        --prefix ex --out <out dir> [--fetch] [--site-wide-pages 8]
    The first host is the site itself; others are CDNs its files live on (static.wixstatic.com,
    images.squarespace-cdn.com, assets.cdn.filesafe.space for a HighLevel site ...).
    --fetch downloads files that aren't in the capture, politely, and remembers 404s.
"""
import argparse
import csv
import json
import os
import posixpath
import re
import subprocess
import sys
import time
import urllib.parse
import zipfile

IMG = ("jpg", "jpeg", "png", "gif", "webp", "svg", "avif")
VID = ("mp4", "webm", "mov", "m4v", "ogv")
AUD = ("mp3", "m4a", "wav", "ogg")
DOC = ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv", "zip", "txt", "rtf", "epub")
ALL = IMG + VID + AUD + DOC
KIND = {**{e: "images" for e in IMG}, **{e: "videos" for e in VID + AUD}, **{e: "documents" for e in DOC}}
WP_SIZE = re.compile(r"-(\d+)x(\d+)(?=\.\w+$)")


def parse():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True)
    ap.add_argument("--hosts", required=True, help="comma-separated hosts whose files count as the site's media")
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--site-wide-pages", type=int, default=8)
    return ap.parse_args()


A = parse()
SITE = os.path.abspath(A.site)
HOSTS = [h.strip().lower() for h in A.hosts.split(",") if h.strip()]
OUT = os.path.abspath(A.out)
FETCHED = os.path.join(OUT, ".fetched")
EXT = "|".join(ALL)
HOST_RE = "|".join(re.escape(h) for h in HOSTS)
# References in any form: absolute, protocol-relative, JSON-escaped, or root-relative.
ABS = re.compile(r"(?:https?:)?\\?/\\?/(" + HOST_RE + r")((?:\\?/[^\s\"'<>()\\,]*?)+\.(?:" + EXT + r"))((?:\?[^\s\"'<>()\\,]*)?)(?![\w.])", re.I)
ROOT = re.compile(r"(?<=[\s\"'(,=])(/[^\s\"'<>()\\,]+?\.(?:" + EXT + r"))(?![\w.])", re.I)
SRCSET = re.compile(r"\b(?:data-)?(?:lazy-)?srcset(?:-webp)?=([\"'])(.*?)\1", re.S | re.I)
OG_IMAGE = re.compile(r"<meta[^>]+property=[\"']og:image[\"'][^>]*content=[\"']([^\"']+)", re.I)


def norm(path, query=""):
    """One key per file: unescaped, single slashes, platform transforms removed."""
    p = urllib.parse.unquote(path.replace("\\/", "/"))
    p = re.sub(r"/{2,}", "/", p)
    p = posixpath.normpath(p) if p.startswith("/") else p
    p = re.sub(r"/v1/(?:fill|fit|crop)/[^/]+/[^/]+$", "", p)  # Wix: /media/<file>/v1/fill/w_..,h_../name.jpg
    return p


def variant_of(p):
    """(original, is_webp_copy): EWWW's x.jpg.webp is the WebP copy of x.jpg."""
    m = re.match(r"(.+\.(?:jpe?g|png))\.webp$", p, re.I)
    return (m.group(1), True) if m else (p, False)


def base_key(p):
    return re.sub(r"-scaled(?=\.\w+$)", "", WP_SIZE.sub("", p))


def size_in_name(p):
    m = WP_SIZE.search(p)
    return (int(m.group(1)), int(m.group(2))) if m else None


def slug(s, n=60):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n].strip("-")


def page_path(f):
    rel = os.path.relpath(f, SITE).replace(os.sep, "/")
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[:-len("index.html")]
    return "/" + re.sub(r"\.html?$", "", rel)  # wget saves /about as about.html


def page_key(path):
    return "home" if path == "/" else "_".join(slug(s, 70) for s in path.strip("/").split("/") if s) or "home"


def split_ref(p):
    """(host, path): references to the site's own host are plain paths; files on other hosts (a CDN) are //host/path."""
    if p.startswith("//"):
        host, _, rest = p[2:].partition("/")
        return host, "/" + rest
    return HOSTS[0], p


def local_file(p):
    host, path = split_ref(p)
    roots = [SITE, os.path.join(FETCHED, host)] if host == HOSTS[0] else [os.path.join(os.path.dirname(SITE), host), os.path.join(FETCHED, host)]
    for root in roots:
        f = os.path.join(root, path.lstrip("/"))
        if os.path.isfile(f):
            return f
    if not A.fetch:
        return None
    g = os.path.join(FETCHED, host, path.lstrip("/"))
    if os.path.exists(g + ".404"):
        return None
    os.makedirs(os.path.dirname(g), exist_ok=True)
    time.sleep(0.5)
    r = subprocess.run(["curl", "-sS", "-f", "-L", "--max-time", "180", "-A", "Mozilla/5.0", "-o", g, "https://" + host + urllib.parse.quote(path)])
    if r.returncode != 0:
        if os.path.exists(g):
            os.remove(g)
        if r.returncode == 22:
            open(g + ".404", "w").close()
        return None
    return g


def refs_in(text, base_path="/"):
    out = set()
    for host, path, _q in ABS.findall(text):
        host = host.lower()
        own = host == HOSTS[0] or host == "www." + HOSTS[0] or "www." + host == HOSTS[0]
        out.add(norm(path) if own else "//" + host + norm(path))
    for path in ROOT.findall(text):
        if not path.startswith("//"):
            out.add(norm(path))
    return out


def main():
    pages, assets = {}, []
    for root, _dirs, files in os.walk(SITE):
        for n in files:
            f = os.path.join(root, n)
            if n.endswith((".html", ".htm")):
                pages[page_path(f)] = f
            elif re.search(r"\.(css|js)(@.*|\?.*)?$", n):
                assets.append(f)
    order = sorted(pages, key=lambda p: (p != "/", p.count("/"), p))

    used_on, primary, og, theme = {}, set(), {}, set()
    for p in order:
        s = open(pages[p], encoding="utf-8", errors="ignore").read()
        for r in refs_in(s):
            used_on.setdefault(r, set()).add(p)
        primary |= refs_in(SRCSET.sub("", s))
        for m in OG_IMAGE.findall(s):
            for r in refs_in(" " + m + " "):
                og.setdefault(base_key(variant_of(r)[0]), p)
    for f in assets:
        rel = "/" + os.path.relpath(f, SITE).replace(os.sep, "/").split("@")[0].split("?")[0]
        s = open(f, encoding="utf-8", errors="ignore").read()
        found = refs_in(s)
        for m in re.finditer(r"url\(\s*['\"]?([^'\")]+\.(?:" + EXT + r"))(?:\?[^'\")]*)?['\"]?\s*\)", s, re.I):
            if m.group(1).startswith("data:"):
                continue
            found |= refs_in(" " + urllib.parse.urljoin("https://" + HOSTS[0] + rel, m.group(1)) + " ")
        for r in found:
            theme.add(r)
            used_on.setdefault(r, set())
            primary.add(r)

    groups = {}
    for r in used_on:
        v, _ = variant_of(r)
        ext = v.rsplit(".", 1)[-1].lower()
        if ext not in ALL or "/fonts/" in v.lower():  # icon-font SVGs stay with their stylesheet
            continue
        groups.setdefault(base_key(v), {}).setdefault(v, set()).update(used_on[r])
        if r in primary:
            primary.add(v)
        if r in theme:
            theme.add(v)

    files, refmap, taken, missing = {}, {}, set(), []
    for base, variants in sorted(groups.items()):
        sized = {v: size_in_name(v) for v in variants}
        biggest = max((s for s in sized.values() if s), default=None, key=lambda s: s[0] * s[1])
        ratio = biggest[0] / biggest[1] if biggest else None
        fams = {}
        for v, s in sized.items():
            crop = "%dx%d" % s if (s and ratio and abs(s[0] / s[1] - ratio) > 0.02 * ratio) else ""
            fams.setdefault(crop, []).append(v)
        for crop, vs in sorted(fams.items()):
            def area(v):
                s = sized[v]
                return s[0] * s[1] if s else 10 ** 9  # the unsuffixed original is the largest
            prim = [v for v in vs if v in primary]
            cands = sorted(prim or vs, key=area, reverse=True)
            src = next((v for v in cands + sorted(vs, key=area, reverse=True) if local_file(v)), None)
            if not src:
                missing.append(base + (" (" + crop + ")" if crop else ""))
                continue
            pg = set().union(*(variants[v] for v in vs))
            if base in og and not crop:
                key = page_key(og[base])
            elif any(v in theme for v in vs) or len(pg) >= A.site_wide_pages or not pg:
                key = "site-wide"
            else:
                key = page_key(min(pg, key=lambda p: (p != "/", p.count("/"), p)))
            ext = src.rsplit(".", 1)[-1].lower().replace("jpeg", "jpg")
            stem = slug(os.path.splitext(os.path.basename(base))[0]) + ("-" + crop if crop else "")
            name = "%s--%s--%s.%s" % (A.prefix, key, stem or "file", ext)
            n = 2
            while os.path.splitext(name)[0].lower() in taken:
                name = re.sub(r"(-\d+)?\.(\w+)$", r"-%d.\2" % n, name)
                n += 1
            taken.add(os.path.splitext(name)[0].lower())
            info = {"kind": KIND[ext if ext in KIND else "jpg"], "source": src, "pages": sorted(pg, key=lambda p: (p != "/", p))}
            files[name] = info
            for v in vs:
                refmap[v] = name
                refmap[v + ".webp"] = name  # EWWW copies point at the same file

    # Files, pixel sizes and zips.
    try:
        from PIL import Image
    except ImportError:
        Image = None
        print("Pillow not installed: pixel sizes skipped (pip install pillow)")
    dirs = {k: os.path.join(OUT, k) for k in ("images", "videos", "documents")}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
    for name, info in files.items():
        src = local_file(info["source"])
        dest = os.path.join(dirs[info["kind"]], name)
        with open(src, "rb") as a, open(dest, "wb") as b:
            b.write(a.read())
        info["bytes"] = os.path.getsize(dest)
        if Image and info["kind"] == "images" and not name.endswith(".svg"):
            try:
                with Image.open(dest) as im:
                    info["width"], info["height"] = im.size
            except Exception:
                pass
    zips = {}
    for k, d in dirs.items():
        names = sorted(os.listdir(d))
        if not names:
            continue
        zp = os.path.join(OUT, "%s-%s.zip" % (A.prefix, k))
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as zf:
            for f in names:
                zf.write(os.path.join(d, f), f)
        zips[os.path.basename(zp)] = (len(names), round(os.path.getsize(zp) / 1e6, 1))

    json.dump({"hosts": HOSTS, "prefix": A.prefix, "files": files, "refs": dict(sorted(refmap.items()))},
              open(os.path.join(OUT, "media-map.json"), "w"), indent=1)
    with open(os.path.join(OUT, "media-manifest.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "kind", "original", "pages using it"])
        for name, info in sorted(files.items()):
            host, path = split_ref(info["source"])
            w.writerow([name, info["kind"], "https://" + host + path, " ".join(info["pages"]) or "(stylesheets)"])
    print("pages scanned:", len(pages), "| stylesheets/scripts scanned:", len(assets))
    for z, (n, mb) in zips.items():
        print("  %s: %d files, %.1f MB" % (z, n, mb))
    if missing:
        print("not found in the capture%s (%d):" % ("" if A.fetch else "; rerun with --fetch to download", len(missing)))
        for m in missing[:40]:
            print("  " + m)


if __name__ == "__main__":
    main()

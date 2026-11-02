#!/usr/bin/env python3
"""After the user uploads the zips: match the uploaded files to media-map.json and write media-urls.json.

Input: one or more Media Storage listings saved from HighLevel (the GHL connector's fetch-media-content operation,
params {altType:"location", type:"file", sortBy:"updatedAt", sortOrder:"desc", fetchAll:"true", limit:"1000",
offset}; each call returns up to 1000 files, so page with offset until fewer come back, or narrow it with
query=<prefix>). Each file in the listing has name, url, size (bytes) and deleted.

Files are matched by name (media_collect.py makes every name unique) and checked by size. HighLevel may add
"(1)" or similar to a name that already exists in the folder; those count as a match when the size agrees.

Output: media-urls.json {file name: Media Storage URL} and media-dims-by-url.json {URL: [width, height]} for
lib/hl_images.py, next to media-map.json. Prints what is missing or doesn't match, so the user can upload again.

Usage: python3 -I media_match.py <out dir with media-map.json> <listing.json> [<listing.json> ...]
"""
import json
import os
import re
import sys

out_dir = sys.argv[1]
mm = json.load(open(os.path.join(out_dir, "media-map.json")))
listing = []
for f in sys.argv[2:]:
    s = open(f, encoding="utf-8").read()
    d = json.loads(s[s.find("{"):])
    d = d.get("data", d)
    listing += d.get("files", d if isinstance(d, list) else [])
by_name = {}
for f in listing:
    if f.get("deleted") or f.get("type") == "folder":
        continue
    name = f.get("name") or ""
    clean = re.sub(r"\s*\(\d+\)(?=\.\w+$)", "", name)
    by_name.setdefault(clean.lower(), []).append(f)

urls, dims, missing, wrong = {}, {}, [], []
for name, info in mm["files"].items():
    cands = by_name.get(name.lower(), [])
    good = [c for c in cands if not info.get("bytes") or not c.get("size") or int(c["size"]) == info["bytes"]]
    if good:
        u = good[0]["url"]
        urls[name] = u
        w, h = info.get("width") or good[0].get("width"), info.get("height") or good[0].get("height")
        if w and h:
            dims[u] = [int(w), int(h)]
    elif cands:
        wrong.append("%s (uploaded %s bytes, expected %s)" % (name, cands[0].get("size"), info.get("bytes")))
    else:
        missing.append(name)

json.dump(urls, open(os.path.join(out_dir, "media-urls.json"), "w"), indent=1)
json.dump(dims, open(os.path.join(out_dir, "media-dims-by-url.json"), "w"), indent=1)
print("matched %d of %d files" % (len(urls), len(mm["files"])))
for label, xs in (("not uploaded", missing), ("size differs", wrong)):
    if xs:
        print("%s (%d):" % (label, len(xs)))
        for x in xs[:50]:
            print("  " + x)
sys.exit(1 if missing or wrong else 0)

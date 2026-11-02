#!/usr/bin/env python3
"""Compare two screenshot folders from shots.js: page height changes and the share of changed pixels per page.

    python3 -I shots_diff.py shots-old shots-new [diff-images-dir] [--threshold 24]

Anything above 0.00% needs a look: open the diff image (changed pixels in white) and the two screenshots. Expect
small changes from fonts that were swapped on purpose, video frames and carousels; anything else is a regression.
"""
import os
import sys
from PIL import Image, ImageChops

args = [a for a in sys.argv[1:] if not a.startswith("--")]
thr = int(sys.argv[sys.argv.index("--threshold") + 1]) if "--threshold" in sys.argv else 24
a, b = args[0], args[1]
outd = args[2] if len(args) > 2 else None
changed_pages = 0
for f in sorted(os.listdir(a)):
    if not f.endswith(".png"):
        continue
    if not os.path.exists(os.path.join(b, f)):
        print("%-60s MISSING in %s" % (f, b))
        continue
    A = Image.open(os.path.join(a, f)).convert("RGB")
    B = Image.open(os.path.join(b, f)).convert("RGB")
    note = "" if A.size == B.size else "  HEIGHT %d -> %d" % (A.height, B.height)
    w, h = min(A.width, B.width), min(A.height, B.height)
    d = ImageChops.difference(A.crop((0, 0, w, h)), B.crop((0, 0, w, h))).convert("L").point(lambda v: 255 if v > thr else 0)
    pct = d.histogram()[255] / (w * h) * 100
    if pct > 0 or note:
        changed_pages += 1
    print("%-60s %6.2f%%  %s%s" % (f, pct, d.getbbox() or "", note))
    if outd and pct > 0.01:
        os.makedirs(outd, exist_ok=True)
        d.save(os.path.join(outd, f))
print("\n%d page(s) differ" % changed_pages)

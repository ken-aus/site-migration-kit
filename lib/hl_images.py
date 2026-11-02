"""HighLevel image service: serve Media Storage photos as WebP, sized for the screen.

    https://images.leadconnectorhq.com/image/f_webp/q_80/r_<width>/u_<Media Storage file URL>

The service converts to WebP on the fly, resizes to the width asked for, never upscales, and returns the original
file when a WebP would not be smaller. So upload the originals only (JPEG, PNG, GIF, SVG); no separate WebP set.

Rules learned on past migrations:
- Give every <img> a srcset of widths AND an explicit sizes value. Without sizes the browser shows the picture at
  the chosen file's own width, which changed layouts.
- Never list a width above the original's (it returns the original anyway, labelled wrongly: a 1024 px file labelled
  2048w displayed at the wrong size).
- Animated GIFs keep their original file (resizing can drop the animation). SVGs are not resized.
- Meta tags (og:image, twitter:image) and schema images use the plain Media Storage URL, which every crawler reads.

Usage: rewrite_imgs(html, dims) where dims maps Media Storage URL -> [width, height] (media_collect.py writes
media-dims.json keyed by file name; media_match.py turns that into URL keys).
"""
import re

SERVICE = "https://images.leadconnectorhq.com/image/f_webp/q_%d/r_%d/u_%s"
MEDIA_URL = r"https://(?:assets\.cdn\.filesafe\.space|storage\.googleapis\.com/msgsndr)/[A-Za-z0-9]+/media/[^\s\"'<>(),]+?\.(?:jpe?g|png|webp)"
MEDIA_RE = re.compile(r"(?<!/u_)" + MEDIA_URL, re.I)
WIDTHS = (480, 768, 960, 1200, 1440, 1920)
MAX_W = 1920


def resized(url, width, dims=None, quality=80):
    """Service URL for url at most `width` px wide (capped at the original's width when dims are known)."""
    nat = (dims or {}).get(url)
    if nat:
        width = min(width, nat[0])
    return SERVICE % (quality, width, url)


def srcset(url, dims, widths=WIDTHS, max_w=MAX_W):
    nat = dims[url][0]
    ws = sorted(set([w for w in widths if w < nat] + [min(nat, max_w)]))
    return ", ".join("%s %dw" % (resized(url, w, dims), w) for w in ws)


ATTR = re.compile(r"""\s([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?""")


def attrs_of(tag):
    inner = re.match(r"<[a-zA-Z0-9]+\b(.*?)\s*/?>$", tag, re.S).group(1)
    out = []
    for m in ATTR.finditer(inner):
        v = m.group(2) if m.group(2) is not None else m.group(3) if m.group(3) is not None else m.group(4)
        out.append([m.group(1), v])
    return out


def tag_of(name, attrs):
    return "<%s %s>" % (name, " ".join(k if v is None else '%s="%s"' % (k, v.replace('"', "&quot;")) for k, v in attrs))


def img_tag(tag, dims, lazy=True, default_sizes=None, add_dims=False):
    """One <img> rewritten: src through the service, srcset and sizes added, loading/decoding set.
    lazy=False for the first (hero) image: it gets fetchpriority=high instead.
    add_dims=True adds width/height from the file when the tag has neither (stops layout shift, but check the page's
    CSS caps image width first, or a large photo will display at full size)."""
    a = attrs_of(tag)
    d = {k.lower(): v for k, v in a}
    src = d.get("src") or ""
    if not MEDIA_RE.fullmatch(src) or src not in dims:
        return tag
    out = [[k, v] for k, v in a if k.lower() not in ("srcset", "sizes", "loading", "decoding", "fetchpriority")]
    out = [[k, resized(v, MAX_W, dims) if k.lower() == "src" else v] for k, v in out]
    out.append(["srcset", srcset(src, dims)])
    w = d.get("width") if (d.get("width") or "").isdigit() else str(min(dims[src][0], MAX_W))
    out.append(["sizes", default_sizes or "(max-width: %spx) 100vw, %spx" % (w, w)])
    if add_dims and not d.get("width") and not d.get("height"):
        out += [["width", str(dims[src][0])], ["height", str(dims[src][1])]]
    out += [["loading", "lazy"], ["decoding", "async"]] if lazy else [["fetchpriority", "high"]]
    return tag_of("img", out)


SKIP = re.compile(r"(<meta\b[^>]*>|<link\b[^>]*>|<script[^>]+application/ld\+json[^>]*>.*?</script>|<noscript\b.*?</noscript>)", re.S | re.I)


def rewrite_imgs(html, dims, hero_first=True):
    """Every Media Storage <img> on the page; other references (CSS backgrounds, data attributes) get the 1920 px
    WebP. Meta tags, JSON-LD and noscript copies are left alone. The first image on the page is treated as the hero
    (not lazy) when hero_first is set; pass False when the hero is a CSS background or slider."""
    parts = SKIP.split(html)
    first = [hero_first]

    def one(m):
        lazy = not first[0]
        first[0] = False
        return img_tag(m.group(0), dims, lazy=lazy)
    for i in range(0, len(parts), 2):
        t = re.sub(r"<img\b[^>]*>", one, parts[i], flags=re.I)
        parts[i] = MEDIA_RE.sub(lambda m: resized(m.group(0), MAX_W, dims) if not m.group(0).lower().endswith(".gif") else m.group(0), t)
    return "".join(parts)


def rewrite_css(css, dims):
    """Background images in a stylesheet: the 1920 px WebP."""
    return MEDIA_RE.sub(lambda m: resized(m.group(0), MAX_W, dims), css)

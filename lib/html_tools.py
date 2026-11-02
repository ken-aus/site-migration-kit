"""HTML helpers shared by the migration tools and site build scripts.

Regex-based on purpose: captured pages are kept byte-for-byte except where a change is made, which an HTML parser
round trip would not guarantee. Import with:  sys.path.insert(0, "<kit>/lib"); import html_tools as H
"""
import html as htmllib
import json
import re


def elem_end(html, start):
    """Index just after the element that starts at html[start] ('<div ...'), counting nested tags of the same name."""
    tag = re.match(r"<([a-zA-Z0-9-]+)", html[start:]).group(1)
    pat = re.compile(r"<(/?)%s\b[^>]*?(/?)>" % re.escape(tag), re.I)
    depth = 0
    for m in pat.finditer(html, start):
        if m.group(1):
            depth -= 1
        elif not m.group(2):
            depth += 1
        if depth == 0:
            return m.end()
    raise ValueError("unclosed <%s> at %d" % (tag, start))


def element_by_id(html, el_id):
    """The whole element whose id is el_id, or None."""
    m = re.search(r'<[a-zA-Z0-9-]+\b[^>]*\bid="%s"' % re.escape(el_id), html)
    return html[m.start():elem_end(html, m.start())] if m else None


def text_of(fragment):
    """Visible text: tags, scripts, styles and noscript removed, entities decoded, whitespace collapsed."""
    t = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<noscript\b.*?</noscript>", " ", fragment, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", htmllib.unescape(t)).strip()


def esc(s):
    return htmllib.escape(s, quote=True)


# ---------- Head: title, description, canonical, robots ----------
def title_of(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return htmllib.unescape(m.group(1)).strip() if m else ""


def meta(html, name, prop=False):
    """Content of <meta name=...> (or property=... with prop=True), attribute order independent."""
    key = "property" if prop else "name"
    for m in re.finditer(r"<meta\b[^>]*>", html, re.I):
        t = m.group(0)
        if re.search(r'\b%s=["\']%s["\']' % (key, re.escape(name)), t, re.I):
            c = re.search(r'\bcontent=(["\'])(.*?)\1', t, re.S | re.I)
            return htmllib.unescape(c.group(2)) if c else ""
    return None


def canonical(html):
    for m in re.finditer(r"<link\b[^>]*>", html, re.I):
        t = m.group(0)
        if re.search(r'\brel=["\']canonical["\']', t, re.I):
            h = re.search(r'\bhref=["\']([^"\']+)', t)
            return h.group(1) if h else ""
    return ""


def set_title(html, title, og=True):
    t = esc(title)
    html = re.sub(r"<title[^>]*>.*?</title>", "<title>%s</title>" % t.replace("\\", "\\\\"), html, count=1, flags=re.S | re.I)
    if og:
        for key, name in (("property", "og:title"), ("name", "twitter:title")):
            html = re.sub(r'(<meta %s="%s" content=")[^"]*(")' % (key, name), lambda m: m.group(1) + t + m.group(2), html, count=1)
    return html


def set_description(html, desc):
    d = esc(desc)
    if re.search(r'<meta name="description"', html):
        html = re.sub(r'(<meta name="description" content=")[^"]*(")', lambda m: m.group(1) + d + m.group(2), html, count=1)
    else:
        html = re.sub(r"(</title>)", lambda m: m.group(1) + '\n<meta name="description" content="%s">' % d, html, count=1)
    html = re.sub(r'(<meta property="og:description" content=")[^"]*(")', lambda m: m.group(1) + d + m.group(2), html, count=1)
    return html


# ---------- JSON-LD ----------
def _ld(data):
    return '<script type="application/ld+json">%s</script>' % json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def add_jsonld(html, data):
    return html.replace("</head>", _ld(data) + "\n</head>", 1)


def jsonld_blocks(html):
    for m in re.finditer(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            yield m, json.loads(m.group(1))
        except ValueError:
            continue


def rewrite_jsonld(html, fn):
    """Apply fn(data) -> data to every JSON-LD block (fn returns None to drop the block)."""
    out, pos = [], 0
    for m, data in list(jsonld_blocks(html)):
        new = fn(data)
        out.append(html[pos:m.start()])
        if new is not None:
            out.append(_ld(new))
        pos = m.end()
    out.append(html[pos:])
    return "".join(out)


def graph_nodes(data):
    if isinstance(data, dict) and "@graph" in data:
        return data["@graph"]
    return [data] if isinstance(data, dict) else (data or [])


def schema_types(html):
    """Every @type in the page's JSON-LD (nested nodes included)."""
    found = set()

    def walk(x):
        if isinstance(x, dict):
            t = x.get("@type")
            for v in (t if isinstance(t, list) else [t]):
                if v:
                    found.add(v)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for _m, data in jsonld_blocks(html):
        walk(data)
    return found


# ---------- One H1 per page ----------
def one_h1(html, cls="demoted-h1"):
    """Keep the first non-empty H1; empty H1s are removed and later ones become <h2 class="demoted-h1">. Pair with
    h1_css() so they look exactly as before. Returns (html, changes)."""
    hs = list(re.finditer(r"<h1\b([^>]*)>(.*?)</h1>", html, re.S | re.I))
    if len(hs) <= 1:
        return html, 0
    kept, out, pos, n = False, [], 0, 0
    for m in hs:
        out.append(html[pos:m.start()])
        if not text_of(m.group(2)):
            n += 1
        elif not kept:
            kept = True
            out.append(m.group(0))
        else:
            attrs = m.group(1)
            attrs = re.sub(r'\bclass="', 'class="%s ' % cls, attrs, count=1) if re.search(r'\bclass="', attrs) else attrs + ' class="%s"' % cls
            out.append("<h2%s>%s</h2>" % (attrs, m.group(2)))
            n += 1
        pos = m.end()
    out.append(html[pos:])
    return "".join(out), n


H1_TOKEN = re.compile(r"(?<![\w.#-])h1(?![\w-])", re.I)


def h1_css(css_texts, cls="demoted-h1"):
    """Every CSS rule that styles an h1, repeated for h2.<cls> with :where() (same specificity as h1), so headings
    demoted by one_h1() keep their look. Pass the page's inline styles and stylesheets."""
    out = []

    def walk(css):
        res, i, n = [], 0, len(css)
        while i < n:
            j = css.find("{", i)
            if j < 0:
                break
            prelude = css[i:j].strip()
            depth, k = 1, j + 1
            while k < n and depth:
                depth += {"{": 1, "}": -1}.get(css[k], 0)
                k += 1
            block = css[j + 1:k - 1]
            low = prelude.lower()
            if low.startswith(("@media", "@supports", "@container", "@layer")):
                inner = walk(block)
                if inner:
                    res.append("%s{%s}" % (prelude, "".join(inner)))
            elif not low.startswith("@"):
                hit = [H1_TOKEN.sub("h2:where(.%s)" % cls, x.strip()) for x in prelude.split(",") if H1_TOKEN.search(x)]
                if hit:
                    res.append("%s{%s}" % (",".join(hit), block))
            i = k
        return res
    for t in css_texts:
        out.extend(walk(re.sub(r"/\*.*?\*/", "", t, flags=re.S)))
    return "\n".join(dict.fromkeys(out)) + "\n"


# ---------- Cloudflare email protection ----------
def decode_cf_email(hexs):
    """Cloudflare's /cdn-cgi/l/email-protection#<hex> and data-cfemail="<hex>" back to the address."""
    key = int(hexs[:2], 16)
    return "".join(chr(int(hexs[i:i + 2], 16) ^ key) for i in range(2, len(hexs), 2))


def undo_cf_email(html):
    html = re.sub(r'<a\b[^>]*href="/cdn-cgi/l/email-protection#([0-9a-f]+)"',
                  lambda m: m.group(0).replace("/cdn-cgi/l/email-protection#" + m.group(1), "mailto:" + decode_cf_email(m.group(1))), html)
    html = re.sub(r'<span class="__cf_email__" data-cfemail="([0-9a-f]+)">\[email&#160;protected\]</span>',
                  lambda m: esc(decode_cf_email(m.group(1))), html)
    return re.sub(r'<script[^>]*src="/cdn-cgi/scripts/[^"]*email-decode[^"]*"[^>]*></script>', "", html)

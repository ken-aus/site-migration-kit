"""Speed changes for captured pages, platform independent. Each function takes and returns page HTML (or a dict of
pages) and leaves everything else byte-for-byte, so before/after screenshots compare cleanly.

Order that has worked on past migrations:
  1. strip_tracking (dev only)              6. lazy_iframes / lazy_on_interaction
  2. hl_images.rewrite_imgs                  7. squeeze
  3. hero_preload                            8. SharedBlocks: count on every page, then externalise
  4. fonts_swap                              9. check: screenshots, accessibility snapshot, WebPageTest
  5. drop_tags (builder leftovers)

Lessons built in:
- Third-party widgets (chat, reCAPTCHA, Drift, MemberSpace, Vimeo/YouTube players) load on the first scroll, tap,
  key press, mouse move or form focus. A script that waits for DOMContentLoaded must be adapted, as that event has
  passed when it loads (Contact Form 7's reCAPTCHA module needed a copy that starts at once).
- Booking calendars and form iframes load when scrolled within 1500 px (each HighLevel calendar is about 120 files
  and 1.2 MB). Native loading=lazy is enough for other iframes.
- Order-sensitive inline scripts stay inline: moving Slider Revolution's small set-up script to a file broke a home
  page slider. Only scripts of 1,000+ bytes move; styles can move from 300 bytes.
- Never animate box-shadow forever (HighLevel's "pulse glow" used 40% of a phone's main thread): animate the
  opacity and scale of a pseudo-element instead (PULSE_GLOW_CSS below).
"""
import hashlib
import os
import re

SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)
STYLE = re.compile(r"<style\b([^>]*)>(.*?)</style>", re.S | re.I)


# ---------- 1. Tracking off on dev ----------
TRACKING = re.compile(
    r"googletagmanager\.com|google-analytics\.com|gtag\(|fbq\(|connect\.facebook\.net|stats\.wp\.com|_stq\b|"
    r"monsterinsights|hotjar|clarity\.ms|analytics\.tiktok|snap\.licdn|bat\.bing|ahrefs\.com/analytics|plausible\.io", re.I)


def strip_tracking(html):
    """Remove the client's analytics and ad tags (inline or external) and GTM noscript iframes. Dev copies only:
    note what was removed, so one Google tag and one Meta pixel can be restored at go-live."""
    html = SCRIPT.sub(lambda m: "" if TRACKING.search(m.group(1)) or TRACKING.search(m.group(2)) else m.group(0), html)
    html = re.sub(r"<noscript>\s*<iframe[^>]*googletagmanager\.com.*?</noscript>", "", html, flags=re.S | re.I)
    html = re.sub(r"<noscript>\s*<img[^>]*facebook\.com/tr.*?</noscript>", "", html, flags=re.S | re.I)
    return re.sub(r"<link\b[^>]*(?:googletagmanager|google-analytics)[^>]*>", "", html, flags=re.I)


# ---------- 3. Hero ----------
def hero_preload(html, url, srcset=None, sizes=None):
    """Preload the first-screen image at high priority (the LCP element on most pages)."""
    extra = (' imagesrcset="%s" imagesizes="%s"' % (srcset, sizes or "100vw")) if srcset else ""
    tag = '<link rel="preload" as="image" href="%s"%s fetchpriority="high">' % (url, extra)
    return html.replace("</title>", "</title>\n" + tag, 1) if "</title>" in html else html.replace("<head>", "<head>" + tag, 1)


# ---------- 4. Fonts ----------
def fonts_swap(html):
    """Google Fonts: display=swap, duplicate stylesheet links merged, and the stylesheet made non-blocking.
    Better still: self-host the font files actually used, and subset icon fonts."""
    seen = set()

    def one(m):
        tag = m.group(0)
        href = re.search(r'href=["\']([^"\']+)', tag).group(1).replace("&amp;", "&")
        if href in seen:
            return ""
        seen.add(href)
        if "display=" not in href:
            tag = tag.replace(m.group(1), m.group(1) + ("&amp;" if "?" in m.group(1) else "?") + "display=swap")
        if "media=" not in tag:
            tag = tag[:-1] + ' media="print" onload="this.media=\'all\'">'
        return tag
    return re.sub(r'<link\b[^>]*href=["\'](https://fonts\.googleapis\.com/[^"\']+)["\'][^>]*>', one, html, flags=re.I)


# ---------- 5. Builder leftovers ----------
def drop_tags(html, patterns):
    """Remove <link>/<script>/<style> tags matching any regex in `patterns` (e.g. editor-only WordPress styles
    r"id=['\\"]wp-(components|preferences|block-editor)-css", an unused page builder's frontend CSS, a duplicate
    Font Awesome). Check the builder really builds nothing first: count its data attributes, not its body class."""
    rx = re.compile("|".join(patterns), re.I)
    html = re.sub(r"<link\b[^>]*>\s*", lambda m: "" if rx.search(m.group(0)) else m.group(0), html, flags=re.I)
    return SCRIPT.sub(lambda m: "" if rx.search(m.group(1)) else m.group(0), html)


# HighLevel's "Pulse Glow" button effect redone without animating box-shadow: the glow is drawn once on a
# pseudo-element and only its opacity and scale animate, which the graphics card handles on its own. Add to the
# site stylesheet; the look is the same.
PULSE_GLOW_CSS = (
    ".buttonPulseGlow,.buttonPulseGlow:hover{animation:none!important}.buttonPulseGlow{position:relative!important}"
    ".buttonPulseGlow::after{content:\"\";position:absolute;top:-2px;right:-2px;bottom:-2px;left:-2px;border-radius:inherit;"
    "pointer-events:none;box-shadow:0 0 5px 3px #ffffff80;opacity:0;animation:pulseGlowLite 2s ease-in-out infinite}"
    "@keyframes pulseGlowLite{0%{opacity:0;transform:scale(1)}25%{opacity:.4;transform:scale(1)}50%{opacity:1;transform:scale(1)}"
    "85%{opacity:0;transform:scale(1.015)}to{opacity:0;transform:scale(1)}}")


# ---------- 6. Lazy loading ----------
INTERACTION_LOADER = (
    '<script>(function(){var d=0,ev=["scroll","pointerdown","touchstart","keydown","mousemove","focusin"];'
    'function go(){if(d)return;d=1;ev.forEach(function(e){removeEventListener(e,go,{passive:true})});'
    '[].forEach.call(document.querySelectorAll("iframe[data-lazy-src]"),function(f){f.src=f.getAttribute("data-lazy-src")});'
    'var l=[].slice.call(document.querySelectorAll(\'script[type="text/lazy"]\'));(function n(){var o=l.shift();'
    'if(!o)return;var s=document.createElement("script"),a=o.attributes;for(var i=0;i<a.length;i++)'
    'if(a[i].name!=="type"&&a[i].name!=="data-src")s.setAttribute(a[i].name,a[i].value);'
    'if(o.getAttribute("data-src")){s.src=o.getAttribute("data-src");s.async=false;s.onload=s.onerror=n;'
    'o.parentNode.replaceChild(s,o)}else{s.text=o.text;o.parentNode.replaceChild(s,o);n()}})()}'
    'ev.forEach(function(e){addEventListener(e,go,{passive:true})})})();</script>')
NEAR_LOADER = (
    '<script>(function(){var f=[].slice.call(document.querySelectorAll("iframe[data-near-src]"));if(!f.length)return;'
    'function load(x){if(x.getAttribute("data-near-src")){x.src=x.getAttribute("data-near-src");x.removeAttribute("data-near-src");'
    'if(window.cfNearLoaded)window.cfNearLoaded(x)}}'
    'if(!("IntersectionObserver" in window)){f.forEach(load);return}'
    'var o=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){o.unobserve(e.target);load(e.target)}})},'
    '{rootMargin:"1500px 0px"});f.forEach(function(x){o.observe(x)})})();</script>')
DEFAULT_LAZY = re.compile(r"google\.com/recaptcha/api\.js|js\.driftt\.com|window\.driftt|cdn\.memberspace\.com|"
                          r"widgets\.leadconnectorhq\.com/loader\.js|embed\.tawk\.to|static\.zdassets\.com|js\.intercomcdn\.com", re.I)
VIDEO_IFRAME = re.compile(r'(<iframe\b[^>]*?\s)src=("https://(?:player\.vimeo\.com|www\.youtube(?:-nocookie)?\.com)/[^"]*")', re.I)
NEAR_IFRAME = re.compile(r'(<iframe\b[^>]*?\s)src=("https://(?:[a-z0-9.-]*leadconnectorhq\.com|[a-z0-9.-]*msgsndr\.com|link\.[a-z0-9.-]+)/(?:widget/booking|widget/form|widget/survey|widget/group)[^"]*")', re.I)


def lazy_on_interaction(html, pattern=DEFAULT_LAZY, videos=True):
    """Scripts matching `pattern` (by src or body) and video player iframes wait for the visitor's first interaction."""
    n = [0]

    def one(m):
        attrs, body = m.group(1), m.group(2)
        src = re.search(r"""\bsrc=["']([^"']+)["']""", attrs)
        if src and pattern.search(src.group(1)):
            rest = re.sub(r"""\s(?:src|type|async|defer)(?:=["'][^"']*["'])?""", "", attrs)
            n[0] += 1
            return '<script type="text/lazy" data-src="%s"%s></script>' % (src.group(1), rest)
        if not src and pattern.search(body) and "ld+json" not in attrs:
            n[0] += 1
            return '<script type="text/lazy">%s</script>' % body
        return m.group(0)
    html = SCRIPT.sub(one, html)
    if videos:
        html, k = VIDEO_IFRAME.subn(lambda m: m.group(1) + "data-lazy-src=" + m.group(2), html)
        n[0] += k
    if n[0]:
        i = html.rfind("</body>")
        html = html[:i] + INTERACTION_LOADER + html[i:] if i >= 0 else html + INTERACTION_LOADER
    return html


def lazy_iframes(html, near=NEAR_IFRAME):
    """Booking calendars and forms load when scrolled within 1500 px; every other iframe gets loading=lazy.
    The iframe must keep its reserved height (check for layout shift). HighLevel's form_embed.js (which sizes the
    iframe) should load with the first one: set window.cfNearLoaded to load it."""
    html, k = near.subn(lambda m: m.group(1) + "data-near-src=" + m.group(2), html)
    html = re.sub(r"<iframe\b(?![^>]*\bloading=)", '<iframe loading="lazy"', html, flags=re.I)
    if k:
        i = html.rfind("</body>")
        html = html[:i] + NEAR_LOADER + html[i:] if i >= 0 else html + NEAR_LOADER
    return html


# ---------- 7. Smaller HTML ----------
KEEP_WS = re.compile(r"(<(?:pre|textarea|script|style)\b.*?</(?:pre|textarea|script|style)>)", re.S | re.I)
COMMENT = re.compile(r"<!--(?!\s*\[if|\s*<!\[endif).*?-->", re.S)


def squeeze(html):
    """Drop HTML comments (IE conditionals kept) and collapse whitespace between tags. Rendering is unchanged."""
    parts = KEEP_WS.split(html)
    return "".join(t if i % 2 else re.sub(r">\s+<", "> <", re.sub(r"\n[ \t]+", "\n", COMMENT.sub("", t))) for i, t in enumerate(parts))


# ---------- 8. Shared blocks ----------
class SharedBlocks:
    """Inline <style> and <script> blocks repeated on many pages move to shared files with content-hashed names, in
    the same position (so order is kept), and browsers cache them. Two passes: count(html) for every page, then
    externalise(html) for every page.

        sb = SharedBlocks(public_dir, "/assets/shared/")
        for h in pages.values(): sb.count(h)
        pages = {p: sb.externalise(h) for p, h in pages.items()}

    On AI Studio, files in public/ are served with max-age=0; for a year-long cache serve them from the server code
    at a content-hashed address with cache-control max-age=31536000, immutable, or through Cloudflare."""
    JS_TYPES = ("", "text/javascript", "application/javascript", "module")
    KEEP_INLINE = re.compile(r"RS_MODULES|setREVStartSize|revslider|revapi|document\.write|document\.currentScript", re.I)

    def __init__(self, public, url_dir, min_style=300, min_script=1000, min_pages=3, big_style=20000):
        self.public, self.url_dir = public, "/" + url_dir.strip("/") + "/"
        self.min_style, self.min_script, self.min_pages, self.big_style = min_style, min_script, min_pages, big_style
        self.pages = {}

    def _movable(self, attrs, body):
        t = re.search(r"\btype=[\"']([^\"']*)[\"']", attrs, re.I)
        return (not re.search(r"\bsrc=", attrs, re.I) and (t.group(1).strip().lower() if t else "") in self.JS_TYPES
                and len(body) >= self.min_script and not self.KEEP_INLINE.search(body))

    def count(self, html):
        found = {m.group(0) for m in STYLE.finditer(html) if len(m.group(2)) >= self.min_style}
        found |= {m.group(0) for m in SCRIPT.finditer(html) if self._movable(m.group(1), m.group(2))}
        for b in found:
            self.pages[b] = self.pages.get(b, 0) + 1

    def _file(self, body, ext):
        name = hashlib.sha256(body.encode("utf-8", "surrogateescape")).hexdigest()[:16] + ext
        dest = os.path.join(self.public, self.url_dir.strip("/"), name)
        if not os.path.isfile(dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            open(dest, "w", encoding="utf-8", errors="surrogateescape").write(body)
        return self.url_dir + name

    def externalise(self, html):
        def style(m):
            attrs, body = m.group(1), m.group(2)
            if not (len(body) >= self.big_style or (len(body) >= self.min_style and self.pages.get(m.group(0), 0) >= self.min_pages)):
                return m.group(0)
            keep = " ".join(re.findall(r"\b(?:id|media)=[\"'][^\"']*[\"']", attrs))
            return '<link rel="stylesheet" href="%s"%s>' % (self._file(body, ".css"), (" " + keep) if keep else "")

        def script(m):
            attrs, body = m.group(1), m.group(2)
            if not (self._movable(attrs, body) and self.pages.get(m.group(0), 0) >= self.min_pages):
                return m.group(0)
            return '<script%s src="%s"></script>' % (attrs, self._file(body, ".js"))
        return SCRIPT.sub(script, STYLE.sub(style, html))

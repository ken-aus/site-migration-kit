#!/usr/bin/env python3
"""Crawl a site and report broken links and files, with the pages that use them.

Run it against the local build (http://localhost:<port>) or the dev site, and against the old site for comparison
(a link already broken on the old site is the client's decision, not a migration fault).

Reports:
  BROKEN PAGE     internal link to a page that answers 4xx/5xx (with every page linking to it)
  BROKEN FILE     image, stylesheet, script, video or document that answers 4xx/5xx
  REDIRECTED      internal link that redirects (point the link straight at the final address)
  OLD HOST        links or files still on the old site's address (--old-host), except canonical/og/schema
  EXTERNAL        broken links to other sites (only with --external; many sites refuse robots, so check by hand)

Usage:
  python3 -I link_check.py http://localhost:4321 [--start /,/blog] [--sitemap /sitemap.xml] [--old-host example.com]
      [--host-alias example.com] [--max-pages 2000] [--external] [--json report.json]
  --host-alias: treat absolute links to this host as internal (a dev copy whose pages still link to the production
  domain), and check them on the base URL.
"""
import argparse
import concurrent.futures as cf
import html as htmllib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("base")
ap.add_argument("--start", default="/")
ap.add_argument("--sitemap")
ap.add_argument("--old-host", action="append", default=[])
ap.add_argument("--host-alias", action="append", default=[])
ap.add_argument("--max-pages", type=int, default=2000)
ap.add_argument("--external", action="store_true")
ap.add_argument("--json")
A = ap.parse_args()
BASE = A.base.rstrip("/")
BHOST = urllib.parse.urlparse(BASE).netloc.lower()
ALIASES = {h.lower() for h in A.host_alias} | {"www." + h.lower() for h in A.host_alias}
OLD = {h.lower() for h in A.old_host} | {"www." + h.lower() for h in A.old_host}
UA = {"User-Agent": "Mozilla/5.0 (site-migration-kit link check)"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPEN = urllib.request.build_opener(NoRedirect)


def status(url, method="HEAD"):
    """(status, location, body or None). GET for pages (to parse them); HEAD for files, falling back to GET."""
    p = urllib.parse.urlsplit(url)
    url = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(urllib.parse.unquote(p.path), safe="/%:@!$&'()*+,;=~"), p.query, ""))
    req = urllib.request.Request(url, headers=UA, method=method)
    try:
        r = OPEN.open(req, timeout=30)
        body = r.read() if method == "GET" else None
        return r.status, None, body, r.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        if e.code in (405, 403, 501) and method == "HEAD":
            return status(url, "GET")
        return e.code, e.headers.get("location"), None, e.headers.get("content-type", "")
    except Exception as e:
        return 0, str(e)[:80], None, ""


def internal(u):
    p = urllib.parse.urlparse(u)
    h = p.netloc.lower()
    if h in ("", BHOST) or h in ALIASES:
        return BASE + (p.path or "/") + ("?" + p.query if p.query else "")
    return None


SKIP_ATTR = re.compile(r"<link\b[^>]*rel=[\"'](?:canonical|alternate|shortlink|preconnect|dns-prefetch|profile|pingback|EditURI|wlwmanifest)[\"'][^>]*>|<meta\b[^>]*>|<script[^>]+application/ld\+json[^>]*>.*?</script>", re.S | re.I)


def refs(html, page_url):
    """(links, files) found on a page, as absolute URLs."""
    s = SKIP_ATTR.sub(" ", html)
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    links, files = set(), set()
    for m in re.finditer(r"<a\b[^>]*?\bhref=([\"'])(.*?)\1", s, re.S | re.I):
        links.add(m.group(2))
    for m in re.finditer(r"<(?:img|script|source|video|audio|iframe|embed)\b[^>]*?\b(?:src|poster)=([\"'])(.*?)\1", s, re.S | re.I):
        files.add(m.group(2))
    for m in re.finditer(r"<link\b[^>]*?\bhref=([\"'])(.*?)\1", s, re.S | re.I):
        files.add(m.group(2))
    for m in re.finditer(r"\bsrcset=([\"'])(.*?)\1", s, re.S | re.I):
        for part in m.group(2).split(","):
            if part.strip():
                files.add(part.strip().split()[0])
    out = []
    for group in (links, files):
        res = set()
        for v in group:
            v = htmllib.unescape(v.strip())
            if not v or v.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "sms:", "{", "$")):
                continue
            res.add(urllib.parse.urljoin(page_url, v).split("#")[0])
        out.append(res)
    return out


def main():
    starts = [BASE + p.strip() for p in A.start.split(",") if p.strip()]
    if A.sitemap:
        _s, _l, body, _t = status(BASE + A.sitemap, "GET")
        for loc in re.findall(r"<loc>([^<]+)</loc>", (body or b"").decode("utf-8", "ignore")):
            i = internal(loc.strip())
            if i:
                starts.append(i)
    seen_pages, queue, linked_from, file_from, pages_ok = set(), list(dict.fromkeys(starts)), {}, {}, {}
    redirected, old_refs, external = {}, {}, {}
    with cf.ThreadPoolExecutor(8) as pool:
        while queue and len(seen_pages) < A.max_pages:
            batch = [u for u in queue if u not in seen_pages][: A.max_pages - len(seen_pages)]
            queue = []
            seen_pages.update(batch)
            for url, (st, loc, body, ctype) in zip(batch, pool.map(lambda u: status(u, "GET"), batch)):
                pages_ok[url] = (st, loc)
                if st in (301, 302, 307, 308) and loc:
                    nxt = internal(urllib.parse.urljoin(url, loc))
                    if nxt and nxt not in seen_pages:
                        queue.append(nxt)
                    continue
                if st != 200 or not body or "html" not in ctype:
                    continue
                links, files = refs(body.decode("utf-8", "ignore"), url)
                for group, store in ((links, linked_from), (files, file_from)):
                    for v in group:
                        host = urllib.parse.urlparse(v).netloc.lower()
                        if host in OLD and host not in ALIASES:
                            old_refs.setdefault(v, set()).add(url)
                        i = internal(v)
                        if i:
                            store.setdefault(i, set()).add(url)
                            if store is linked_from and i not in seen_pages and not re.search(r"\.(?:pdf|jpe?g|png|gif|webp|svg|zip|docx?|xlsx?|mp4|mp3)$", urllib.parse.urlparse(i).path, re.I):
                                queue.append(i)
                        elif A.external and store is linked_from and v.startswith("http"):
                            external.setdefault(v, set()).add(url)
        # Files, and links to non-HTML things, by HEAD.
        to_check = [u for u in set(file_from) | {u for u in linked_from if u not in pages_ok}]
        file_st = dict(zip(to_check, pool.map(status, to_check)))
        ext_st = dict(zip(list(external), pool.map(status, list(external)))) if A.external else {}

    rel = lambda u: u[len(BASE):] or "/"
    report = {"broken_pages": {}, "broken_files": {}, "redirected": {}, "old_host": {}, "external": {}}
    for u, srcs in linked_from.items():
        st, loc = pages_ok.get(u, file_st.get(u, (0, None))[:2])
        if st >= 400 or st == 0:
            report["broken_pages"][rel(u)] = {"status": st, "linked_from": sorted(map(rel, srcs))[:20]}
        elif st in (301, 302, 307, 308):
            report["redirected"][rel(u)] = {"to": loc, "linked_from": sorted(map(rel, srcs))[:20]}
    for u, srcs in file_from.items():
        st = file_st.get(u, (0,))[0]
        if st >= 400 or st == 0:
            report["broken_files"][rel(u)] = {"status": st, "used_on": sorted(map(rel, srcs))[:20]}
    for u, srcs in old_refs.items():
        report["old_host"][u] = sorted(map(rel, srcs))[:20]
    for u, (st, *_r) in ext_st.items():
        if st >= 400 or st == 0:
            report["external"][u] = {"status": st, "linked_from": sorted(map(rel, external[u]))[:20]}

    print("Crawled %d pages from %s" % (len(seen_pages), BASE))
    for key, label in (("broken_pages", "BROKEN PAGE"), ("broken_files", "BROKEN FILE"), ("redirected", "REDIRECTED"),
                       ("old_host", "OLD HOST"), ("external", "EXTERNAL")):
        items = report[key]
        print("\n%s: %d" % (label, len(items)))
        for u, v in sorted(items.items())[:60]:
            if isinstance(v, dict):
                extra = (" -> " + str(v.get("to"))) if "to" in v else (" [%s]" % v.get("status"))
                srcs = v.get("linked_from") or v.get("used_on") or []
            else:
                extra, srcs = "", v
            print("  %s%s   on: %s%s" % (u, extra, ", ".join(srcs[:4]), " (+%d)" % (len(srcs) - 4) if len(srcs) > 4 else ""))
    if A.json:
        json.dump(report, open(A.json, "w"), indent=1)
    sys.exit(1 if report["broken_pages"] or report["broken_files"] else 0)


if __name__ == "__main__":
    main()

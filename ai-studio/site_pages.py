"""Write src/lib/site-pages.ts and src/lib/site-uploads.ts for ai-studio/server-static.ts.

    import site_pages
    site_pages.write(repo_dir, production_hosts=["example.com", "www.example.com"], pages=paths_written,
                     sitemap=indexable_self_canonical_paths, redirects={"/old/": "/new/"}, not_found_html=html_404,
                     uploads={"/wp-content/uploads/2024/01/x.jpg": "https://assets.cdn.filesafe.space/.../x.jpg"})

Sitemap rule: only pages that are indexable (no robots noindex) and are their own canonical; leave out tag, author,
feed and paginated archive pages unless the old site listed them. sitemap_paths() below does that from the HTML.
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import html_tools as H  # noqa: E402

TEMPLATE = r'''// Migrated site: the list of pages (built /*STAMP*/) and the 404 page. Written by site-migration-kit/ai-studio/site_pages.py.
// The pages themselves are static files in public/. Server-only module.
export const PRODUCTION_HOSTS = new Set(/*HOSTS*/);

const PATHS: string[] = /*PATHS*/;
const SET = new Set(PATHS);

export function hasPage(path: string): boolean {
  return SET.has(path);
}

// Pages listed in the production sitemap (indexable, self-canonical) and permanent redirects (old path -> new path).
const SITEMAP: string[] = /*SITEMAP*/;
export const REDIRECTS: Record<string, string> = /*REDIRECTS*/;

export function pagePaths(): string[] {
  return SITEMAP;
}

export const NOT_FOUND: string = import.meta.env.SSR ? /*NOT_FOUND*/ : "";
'''
NOT_IN_SITEMAP = re.compile(r"^/(?:category|tag|author|feed|wp-|cdn-cgi|search)/|/page/\d+/?$")


def sitemap_paths(pages_html, production_host):
    """{path: html} -> paths that belong in the sitemap."""
    out = []
    for p, h in sorted(pages_html.items()):
        if NOT_IN_SITEMAP.search(p) or "noindex" in (H.meta(h, "robots") or "").lower():
            continue
        c = H.canonical(h)
        if c and re.sub(r"^https?://(www\.)?", "", c).rstrip("/") != (production_host + p).rstrip("/"):
            continue
        out.append(p)
    return out


def write(repo, production_hosts, pages, sitemap, redirects, not_found_html, uploads=None):
    lib = os.path.join(repo, "src", "lib")
    os.makedirs(lib, exist_ok=True)
    ts = (TEMPLATE.replace("/*STAMP*/", datetime.date.today().isoformat())
          .replace("/*HOSTS*/", json.dumps(list(production_hosts)))
          .replace("/*PATHS*/", json.dumps(sorted(pages)))
          .replace("/*SITEMAP*/", json.dumps(list(sitemap)))
          .replace("/*REDIRECTS*/", json.dumps(redirects, sort_keys=True))
          .replace("/*NOT_FOUND*/", json.dumps(not_found_html, ensure_ascii=False)))
    open(os.path.join(lib, "site-pages.ts"), "w", encoding="utf-8").write(ts)
    open(os.path.join(lib, "site-uploads.ts"), "w", encoding="utf-8").write(
        "// Old media URLs and their Media Storage files (301 redirects). Server-only module.\n"
        "export const UPLOADS: Record<string, string> = %s;\n" % json.dumps(uploads or {}, sort_keys=True))

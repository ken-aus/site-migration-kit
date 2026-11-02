// Template src/server.ts for a migrated site whose pages are static files in public/ (<path>/index.html, or
// <path>.html). Copy over AI Studio's generated src/server.ts, keeping its first ~45 lines (getServerEntry and the
// h3 error handling) above this section, then fill in SITE below. Needs src/lib/site-pages.ts and
// src/lib/site-uploads.ts, written by ai-studio/site_pages.py.
//
// What it does that static files can't:
// - robots.txt: production rules on the real domain; Disallow everything on any other host (dev, AI Studio previews).
// - X-Robots-Tag: noindex on every response off the production domain.
// - sitemap.xml: generated from the page list (indexable, self-canonical pages), production domain only.
// - Form posts and AJAX pass through to the old site until go-live (WordPress admin-ajax.php, /wp-json/, any POST).
// - Old media URLs (e.g. /wp-content/uploads/...) 301 to their Media Storage files, for backlinks and image search.
// - Page redirects (merged duplicates, renamed URLs), the trailing-slash convention, and the site's own 404 page.
//
// Static pages in public/ are served by AI Studio's host BEFORE this code runs, with no Content-Type (so they are
// not compressed) and max-age=0. If HTML compression matters (it does), either serve pages from server code (small
// sites, with shared CSS moved to cached files) or put the dev/production hostname behind Cloudflare with a
// response header Transform Rule adding "Content-Type: text/html; charset=utf-8" to page paths (see NOTES.md).

import { hasPage, NOT_FOUND, pagePaths, PRODUCTION_HOSTS, REDIRECTS } from "./lib/site-pages";
import { UPLOADS } from "./lib/site-uploads";

const SITE = {
  // The old site, while it still handles forms. Set to "" once forms post to HighLevel.
  live: "https://example.com",
  // Production robots.txt rules (copy the old site's, minus anything that only applied to its admin area).
  robots: "User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n",
  // true: WordPress style /page/ URLs (no-slash 301s to slash); false: /page (slash 301s to no-slash).
  trailingSlash: true,
  // Paths passed through to the old site (any POST is passed through too).
  passThrough: [/^\/wp-admin\/admin-ajax\.php$/, /^\/wp-json\//],
  // Old media path prefix whose files moved to Media Storage (UPLOADS maps each to its new URL).
  uploadsPrefix: "/wp-content/uploads/",
};

const HTML_HEADERS = { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=0, must-revalidate" };
const isProduction = (url: URL) => PRODUCTION_HOSTS.has(url.hostname);

function robotsTxt(url: URL): string {
  if (!isProduction(url)) return "# " + url.hostname + " is a development copy and must not be indexed.\nUser-agent: *\nDisallow: /\n";
  return SITE.robots + "\nSitemap: " + url.origin + "/sitemap.xml\n";
}

function sitemapXml(origin: string): string {
  const urls = pagePaths().map((p) => "<url><loc>" + origin + p + "</loc></url>").join("");
  return '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + "</urlset>";
}

// Pass a request through to the old site and return its answer, with redirects pointed back at this host.
async function toLive(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const liveHost = new URL(SITE.live).hostname.replace(/^www\./, "");
  const headers = new Headers();
  for (const h of ["content-type", "accept", "accept-language", "user-agent", "x-requested-with"]) {
    const v = request.headers.get(h);
    if (v) headers.set(h, v);
  }
  headers.set("referer", SITE.live + url.pathname);
  headers.set("origin", SITE.live);
  const res = await fetch(SITE.live + url.pathname + url.search, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
    redirect: "manual",
  } as RequestInit);
  const out = new Headers();
  for (const h of ["content-type", "cache-control", "location"]) {
    const v = res.headers.get(h);
    if (v) out.set(h, h === "location" ? v.replace(new RegExp("^https?://(www\\.)?" + liveHost.replace(/\./g, "\\."), "i"), url.origin) : v);
  }
  return new Response(request.method === "HEAD" ? null : res.body, { status: res.status, headers: out });
}

async function siteResponse(request: Request, env: unknown): Promise<Response | null> {
  const url = new URL(request.url);
  const path = url.pathname;
  const head = request.method === "HEAD";
  if (SITE.live && (SITE.passThrough.some((r) => r.test(path)) || (request.method === "POST" && !/^\/(@|_|node_modules\/|src\/)/.test(path)))) {
    return toLive(request);
  }
  if (request.method !== "GET" && !head) return null;
  if (path === "/robots.txt") return new Response(head ? null : robotsTxt(url), { headers: { "content-type": "text/plain; charset=utf-8" } });
  if (path === "/sitemap.xml" || path === "/sitemap_index.xml" || path === "/wp-sitemap.xml") {
    if (!isProduction(url)) return new Response(null, { status: 404 });
    return new Response(head ? null : sitemapXml(url.origin), { headers: { "content-type": "application/xml; charset=utf-8" } });
  }
  if (SITE.uploadsPrefix && path.startsWith(SITE.uploadsPrefix)) {
    const file = UPLOADS[decodeURIComponent(path)];
    if (file) return new Response(null, { status: 301, headers: { location: file } });
  }
  // Framework and asset requests are left to AI Studio.
  if (/^\/(@|_|node_modules\/|src\/|assets\/)/.test(path) || /\.[a-z0-9]+$/i.test(path)) return null;
  const moved = REDIRECTS[path] ?? REDIRECTS[path.endsWith("/") ? path.slice(0, -1) : path + "/"];
  if (moved) return new Response(null, { status: 301, headers: { location: moved + url.search } });
  if (hasPage(path)) {
    // Normally served from public/ before this code runs. If the host passes it here, fetch the file.
    const assets = (env as { ASSETS?: { fetch: (r: Request) => Promise<Response> } } | undefined)?.ASSETS;
    if (!assets) return null;
    const file = path.endsWith("/") ? path + "index.html" : path + ".html";
    const res = await assets.fetch(new Request(url.origin + file, { method: request.method }));
    return new Response(res.body, { status: res.status, headers: HTML_HEADERS });
  }
  const other = SITE.trailingSlash ? path + "/" : path.replace(/\/+$/, "");
  if (path !== "/" && other !== path && hasPage(other)) {
    return new Response(null, { status: 301, headers: { location: other + url.search } });
  }
  return new Response(head ? null : NOT_FOUND, { status: 404, headers: HTML_HEADERS });
}

function withRobotsHeader(response: Response, request: Request): Response {
  if (isProduction(new URL(request.url))) return response;
  const out = new Response(response.body, response);
  out.headers.set("X-Robots-Tag", "noindex, nofollow");
  return out;
}

export default {
  async fetch(request: Request, env: unknown, ctx: unknown) {
    try {
      const site = await siteResponse(request, env);
      if (site) return withRobotsHeader(site, request);
      const handler = await getServerEntry(); // from AI Studio's generated preamble above
      const response = await handler.fetch(request, env, ctx);
      return withRobotsHeader(await normalizeCatastrophicSsrResponse(response), request);
    } catch (error) {
      console.error(error);
      return new Response(renderErrorPage(), { status: 500, headers: { "content-type": "text/html; charset=utf-8" } });
    }
  },
};

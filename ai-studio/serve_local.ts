// Local preview of an AI Studio (TanStack Start) build, served as AI Studio serves it: static files from
// dist/client first, then the server entry. Pretends to be the dev host so host-dependent code (noindex, tracking
// gates, link rewriting) behaves as on dev.
//   cd <repo> && bun run build && bun <kit>/ai-studio/serve_local.ts <repo dir> <port> <dev host>
// e.g. bun serve_local.ts /home/claude/site 4321 dev.example.com   (then http://localhost:4321)
// Static pages: <path>/index.html for slash URLs, <path>.html otherwise.
const root = process.argv[2] ?? ".";
const port = Number(process.argv[3] ?? 4321);
const devHost = process.argv[4] ?? "dev.example.com";
const mod = await import(root + "/dist/server/server.js?" + Date.now());
const handler = mod.default;
Bun.serve({ port, async fetch(req) {
  const u = new URL(req.url);
  if (req.method === "GET" || req.method === "HEAD") {
    const tries = u.pathname.endsWith("/") ? [u.pathname + "index.html"] : [u.pathname, u.pathname + ".html"];
    for (const t of tries) {
      const f = Bun.file(root + "/dist/client" + decodeURIComponent(t));
      if (await f.exists()) return new Response(req.method === "HEAD" ? null : f, { headers: { "cache-control": t.startsWith("/assets/") ? "public, max-age=31536000, immutable" : "public, max-age=0, must-revalidate" } });
    }
  }
  return handler.fetch(new Request("https://" + devHost + u.pathname + u.search, req), {}, {});
} });
console.log("listening on http://localhost:" + port + " as " + devHost);

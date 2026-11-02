# AI Studio platform notes

What we learned migrating several sites into HighLevel AI Studio (October-November 2026). Check these again if a
build behaves differently: the platform changes.

## Project and sync

- AI Studio projects are TanStack Start (React 19, Vite) apps, deployed to Cloudflare (nitro). Each project syncs
  with a GitHub repo. AI Studio picks the repo name when it connects; don't rename it afterwards (it can break sync).
- **Never force-push or rewrite pushed history.** AI Studio mirrors it and the project history is lost.
- Pushing to the connected branch syncs to AI Studio, but **does not publish**. Publish: open the project, click
  **Publish** (top right), then **Update** in the panel, and wait until it says **Up to date**. In the browser pane,
  a viewport of 1280x800 makes the buttons reliable; a click sometimes needs repeating.
- Keep the connected branch buildable. Work in progress goes on another branch (e.g. `clone-wip`) until it builds.
- AI Studio commits regenerated data files one at a time, so intermediate git revisions can be half-updated. Compare
  complete snapshots only.
- When the user edits in AI Studio and you edit in git, pull first. Agree with the user which wins on conflict.
- Project settings: domains at `.../vibe/projects/<id>/settings/domains` (shows the DNS record to add); git at
  `.../vibe/projects/<id>?view=more&more=github`.

## Build

- The build runs a strict TypeScript check. Run `bunx tsc --noEmit -p .` before every push.
- **Size limit:** builds fail with "start build: internal error" at about 76 MB of tracked files (one upload of 99 MB
  worked, a later one at 76.4 MB failed, so the limit isn't a fixed number). "Retry build" sometimes works. Levers, in
  order: move media to Media Storage, move repeated inline CSS/JS into shared files, drop HTML comments and whitespace,
  collapse srcset lists that point at one file, prune copied files nothing references.
- A server bundle can't hold hundreds of pages of ~480 KB each: large captured sites are static files in `public/`.
  Small sites (or pages slimmed by shared CSS files to ~30 KB each compressed) can be served from server
  code, which also gets them compressed.
- `.gitignore` patterns like `dist` match every folder of that name: WordPress's `wp-includes/js/dist` was silently
  dropped and broke Contact Form 7. Anchor build-output rules to the root (`/dist`).
- Keep Tailwind (`tailwindcss`, `@tailwindcss/vite`): AI Studio's build config loads it. The shadcn/ui kit, React
  Query and most template packages can go.

## Serving

- `public/` files are served before `src/server.ts` runs, with `cache-control: public, max-age=0, must-revalidate`
  and, for pages without an extension, **no Content-Type**, so they are not compressed. `_headers` files are served as
  files, not applied. The server code cannot read `public/` (no ASSETS binding, and fetching its own address fails).
- Responses from server code get gzip (not Brotli). HTTP/2 is on by default (GTmetrix: all own files HTTP/2).
- Long caching for shared CSS/JS: serve them from server code at a content-hashed address with
  `cache-control: public, max-age=31536000, immutable`, or bundle them through Vite
  (`?url` imports land in `/assets/` with immutable caching).
- AI Studio injects `__vibe/analytics.js` into pages.
- Server-rendered only is fine: dropping TanStack's `<Scripts />` from the root shell removes the React bundle and
  hydration data (~125 KB); strip the leftover `<link rel="modulepreload">` tags in server.ts.

## Cloudflare in front (when the client's DNS is on Cloudflare)

- Proxying the dev or production hostname (orange cloud to AI Studio's `vibe.ludicrous.cloud`) allows:
  - a response header **Transform Rule** adding `Content-Type: text/html; charset=utf-8` to page paths, so Cloudflare
    compresses them with Brotli (on one site the home page HTML went from 216 KB to 29 KB);
  - a Transform Rule adding `Cache-Control: public, max-age=86400` to theme/plugin asset paths.
- **Cache Rules do nothing** in this set-up (orange-to-orange, `cf-cache-status: BYPASS`).
- The extra hop adds about 0.2 s to server response time; repeat views get much faster. Measure both.
- These change the client's Cloudflare zone: get the user's approval first, and note how to undo each change.

## Measuring

- Never test HTTP versions, TLS or compression from Claude's workspace: its proxy answers with its own protocol
  (HTTP/1.1 "Connection Established") and strips Accept-Encoding. Use GTmetrix or WebPageTest.
- Send `Accept-Encoding: gzip, br` before reporting missing compression.
- WebPageTest from a test location near the site's audience, median of 3 runs, first view (plus repeat view for caching changes). Mobile is where the
  differences show.
- Lab LCP can be inflated by late-injected scripts that change nothing visible: check the filmstrip before chasing it.

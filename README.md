# site-migration-kit

Scripts and notes for migrating websites (WordPress, Wix, Squarespace, Webflow, HighLevel funnels and others) into
HighLevel AI Studio, with media in HighLevel Media Storage. Used with the `website-migration` skill (`SKILL.md`),
which has the step-by-step process; this repo has the tools it runs.

## Layout

| Path | What it is |
|---|---|
| `SKILL.md` | The website-migration skill: the process, phase by phase |
| `tools/capture.sh` | Polite wget capture of a site from its sitemap (pages, CSS, JS, fonts, images) |
| `tools/media_collect.py` | One file per picture/video/document at the largest size used, unique names, zips for upload, `media-map.json` |
| `tools/media_match.py` | After the user uploads the zips: match Media Storage files by name and size, write `media-urls.json` |
| `tools/media_audit.py` | Is every file the site uses in this sub-account's Media Storage? |
| `tools/origin_audit.py` | What does the new site still load from the old site (or anywhere else)? |
| `tools/link_check.py` | Crawl a site: broken pages and files, redirected links, links to the old host |
| `tools/seo_check.py` | Titles, descriptions, H1s, canonicals, robots, schema, alt text, per page and site-wide |
| `tools/browser/shots.js`, `shots_diff.py` | Full-page screenshots at 1440 and 390 px, and pixel comparison |
| `tools/browser/a11y_snapshot.js` | Accessibility snapshot for before/after comparison |
| `lib/html_tools.py` | HTML helpers: elements, titles, meta, JSON-LD, one H1 per page (with matching CSS), Cloudflare email decode |
| `lib/hl_images.py` | HighLevel image service: WebP, srcset and sizes for Media Storage photos |
| `lib/perf_tools.py` | Tracking off on dev, hero preload, fonts, lazy widgets/iframes, shared CSS/JS files, smaller HTML, a lighter pulse glow |
| `ai-studio/server-static.ts` | Template `src/server.ts` for static-file sites: robots, noindex, sitemap, form pass-through, redirects, 404 |
| `ai-studio/site_pages.py` | Writes `src/lib/site-pages.ts` and `site-uploads.ts` for that template |
| `ai-studio/serve_local.ts` | Serve a built project locally the way AI Studio does |
| `ai-studio/NOTES.md` | AI Studio platform behaviour and limits, Cloudflare options, measuring traps |

## Requirements

Python 3.10+ with Pillow (`pip install pillow`), Bun, Node with Playwright, wget and curl. Run Python tools with
`python3 -I` when they read captured files.

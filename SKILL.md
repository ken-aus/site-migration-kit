---
name: website-migration
description: Migrate a client website (WordPress, Wix, Squarespace, HighLevel or other) into HighLevel AI Studio, with media in Media Storage, builder clean-up, speed, SEO fixes and go-live checks.
---

# Website migration into HighLevel AI Studio

Use this for moving a client's existing website into a HighLevel AI Studio project, whether as a proof-of-concept
copy on a dev subdomain or as the real replacement. It captures what was learned migrating several WordPress and
HighLevel sites into AI Studio (October-November 2026).

The scripts live in the public GitHub repo **github.com/ken-aus/site-migration-kit**. Clone it beside the project
(attach it to the session first if the environment needs that). Read its `README.md` and `ai-studio/NOTES.md`
before starting: the notes hold the platform limits that cost the most time on past migrations.

Work through the phases in order and keep a task list. Follow the client's spelling conventions (e.g. Australian or
US English) in everything the client or user sees.

## Phase 0: questions before starting

Ask these with AskUserQuestion before any work (skip any the user has already answered):

1. **Sub-account** for the AI Studio project: the agency's own (for a proof of concept, moved later) or the
   client's.
2. **Scope**: every page (default), or key pages only.
3. **Purpose and address**: proof of concept on a dev subdomain (e.g. dev.<domain>), or the production rebuild.
   Is the subdomain's DNS record already there, and in whose Cloudflare account?
4. **Forms**: keep posting to the old site until go-live (default for a proof of concept), or rebuild as HighLevel
   forms now.
5. **Tracking**: off on dev (default). At go-live, which tags come back (aim for one Google tag and one Meta pixel).
6. **Content changes** wanted during the migration, or a faithful copy first.

Also ask, when they come up, for facts that can't be found on the site: practitioner registration numbers, founder
history, opening hours, business names. Never invent them; draft with a visible placeholder and list what's missing.

Record the answers and every standing decision in the project's `AGENTS.md`, so later sessions and AI Studio's own
agent follow them (for example: which side wins when AI Studio and GitHub differ; the dateModified rule).

## Phase 1: set up the project

- Create the AI Studio project in the chosen sub-account and connect GitHub (AI Studio picks the repo name; don't
  rename it). Clone it, `bun install`.
- Connect the domain under the project's settings, domains. Use the DNS record AI Studio shows; change nothing else
  in the client's DNS without asking.
- Keep the connected branch (main) buildable at every push. Work in progress that doesn't build yet goes on a
  separate branch (e.g. `clone-wip`).
- Fix `.gitignore` first: anchor build-output rules to the root (`/dist`, not `dist`), or folders such as
  `wp-includes/js/dist` are silently left out.

## Phase 2: capture the old site

- **Page list**: the sitemap(s), plus the pages they link to (pagination, archives), plus the 404 page.
  `tools/capture.sh <site> <out> [wait]` does this politely for sites that serve full HTML.
- **If the host starts refusing** (403/429/503, a Wordfence or Cloudflare block): stop crawling at once. Options to
  offer the user: an allowlist entry at the host, a temporary firewall allow rule (the client's security, so their
  call), a `wp-content` export, or saving the missing pages through the user's browser one at a time at a normal
  browsing pace (browser pane, saved to a connected folder). Then compare the captured count with the page list.
- **By platform**:
  - *WordPress*: wget capture works; theme and plugin files come with the pages. Watch for Cloudflare email
    protection (decode with `html_tools.undo_cf_email`) and lazy-load plugins that hide real image URLs in
    `data-src`/`data-srcset`.
  - *HighLevel sites and funnels*: the page HTML is server-rendered (Nuxt) and capturable; HighLevel's API (GHL
    connector: funnels, pages, blogs, blog posts) gives page lists and last-updated dates. Images are already in
    Media Storage: if the new project is in the same sub-account, reuse them rather than uploading again. Convert
    the live markup to stored page data once (strip Nuxt's `<!--[-->` markers, normalise empty attributes), and
    check the conversion reproduces every page before relying on it.
  - *Wix, Squarespace, Webflow and other script-rendered builders* (not yet done on a client site, so verify as you
    go): capture the rendered HTML with Playwright after scrolling the page (lazy content), not with wget; collect
    media from their CDNs (`static.wixstatic.com`, `images.squarespace-cdn.com`, `assets.website-files.com`) by
    passing those hosts to `media_collect.py`, which strips Wix's `/v1/fill/...` size transforms. Expect heavy
    builder scripts that the pages may not need once rendered: test each page with them removed.
- Keep the production domain in canonicals, `og:url`, share images and schema; rewrite everything else to work on
  the new host.
- Before calling the capture done, run `tools/origin_audit.py --hosts <old hosts> public src`: nothing should load
  from the old site except deliberate pass-throughs. (On one past migration the first version still took 90
  stylesheets, 33 scripts and nearly every image from the live site.)

## Phase 3: media into Media Storage

Every image, video, audio file, PDF and other document goes into the client's HighLevel Media Storage; the new site
loads nothing from the old host.

1. Run `tools/media_collect.py --site <captured root> --hosts <site host>,<its CDN hosts> --prefix <2-4 letters>
   --out <dir> [--fetch]`. It makes one file per picture at the largest size any page shows (all the platform's
   resized copies point at it), names each `<prefix>--<page>--<original name>.<ext>` (unique, so files match back by
   name), and writes zips by type plus `media-map.json` and `media-manifest.csv`. No WebP set: the HighLevel image
   service converts on the fly.
2. **Send the zips to the user (SendUserFile) and give them these instructions at that moment**, adapted to the
   site:
   > Please upload these to Media Storage in the **<sub-account>** sub-account:
   > 1. In HighLevel, open **Media Storage** and create a folder for this site (for example
   >    *Websites / <domain>*), with subfolders if you like (Images, Videos, Documents).
   > 2. Unzip each file on your computer.
   > 3. Open the folder in Media Storage, click **Upload**, and select all the files from the matching zip. Large
   >    batches upload more reliably in a few hundred files at a time.
   > 4. Keep the file names exactly as they are: I match the uploads back to the pages by name.
   > 5. Tell me when they're all in (and the folder name), and I'll check every file arrived.
3. When they confirm, list Media Storage through the GHL connector (`fetch-media-content`, params
   `{altType:"location", type:"file", sortBy:"updatedAt", sortOrder:"desc", fetchAll:"true", limit:"1000", offset}`;
   1000 per call, so page with offset; each result is large, so save it to a file) and run
   `tools/media_match.py <dir> <listing files>`. Report missing or wrong-size files to the user and ask them to upload
   those again.
4. Point the pages at the Media Storage URLs. Photos go through the image service with
   `lib/hl_images.rewrite_imgs` (WebP, srcset of widths up to 1920 px, never above the original's width, and an
   explicit `sizes` so layouts don't change). Animated GIFs and SVGs keep their original file. Meta tags and schema
   use the plain Media Storage URL.
5. Add 301 redirects from the old media URLs (e.g. `/wp-content/uploads/...`) to the new files, so backlinks and
   image search keep working (`ai-studio/site_pages.py`, `uploads=`).
6. Finish with `tools/media_audit.py`: every file in this sub-account's Media Storage. Flag files from other
   sub-accounts (they can be deleted without warning) and from other hosts.

## Phase 4: serve it from AI Studio

- **Small sites** (up to roughly a hundred pages once shared CSS is moved out): serve pages from server code (page
  data in modules the server renders). They get compressed, and shared files can be cached for a year at hashed
  addresses.
- **Large sites**: static files in `public/` with `ai-studio/server-static.ts` and `site_pages.py`. Those pages
  aren't compressed by AI Studio; see Phase 7.
- Either way the server code handles: robots.txt (production rules on the real domain, Disallow everything on any
  other host), `X-Robots-Tag: noindex` off production, a robots noindex meta tag on every dev page, the generated
  sitemap (production only), form and AJAX pass-through to the old site until go-live, page redirects, the trailing
  slash convention, and the site's own 404 page.
- **Dev copies**: strip the client's tracking (`perf_tools.strip_tracking`: Tag Manager, Analytics, Ads, Meta
  pixel, Jetpack stats and similar) and list what was removed for go-live. Links to the production domain should
  stay on the dev host so it can be browsed.
- Respect the size limit (about 76 MB tracked; see NOTES.md). Run `bunx tsc --noEmit -p .` before each push,
  then publish (Publish, then Update, until it says Up to date).

## Phase 5: clean-up of the old builder

Remove what the old platform left behind, checking each removal with screenshots (Phase 10):

- *WordPress*: page builders that load but build nothing (count the builder's data attributes on every page; a body
  class doesn't count as use), editor-only stylesheets (`wp-components`, `wp-preferences`, `wp-block-editor`),
  duplicate Font Awesome copies, jQuery UI parts no page uses, comment-reply on pages without comments, emoji
  scripts, plugin files for features the site doesn't use, duplicate font requests.
- *HighLevel*: the pulsing `box-shadow` button animation (redo it on a pseudo-element's opacity and scale), the
  accessibility body script (make its changes to the HTML on the server instead), the JSON-LD injector
  script (schema on the server instead), empty `data-animation-class` attributes, the animation library.
- *AI Studio template*: the shadcn/ui kit, React Query and unused packages (keep Tailwind).
- *Any platform*: copied files nothing references any more.
- Keep order-sensitive inline scripts where they are: moving Slider Revolution's small set-up script to a file broke
  a home page slider.

## Phase 6: speed

Use `lib/perf_tools.py`:

- **Fewer, cached files**: inline `<style>` and `<script>` blocks repeated on 3+ pages move to shared files with
  content-hashed names (`SharedBlocks`: styles from 300 bytes, scripts from 1,000 bytes); runs of local stylesheets
  or scripts on 10+ pages are combined.
- **Fonts**: self-host the families and weights actually used, one request, `font-display: swap`, preload the main
  text font; cut icon fonts down to the icons used (licence permitting).
- **No hydration bundle** on server-rendered pages (drop `<Scripts />`, strip modulepreload links).
- **Lazy loading**:
  - images below the first screen: `loading="lazy"` (done by `rewrite_imgs`);
  - booking calendars and form iframes: load when scrolled within 1500 px (`lazy_iframes`); HighLevel's
    `form_embed.js` loads with the first one; calendars in the first screen still load at once;
  - other iframes: `loading="lazy"`;
  - chat widgets, reCAPTCHA, Vimeo/YouTube players and similar: on the first scroll, tap, key press, mouse move or
    form focus (`lazy_on_interaction`); a script that waits for DOMContentLoaded needs a copy that starts at once;
  - analytics and HighLevel External Tracking: a couple of seconds after the load event.
- **Hero**: preload the first-screen image at high priority (`hero_preload`); phones get a smaller hero image and a
  480p hero video where there is one.
- Never leave an infinite animation on `box-shadow`, `filter` or layout properties.

## Phase 7: HTTP/2 and compressed HTML

- **HTTP/2** is on by default at AI Studio's host; nothing to configure. Confirm it with GTmetrix or WebPageTest
  (protocol column), never from Claude's workspace, whose proxy reports its own protocol.
- **Compressed HTML**: pages served from server code are gzipped. Static pages in `public/` are not (no
  Content-Type). For those, with the user's approval: proxy the hostname through Cloudflare and add a response header
  Transform Rule setting `Content-Type: text/html; charset=utf-8` on page paths (Brotli then applies), plus one adding
  `Cache-Control: public, max-age=86400` on theme and plugin asset paths. Cache Rules don't work in this set-up.
  Record each change and how to undo it.
- Confirm compression with GTmetrix or WebPageTest (or a request sending `Accept-Encoding: gzip, br` from outside
  Claude's workspace), not assumptions.

## Phase 8: broken links and common errors

Run `tools/link_check.py` on the new build (`--host-alias <production domain>` for a dev copy) and on the old site
for comparison, then ask the user about each class of problem (AskUserQuestion, grouped, with a recommended answer):

- **Pages missing from the capture**: capture them, or link to the old site for now?
- **Broken internal links**: for each, the correct target (suggest the closest existing page), or remove the link.
  Note which were already broken on the old site.
- **Duplicate pages** (e.g. `-2` slugs, near-identical copies): which one stays; the other 301s to it.
- **Two URL patterns for one thing** (e.g. `/timetables/` and `/timetable/`): which wins.
- **Links that redirect**: point them straight at the final URL (no question needed).
- **Images or files already broken on the old site**: replace, remove, or leave.
- **Empty pages** (header and footer only, also empty on the old site): keep, fill, or remove.
- **Forms**: where submissions should go at go-live.

Put every redirect in one list in server code, point internal links directly at final URLs, and keep the trailing
slash convention consistent.

## Phase 9: SEO fixes

Run `tools/seo_check.py` on the old site (baseline) and the new build. Fix the straightforward items without asking;
ask about anything that changes wording the client wrote:

- One H1 per page: keep the first non-empty one, demote the rest with `html_tools.one_h1` and add the CSS from
  `h1_css` so they look exactly as before; remove empty H1s.
- Titles: replace platform defaults ("... Archive", "Uncategorised"), fix missing spaces, add the city to local
  service pages, keep under 60 characters where possible. Meta descriptions: fill missing ones, de-duplicate.
- Canonicals present and self-referencing (production domain), robots correct, `lang` set, `og:image` present.
- **Schema, built on the server (never injected by script)**: Organization (or LocalBusiness / MedicalBusiness /
  the closest type, with address, phone, hours and geo for each location) and WebSite on every page; WebPage with
  dateModified; BreadcrumbList; BlogPosting with a Person author linked to an author page; Person on team pages
  (credentials and registration numbers only when confirmed); Service on service pages; FAQPage where the page shows
  FAQs; ItemList or CollectionPage on list pages. Validate the JSON.
- Visible bylines on blog posts, linked to the author's page.
- Sitemap generated from the pages: indexable, self-canonical pages only. Production robots.txt matches the old
  site's intent.
- **Dates**: one dates file feeding schema dateModified, sitemap lastmod and the Last-Modified header, with a
  fingerprint of each page's visible content stored beside its date, so a check can catch a missed date.
  Only visible content changes (text, images, title, meta description) move a page's date.
- Alt text: flag images with none; decorative images get `alt=""`.

## Phase 10: check everything

- Screenshots of every page at 1440 and 390 px before and after each batch of changes (`tools/browser/shots.js`,
  `shots_diff.py`), blocking the same third-party widgets in both runs. Anything other than intended changes is a
  regression.
- Visible text unchanged on every page unless a change was intended (compare `html_tools.text_of`).
- Accessibility snapshot before and after clean-up (`a11y_snapshot.js`); Lighthouse accessibility should not drop.
- Behaviour: menus, accordions, sliders, popups, forms (submit only with the user's OK, as it creates a real
  record), booking calendars, search, chat.
- WebPageTest from a test location near the site's audience (median of 3, first view; repeat view for caching),
  mobile and desktop, home page plus the heaviest page, against the old site. Report LCP, total blocking time, bytes and requests.
- `link_check.py`, `origin_audit.py`, `media_audit.py` and `seo_check.py` all clean, or every remaining item
  explained.
- Publish, and re-check the dev site itself (robots.txt Disallow, noindex header, tracking off).

## Ongoing: when the old site stays the editing source

If the client keeps editing the old site until switch-over (e.g. writing blog posts there), give the project a sync
tool rather than repeating the migration: a `check` mode that lists new and edited posts on the old site, and an
`apply` mode that converts them with the new site's formatting and rebuilds every list page (blog, categories, tags,
author), the search index and the dates. Before applying, have it confirm its list model reproduces the stored list
pages exactly. Keep edits made ahead of the old site in an overrides file so a rebuild doesn't wipe them.

## Go-live checklist

Present this to the user when the site is approved:

- Tracking restored on the production domain only (one Google tag, one Meta pixel, HighLevel External Tracking if
  wanted), firing after load.
- Forms post to HighLevel (or the chosen destination); pass-through to the old site removed; test one submission
  with the user's OK.
- Production robots.txt, no noindex on production pages, canonicals on the production domain, sitemap live.
- DNS switched to AI Studio (record shown in the project's domain settings); www and non-www both answer, one
  redirecting to the other.
- Old URLs and old media URLs redirect; spot-check the top pages from Search Console and the most-linked pages.
- Sitemap submitted in Search Console; watch coverage and 404s for two weeks.
- The old site kept reachable (e.g. old.<domain>) until nothing depends on it, then nothing on the new site loads
  from it (`origin_audit.py`).

## Reporting

Keep the user informed with short updates when a draft is live or a decision is needed. At the end, give: what was
migrated, before/after speed figures, what was fixed for SEO, open questions, and the go-live dependencies. Write a
summary doc to the project if the session is attached to one.

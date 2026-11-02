// Full-page screenshots of pages at desktop and phone widths, for before/after comparison (pair with shots_diff.py).
//   node shots.js --base http://localhost:4321 --out shots-new [--pages /,/about] [--pages-file paths.txt]
//        [--widths 1440,390] [--block "googletagmanager|chat-widget"] [--host dev.example.com]
// Lazy content is triggered by scrolling to the bottom first; animations are disabled and motion reduced.
// --block aborts requests matching a regex (chat widgets, tracking, booking iframes) so runs are comparable.
// Uses the pre-installed Playwright (require('playwright')); run from any folder.
const { chromium } = require('playwright');
const fs = require('fs');
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const base = arg('base'), out = arg('out', 'shots');
if (!base) { console.error('--base is required'); process.exit(2); }
let pages = (arg('pages', '/')).split(',');
if (arg('pages-file')) pages = fs.readFileSync(arg('pages-file'), 'utf8').split('\n').map(s => s.trim()).filter(Boolean);
const widths = arg('widths', '1440,390').split(',').map(Number);
const block = arg('block') ? new RegExp(arg('block')) : null;
fs.mkdirSync(out, { recursive: true });
(async () => {
  const b = await chromium.launch();
  for (const w of widths) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, reducedMotion: 'reduce', isMobile: w < 768, hasTouch: w < 768 });
    if (block) await ctx.route(block, r => r.abort());
    const pg = await ctx.newPage();
    for (const p of pages) {
      try {
        await pg.goto(base + p, { waitUntil: 'load', timeout: 90000 });
        await pg.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); } scrollTo(0, 0); await document.fonts.ready; });
        await pg.waitForTimeout(800);
        await pg.screenshot({ path: `${out}/${w}${p.replace(/[\/?=&]/g, '_') || '_'}.png`, fullPage: true, animations: 'disabled' });
      } catch (e) { console.log('FAILED', w, p, String(e).slice(0, 120)); }
    }
    await ctx.close();
  }
  await b.close();
  console.log('saved', pages.length * widths.length, 'screenshots to', out);
})();

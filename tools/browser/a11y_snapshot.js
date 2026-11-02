// Accessibility snapshot after scripts have run, for before/after comparison of a clean-up (diff the two JSON files).
//   node a11y_snapshot.js --base http://localhost:4321 --out a11y-new.json [--pages /,/about] [--pages-file paths.txt]
// Records per page: lang, landmarks, roles and labels, aria-current, images without alt / with empty alt / hidden,
// target=_blank links without noopener, FAQ/accordion button states, table header scopes, H1s, form fields without
// a label, and buttons/links without an accessible name.
const { chromium } = require('playwright');
const fs = require('fs');
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const base = arg('base'), out = arg('out', 'a11y.json');
let pages = arg('pages', '/').split(',');
if (arg('pages-file')) pages = fs.readFileSync(arg('pages-file'), 'utf8').split('\n').map(s => s.trim()).filter(Boolean);
(async () => {
  const b = await chromium.launch(); const res = {};
  const pg = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  for (const p of pages) {
    try { await pg.goto(base + p, { waitUntil: 'load', timeout: 90000 }); } catch (e) { res[p] = 'FAILED'; continue; }
    await pg.waitForTimeout(1500);
    res[p] = await pg.evaluate(() => {
      const d = document, A = (e, n) => e.getAttribute(n);
      const sel = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '');
      const name = e => (A(e, 'aria-label') || A(e, 'title') || e.textContent || '').trim() || [...e.querySelectorAll('img[alt]')].map(i => i.alt).join(' ').trim();
      return {
        lang: d.documentElement.lang,
        landmarks: [...d.querySelectorAll('main,nav,header,footer,aside,[role=main],[role=navigation],[role=banner],[role=contentinfo]')].map(sel),
        roles: [...d.querySelectorAll('[role]')].filter(e => !e.closest('svg')).map(e => sel(e) + '[' + A(e, 'role') + ']' + (A(e, 'aria-label') ? '{' + A(e, 'aria-label') + '}' : '')).slice(0, 60),
        current: [...d.querySelectorAll('[aria-current]')].map(e => A(e, 'href')),
        imgsNoAlt: [...d.images].filter(i => !i.hasAttribute('alt')).length,
        imgsEmptyAlt: [...d.images].filter(i => A(i, 'alt') === '').length,
        imgsHidden: [...d.images].filter(i => A(i, 'aria-hidden') === 'true').length,
        blankNoOpener: [...d.querySelectorAll('a[target=_blank]')].filter(a => !/noopener/.test(A(a, 'rel') || '')).length,
        unnamedLinks: [...d.querySelectorAll('a[href]')].filter(a => !name(a)).length,
        unnamedButtons: [...d.querySelectorAll('button,[role=button]')].filter(x => !name(x)).length,
        unlabelledFields: [...d.querySelectorAll('input:not([type=hidden]):not([type=submit]),select,textarea')].filter(f => !(f.labels && f.labels.length) && !A(f, 'aria-label') && !A(f, 'aria-labelledby') && !A(f, 'title')).length,
        expanded: [...d.querySelectorAll('[aria-expanded]')].map(e => A(e, 'aria-expanded')).join(''),
        thScope: [...d.querySelectorAll('th')].map(t => A(t, 'scope')).join(','),
        h1: [...d.querySelectorAll('h1')].map(h => h.textContent.trim().slice(0, 50)),
      };
    });
  }
  fs.writeFileSync(out, JSON.stringify(res, null, 1)); await b.close(); console.log('wrote', out);
})();

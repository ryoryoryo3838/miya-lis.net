import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

// Test the actual dune-built hero, not a JavaScript reimplementation.
const hero = await readFile(resolve(process.argv[2]), 'utf8');
const moduleName = process.env.PLAYWRIGHT_MODULE;
const {chromium} = await import(moduleName ? pathToFileURL(resolve(moduleName)).href : 'playwright-core');
const body = `<body class="hero-page">
  <a href="#unexpected" id="toggle-a" class="nav-toggle extra"><span id="nested">Menu</span></a>
  <nav><button id="toggle-b" class="extra nav-toggle">Menu</button></nav>
  <button id="lookalike" class="nav-toggle-extra">Not a toggle</button>
  <aside id="nav-panel"></aside><div id="nav-overlay"></div>
  <div id="persistent-header"></div>
  <div id="hero"><a class="hero-home" id="home-first">HOME</a><a class="hero-home" id="home-second">HOME 2</a>
    <div id="hero-period"></div><div id="hero-period-placeholder"></div></div>
</body>`;
const server = createServer((req, res) => {
  if (req.url === '/hero.js') {
    res.writeHead(200, {'Content-Type':'application/javascript'}); res.end(hero);
  } else {
    res.writeHead(200, {'Content-Type':'text/html'});
    // The normal script runs while parsing; late initialization is tested separately.
    res.end('<!doctype html><html><head>' + (req.url.startsWith('/late') ? '' : '<script src="/hero.js"></script>') + '</head>' + body + '</html>');
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
const cases = [];
try {
  browser = await chromium.launch({headless:true, executablePath:process.env.HYBRID_CHROMIUM, args:['--no-sandbox']});
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => route.request().url().startsWith('http://127.0.0.1:') ? route.continue() : route.abort());
  const origin = 'http://127.0.0.1:' + server.address().port;
  async function assertNav(open) {
    assert.deepEqual(await page.evaluate(() => ({
      panel:document.getElementById('nav-panel').classList.contains('is-open'),
      overlay:document.getElementById('nav-overlay').classList.contains('is-visible'),
      toggles:[...document.querySelectorAll('.nav-toggle')].map(el => el.classList.contains('is-open')),
      lookalike:document.getElementById('lookalike').classList.contains('is-open'),
      nested:document.getElementById('nested').classList.contains('is-open'),
    })), {panel:open, overlay:open, toggles:[open, open], lookalike:false, nested:false});
  }
  async function exerciseNav(label) {
    await assertNav(false);
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('.nav-toggle')].map(el => el.id)), ['toggle-a', 'toggle-b']);
    assert.deepEqual(await page.evaluate(() => ['toggle-a','toggle-b','nested','lookalike'].map(id => typeof document.getElementById(id).onclick)), ['function','function','object','object']);
    const url = page.url();
    await page.locator('#nested').click(); // bubbling from a nested child must work
    await assertNav(true);
    assert.equal(page.url(), url, 'toggle link default navigation must be prevented');
    await page.locator('#toggle-b').click();
    await assertNav(false);
    await page.locator('#toggle-b').click();
    await assertNav(true);
    await page.locator('#nav-overlay').dispatchEvent('click');
    await assertNav(false);
    await page.locator('#toggle-a').click();
    await page.evaluate(() => document.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', keyCode:13, bubbles:true}))); // non-Escape must not close the panel
    await assertNav(true);
    await page.keyboard.press('Escape');
    await assertNav(false);
    await page.locator('#lookalike').click();
    await assertNav(false);
    cases.push(label);
  }
  await page.goto(origin + '/early', {waitUntil:'load'});
  assert.equal(await page.locator('#hero').evaluate(el => el.style.display), 'none');
  assert.equal(await page.locator('body').evaluate(el => el.classList.contains('hero-page')), false);
  await exerciseNav('DOMContentLoaded: all toggles, nested click, default prevention, overlay, Escape, exact class');

  // Exercise the readyState=complete branch without a hero, as on content pages.
  await page.goto(origin + '/late', {waitUntil:'load'});
  await page.locator('#hero').evaluate(el => el.remove());
  await page.addScriptTag({url:origin + '/hero.js'});
  await exerciseNav('readyState complete, hero absent: same navigation behavior');

  await page.goto(origin + '/late-home#hero', {waitUntil:'load'});
  await page.evaluate(() => {
    window.__observed = [];
    window.__observerCallback = null;
    window.IntersectionObserver = class {
      constructor(callback) { window.__observerCallback = callback; }
      observe(el) { window.__observed.push(el.id); }
    };
    const period = document.getElementById('hero-period');
    const placeholder = document.getElementById('hero-period-placeholder');
    window.__periodTop = 0;
    period.getBoundingClientRect = () => ({top:window.__periodTop, height:100});
    placeholder.getBoundingClientRect = () => ({top:window.__periodTop, height:100});
  });
  await page.addScriptTag({url:origin + '/hero.js'});
  assert.equal(await page.locator('#hero').evaluate(el => el.style.display), '');
  assert.deepEqual(await page.evaluate(() => window.__observed), ['home-first']);
  await exerciseNav('#hero mode: navigation remains active');
  await page.evaluate(() => window.__observerCallback([{boundingClientRect:{bottom:-1}}], null));
  assert.equal(await page.locator('#persistent-header').evaluate(el => el.classList.contains('is-visible')), true);
  await page.evaluate(() => window.__observerCallback([{boundingClientRect:{bottom:1}}], null));
  assert.equal(await page.locator('#persistent-header').evaluate(el => el.classList.contains('is-visible')), false);
  async function scroll(top) {
    await page.evaluate(async top => {
      window.__periodTop = top;
      window.dispatchEvent(new Event('scroll'));
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    }, top);
  }
  await scroll(-80);
  assert.deepEqual(await page.locator('#hero-period').evaluate(el => [el.classList.contains('is-fixed'), el.style.position, el.style.zIndex]), [true,'fixed','11']);
  await scroll(0);
  assert.deepEqual(await page.locator('#hero-period').evaluate(el => [el.classList.contains('is-fixed'), el.style.position, el.style.zIndex]), [false,'','']);
  cases.push('hero-home first match, header observer, throttled scroll pin/unpin');

  await page.goto(origin + '/late-fallback#hero', {waitUntil:'load'});
  await page.locator('.hero-home').evaluateAll(elements => elements.forEach(el => el.remove()));
  await page.evaluate(() => {
    window.__observed = [];
    window.IntersectionObserver = class { observe(el) { window.__observed.push(el.id); } };
  });
  await page.addScriptTag({url:origin + '/hero.js'});
  assert.deepEqual(await page.evaluate(() => window.__observed), ['hero']);
  cases.push('hero-home absent: observer falls back to hero');
  assert.deepEqual(errors, [], 'no runtime errors from actual compiled hero');
  console.log(JSON.stringify({cases, pageErrors:errors}, null, 2));
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}

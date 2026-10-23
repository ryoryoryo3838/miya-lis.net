import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, readdir, lstat, mkdir, writeFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import {resolve, join, extname} from 'node:path';
import {parseArgs} from 'node:util';
import {pathToFileURL} from 'node:url';

// Canonical safe-web.py production output, served byte-for-byte.
// No added assets, fragments, classes, menu or HTML rewrites by this test.
const {values} = parseArgs({options: {
  'production-dir': {type:'string'}, client: {type:'string'},
  case: {type:'string', default:'all'}, 'evidence-dir': {type:'string'},
}});
assert(values['production-dir'] && values.client, 'Pass real --production-dir and --client artifacts');
assert(['all','lifecycle','menu','typography','home','native-core'].includes(values.case), 'Unknown case must not pass an empty suite');
const nativeDir = resolve(values['production-dir']);
const clientPath = resolve(values.client);
assert((await lstat(clientPath)).isFile(), 'Use the actual Dune-compiled regular JS artifact');
const client = await readFile(clientPath);
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const files = new Map();
async function inventory(dir, prefix) {
  for (const entry of await readdir(dir, {withFileTypes:true})) {
    const source = join(dir, entry.name), route = prefix + '/' + entry.name;
    assert(!entry.isSymbolicLink(), 'Fixtures/assets must be regular files, not links');
    if (entry.isDirectory()) await inventory(source, route);
    else if (entry.isFile()) files.set(route, await readFile(source));
  }
}
await inventory(nativeDir, '');
assert(files.has('/theme/client/hero.js'), 'Canonical production artifact lacks its owned client');
assert.equal(hash(files.get('/theme/client/hero.js')), hash(client), 'Browser executes the freshly source-built client, not a fixture copy');
const approvedRoots = ['PUBLICA', 'ISLAND', 'ISLAND2', 'PERSON', 'REFERENCE', 'TARGET'];
const requests = [], blocked = [], failures = [], errors = [], results = [];
const types = {'.html':'text/html; charset=utf-8','.css':'text/css','.js':'application/javascript','.woff2':'font/woff2','.woff':'font/woff','.ttf':'font/ttf','.json':'application/json','.svg':'image/svg+xml','.txt':'text/plain'};
const server = createServer((req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  requests.push(url.pathname);
  let bytes;
  if (url.pathname === '/' || url.pathname === '/index.html') bytes = files.get('/index.html');
  else {
    const id = url.pathname.match(/^\/([A-Za-z0-9-]+)\/?(?:index\.html)?$/)?.[1];
    if (id && files.has(`/${id}/index.html`)) bytes = files.get(`/${id}/index.html`);
    else bytes = files.get(url.pathname);
  }
  if (!bytes) { res.writeHead(404); res.end('fixture not found'); return; }
  res.writeHead(200, {'Content-Type':types[extname(url.pathname)] || (url.pathname.includes('/theme/') ? 'application/octet-stream' : 'text/html; charset=utf-8')});
  res.end(bytes);
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const origin = `http://127.0.0.1:${server.address().port}`;
const moduleName = process.env.PLAYWRIGHT_MODULE;
const {chromium} = await import(moduleName ? pathToFileURL(resolve(moduleName)).href : 'playwright-core');
let browser;
async function newPage(options = {}) {
  const page = await browser.newPage(options);
  page.setDefaultTimeout(5000);
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => { if (response.status() >= 400) failures.push({url:response.url(), status:response.status()}); });
  await page.route('**/*', route => {
    if (route.request().url().startsWith(origin + '/')) return route.continue();
    blocked.push(route.request().url()); return route.abort();
  });
  return page;
}
async function ready(page, path = '/') {
  await page.goto(origin + path, {waitUntil:'networkidle'});
  await page.evaluate(() => document.fonts.ready);
}
async function lifecycle() {
  const page = await newPage();
  await ready(page, '/CHILD');
  // Prime Playwright's main-world interceptors before observing SITE listeners.
  await page.addScriptTag({content:'/* test harness initialization, not a site client */'});
  await page.evaluate(() => {
    window.__listenerAdds = [];
    window.__article = document.querySelector('#grid-wrapper > article');
    const original = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function(type, ...args) {
      if (this === document || this === window || this.id?.startsWith('nav-')) window.__listenerAdds.push({type, target:this === document ? 'document' : this === window ? 'window' : this.id, stack:new Error().stack});
      return original.call(this, type, ...args);
    };
  });
  await page.addScriptTag({url:origin + '/theme/client/hero.js'});
  await page.addScriptTag({url:origin + '/theme/client/hero.js'});
  assert.deepEqual(await page.evaluate(() => window.__listenerAdds.filter(entry => ['keydown','scroll','DOMContentLoaded','click'].includes(entry.type))), [], 'duplicate initialization does not add handlers');
  assert.equal(await page.evaluate(() => document.querySelector('#grid-wrapper > article') === window.__article), true);
  await page.locator('#nav-toggle-global').click();
  assert.equal(await page.locator('#nav-panel').evaluate(el => el.classList.contains('is-open')), true, 'one click is one toggle');
  await page.close();
  results.push({case:'lifecycle', shell:'duplicate-client', nativeArticleIdentity:true});
}
async function dotInk(page, box) {
  const bytes = await page.screenshot({clip:{x:box.x,y:0,width:box.width,height:300}});
  return page.evaluate(async data => {
    const bitmap = await createImageBitmap(new Blob([new Uint8Array(data)], {type:'image/png'}));
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width; canvas.height = bitmap.height;
    const ctx = canvas.getContext('2d'); ctx.drawImage(bitmap,0,0);
    const pixels = ctx.getImageData(0,0,canvas.width,canvas.height).data;
    const rows = [];
    for (let y=0;y<canvas.height;y++) for (let x=0;x<canvas.width;x++) {
      const i=(y*canvas.width+x)*4;
      if (pixels[i]<100 && pixels[i+1]<100 && pixels[i+2]<100) rows.push(y);
    }
    return {pixels:rows.length,top:Math.min(...rows),bottom:Math.max(...rows)};
  }, [...bytes]);
}
async function menuBehavior() {
  for (const viewport of [{width:1440,height:900}, {width:390,height:844}]) {
    for (const colorScheme of ['light','dark']) {
      const page = await newPage({viewport, colorScheme});
      await ready(page, '/CHILD');
      const toggle = page.locator('#nav-toggle-global');
      const panel = page.locator('#nav-panel');
      const initialBox = await toggle.boundingBox();
      const ink = await dotInk(page, initialBox);
      assert(ink.pixels > 5 && ink.top >= initialBox.y && ink.bottom < initialBox.y + initialBox.height, 'painted dot ink must be inside the actual clickable hit target: ' + JSON.stringify({ink,initialBox}));
      const state = async open => {
        assert.equal(await panel.evaluate(el => el.hidden), !open, 'menu is actually shown/hidden');
        assert.equal(await panel.evaluate(el => el.inert), !open, 'closed menu cannot take focus');
        assert.equal(await toggle.getAttribute('aria-expanded'), String(open), 'accessible expanded state follows menu');
        assert.equal(await panel.evaluate(el => el.classList.contains('is-open')), open);
      };
      await state(false);
      await toggle.click();
      await state(true);
      assert.equal(await page.evaluate(() => document.activeElement.id), 'nav-close', 'keyboard focus enters owned navigation');
      await page.locator('#nav-close').click();
      await state(false);
      assert.equal(await page.evaluate(() => document.activeElement.id), 'nav-toggle-global');
      await toggle.focus();
      await page.keyboard.press('Enter');
      await state(true);
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('#nav-panel a')), true, 'Tab reaches the first renderer-authored public root link');
      await page.keyboard.press('Escape');
      await state(false);
      assert.equal(await page.evaluate(() => document.activeElement.id), 'nav-toggle-global');
      await page.keyboard.press('Space');
      await state(true);
      await page.mouse.click(viewport.width - 12, viewport.height - 12);
      await state(false);
      await toggle.click();
      await page.locator('#nav-panel a[href="/TARGET/"]').click();
      await page.waitForURL(origin + '/TARGET/');
      assert.equal(await page.locator('#hero').count(), 0, 'nonhome pages never gain a home shell');
      assert.equal(await page.locator('#nav-panel').evaluate(el => el.hidden), true);
      const box = await toggle.boundingBox();
      assert(box.width >= 44 && box.height >= 44, 'global dot menu has a usable 44px hit target');
      results.push({case:'menu', viewport, colorScheme, keyboard:['Enter','Tab','Escape','Space'],
        close:['button','overlay','Escape','link'], target:'/TARGET', hitTarget:box});
      await page.close();
    }
  }
}
async function typography() {
  for (const viewport of [{width:1440,height:900}, {width:390,height:844}]) {
    for (const colorScheme of ['light','dark']) {
      const page = await newPage({viewport,colorScheme});
      await ready(page, '/CHILD');
      const styles = await page.evaluate(() => {
        const family = selector => getComputedStyle(document.querySelector(selector)).fontFamily;
        return {heading:family('#grid-wrapper > article > section > header h1'),
          prose:family('#grid-wrapper > article > section > .mainmatter > p'),
          metadata:family('#grid-wrapper > article > section > header .metadata'),
          toc:family('#toc'), backmatter:family('#grid-wrapper > article > footer h1'),
          body:getComputedStyle(document.body).color,
          background:getComputedStyle(document.body).backgroundColor,
          overflow:document.documentElement.scrollWidth > innerWidth};
      });
      assert(styles.prose.includes('BIZ UDMincho'), 'native prose must use the existing self-hosted Mincho');
      for (const key of ['heading','metadata','toc','backmatter']) {
        assert(styles[key].startsWith('"Inria Sans"'), `${key} uses the Gothic heading/metadata stack`);
        assert(styles[key].includes('BIZ UDGothic'), `${key} has Japanese Gothic fallbacks`);
        assert(!styles[key].includes('UDMincho'), `${key} must not inherit the prose face`);
      }
      assert.equal(styles.background, 'rgb(255, 255, 255)', 'preserve the original light canvas even under dark preference');
      assert.equal(styles.overflow, false, 'native page cannot overflow the mobile/desktop viewport');
      const cdp = await page.context().newCDPSession(page);
      await cdp.send('DOM.enable');
      await cdp.send('CSS.enable');
      const doc = await cdp.send('DOM.getDocument');
      const actualFonts = {};
      for (const [kind, selector] of [['heading','#grid-wrapper > article > section > header h1'], ['prose','#grid-wrapper > article > section > .mainmatter > p']]) {
        const {nodeId} = await cdp.send('DOM.querySelector', {nodeId:doc.root.nodeId,selector});
        actualFonts[kind] = (await cdp.send('CSS.getPlatformFontsForNode', {nodeId})).fonts;
      }
      assert(actualFonts.heading.some(font => font.isCustomFont && font.familyName === 'Inria Sans' && font.glyphCount > 0), 'actual self-hosted Inria glyphs rendered, not only a CSS family string');
      assert(actualFonts.prose.some(font => font.isCustomFont && font.familyName === 'BIZ UDMincho' && font.glyphCount > 0), 'actual self-hosted BIZ Japanese/Latin glyphs rendered');
      if (values['evidence-dir']) {
        await mkdir(resolve(values['evidence-dir']), {recursive:true});
        await page.screenshot({path:join(resolve(values['evidence-dir']), `content-${viewport.width}-${colorScheme}.png`),fullPage:true});
      }
      await ready(page, '/CHILD');
      // Explicit runtime CSS-scoping control, NOT a fake server-side shell variant.
      await page.evaluate(() => document.body.classList.remove('miya-native'));
      assert.equal(await page.locator('#grid-wrapper > article p').first().evaluate(el => getComputedStyle(el).fontFamily), '"Inria Sans"', 'unowned native prose is unchanged by the scoped stylesheet');
      results.push({case:'typography', viewport, colorScheme, styles, actualFonts, unownedProseUnchanged:true, unownedStyleControl:'owned class removed in browser; served artifact bytes unchanged'});
      await page.close();
    }
  }
}
async function homeBehavior() {
  for (const viewport of [{width:1440,height:900}, {width:390,height:844}, {width:1920,height:700}, {width:320,height:568}, {width:844,height:390}]) {
    for (const colorScheme of ['light','dark']) {
    const page = await newPage({viewport, colorScheme, reducedMotion:'reduce'});
    await ready(page, '/');
    assert.equal(await page.locator('#hero').evaluate(el => getComputedStyle(el).display === 'none'), false, 'authorized root entry opens the real landing hero without a fragment');
    assert.equal(await page.locator('body').evaluate(el => el.classList.contains('hero-page')), true);
    const boxes = await page.evaluate(() => {
      const box = selector => { const r=document.querySelector(selector).getBoundingClientRect(); return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height}; };
      return {hero:box('#hero'),wordmark:box('.hero-title'),home:box('.hero-home'),header:box('#persistent-header'),
        overflow:document.documentElement.scrollWidth > innerWidth, headerVisible:getComputedStyle(document.getElementById('persistent-header')).visibility};
    });
    assert.equal(Math.round(boxes.hero.height), viewport.height, '100svh landing uses the actual small viewport');
    assert(boxes.wordmark.bottom <= boxes.home.top + 1, 'wordmark does not collide with HOME on short/wide windows');
    assert(boxes.home.bottom <= viewport.height && boxes.home.left >= 0, 'HOME remains reachable on a phone');
    assert.equal(boxes.overflow, false);
    assert.equal(boxes.headerVisible, 'hidden', 'persistent header starts hidden, not over the hero');
    assert.equal(await page.getByRole('button', {name:'Open navigation', exact:true}).count(), 1, 'hero period is accessible and the duplicate global dot is hidden');
    await page.locator('#hero-period').click();
    assert.equal(await page.locator('#nav-panel').evaluate(el => el.hidden), false);
    await page.keyboard.press('Escape');
    if (values['evidence-dir']) {
      await mkdir(resolve(values['evidence-dir']), {recursive:true});
      await page.screenshot({path:join(resolve(values['evidence-dir']), `home-${viewport.width}x${viewport.height}-${colorScheme}.png`)});
    }
    assert.equal(await page.locator('.hero-home').evaluate(home => {
      const rect=home.getBoundingClientRect();
      const hit=document.elementFromPoint(rect.x+rect.width/2,rect.y+rect.height/2);
      return home === hit || home.contains(hit);
    }), true, 'HOME is actually hit-testable above oversized wordmark text, not only geometrically separate');
    await page.locator('.hero-home').click();
    await page.waitForFunction(() => document.getElementById('persistent-header').classList.contains('is-visible') && document.getElementById('hero-period').classList.contains('is-fixed'));
    assert.equal(await page.locator('#nav-toggle-global').isVisible(), false);
    const clearance=await page.evaluate(() => ({headerBottom:document.getElementById('persistent-header').getBoundingClientRect().bottom,
      articleTop:document.querySelector('#grid-wrapper > article > section > header').getBoundingClientRect().top}));
    assert(clearance.articleTop >= clearance.headerBottom, 'HOME anchor must not hide the native article heading under the persistent header: ' + JSON.stringify(clearance));
    if (values['evidence-dir']) await page.screenshot({path:join(resolve(values['evidence-dir']), `home-content-${viewport.width}x${viewport.height}-${colorScheme}.png`)});
    const pinnedBox = await page.locator('#hero-period').boundingBox();
    assert(pinnedBox.x >= 0 && pinnedBox.y >= 0 && pinnedBox.width >= 44 && pinnedBox.height >= 44, 'pinned hero dot retains a reachable fixed hit target');
    const before = await page.locator('#grid-wrapper > article > section > .mainmatter').evaluate(el => el.classList.contains('collapsed'));
    await page.locator('.persistent-header-link').click();
    await page.waitForFunction(() => scrollY < 2 && !document.getElementById('hero-period').classList.contains('is-fixed') && !document.getElementById('persistent-header').classList.contains('is-visible'));
    assert.equal(await page.locator('#grid-wrapper > article > section > .mainmatter').evaluate(el => el.classList.contains('collapsed')), before, 'owned Top link cannot trigger native header-collapse delegation');
    await ready(page, '/PUBLICA');
    assert.equal(await page.locator('#hero').isVisible(), false, 'direct configured Home route stays on content');
    assert.equal(await page.locator('#nav-toggle-global').isVisible(), true);
    await ready(page, '/PUBLICA#hero');
    assert.equal(await page.locator('#hero').isVisible(), true, 'explicit #hero stays compatible on configured Home');
    await ready(page, '/index.html');
    assert.equal(await page.locator('#hero').isVisible(), true, 'authorized index.html entry preserves landing behavior');
    await ready(page, '/CHILD#hero');
    assert.equal(await page.locator('#hero').count(), 0, 'hash cannot manufacture a home shell on a nonhome page');
    results.push({case:'home', viewport, colorScheme, boxes, pinnedBox, entries:['/','/index.html','/PUBLICA#hero'], directHomeContent:true, nativeCollapseUnchanged:true});
    await page.close();
    }
  }
}
async function nativeCoexistence() {
  for (const viewport of [{width:1440,height:900},{width:390,height:844}]) {
    for (const colorScheme of ['light','dark']) {
      const page = await newPage({viewport,colorScheme});
      await ready(page, '/PUBLICA');
      const tocLabel=page.locator('#toc span[data-target]').filter({hasText:'Named child'}).first();
      const selector=await tocLabel.getAttribute('data-target');
      assert(selector.startsWith('#id-'), 'use the actual native stable placement ID');
      const target=page.locator(selector);
      const header=target.locator('..').locator(':scope > header');
      assert.equal(await target.evaluate(el => el.classList.contains('collapsed')), false);
      await header.locator(':scope > h1 > .taxon').click();
      assert.equal(await target.evaluate(el => el.classList.contains('collapsed')), true, 'native min.js still owns section collapse');
      await header.locator(':scope > h1 > .taxon').click();
      assert.equal(await target.evaluate(el => el.classList.contains('collapsed')), false);
      const counter=await target.locator('..').evaluate(el => getComputedStyle(el).counterIncrement);
      assert(counter.includes('section-num'), 'native CSS counters/numbered placement semantics survive');
      await tocLabel.click();
      assert.equal(new URL(page.url()).hash, selector, 'TOC label remains native page-local jump');
      await page.locator('#toc a.bullet[href="/CHILD"]').click();
      await page.waitForURL(origin + '/CHILD');
      await page.waitForFunction(() => document.querySelector('span.katex-math.katex-rendered .katex annotation'));
      const tex=await page.locator('span.katex-math.katex-rendered').first().getAttribute('data-tex');
      assert.equal(await page.locator('span.katex-math.katex-rendered annotation').first().textContent(), tex, 'native KaTeX renders serialized TeX exactly');
      assert.equal(tex, '\\alpha + \\beta');
      const mathFont=await page.locator('.katex .mathnormal').first().evaluate(el => getComputedStyle(el).fontFamily);
      assert(mathFont.includes('KaTeX_Math') && !mathFont.includes('UDMincho'), 'prose fonts do not replace KaTeX fonts');
      const reference=page.locator('article > footer section[data-taxon="Reference"]').first();
      assert.equal(await reference.locator(':scope > .mainmatter').evaluate(el => el.classList.contains('collapsed')), true);
      assert.equal(await reference.locator(':scope > header .metadata').isVisible(), true, 'native collapsed reference keeps metadata');
      await reference.locator(':scope > header > h1').click({position:{x:5,y:6}});
      assert.equal(await reference.locator(':scope > .mainmatter').evaluate(el => el.classList.contains('collapsed')), false, 'native backmatter is still expandable');
      await reference.locator(':scope > header > h1').click({position:{x:5,y:6}});
      assert.equal(await reference.locator(':scope > .mainmatter').evaluate(el => el.classList.contains('collapsed')), true);
      await page.locator('#nav-toggle-global').click();
      await page.keyboard.press('Control+k');
      await page.waitForFunction(() => !document.querySelector('.search-modal-overlay').classList.contains('hidden'));
      const input=page.locator('.search-modal-input');
      await input.fill('Public target');
      await page.waitForFunction(() => [...document.querySelectorAll('.search-modal-result-title')].some(el => el.textContent === 'Public target'));
      await page.keyboard.press('Enter');
      await page.waitForURL(origin + '/TARGET');
      assert.equal(await page.locator('#nav-panel').evaluate(el => el.hidden), true);
      await page.keyboard.press('Control+k');
      await page.waitForFunction(() => !document.querySelector('.search-modal-overlay').classList.contains('hidden'));
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('.search-modal-overlay').evaluate(el => el.classList.contains('hidden')), true, 'site client does not consume native search keyboard handling');
      results.push({case:'native-core',viewport,colorScheme,tocPlacement:selector,tocRoute:'/CHILD',nativeCounter:counter,
        nativeCollapse:true,backmatterMetadata:true,backmatterToggle:true,tex,mathFont,nativeSearchRoute:'/TARGET',nativeSearchKeys:['Control+k','Enter','Escape']});
      await page.close();
    }
  }
}
try {
  browser = await chromium.launch({headless:true, executablePath:process.env.HYBRID_CHROMIUM, args:['--no-sandbox','--disable-background-networking']});
  if (values.case === 'all' || values.case === 'lifecycle') await lifecycle();
  if (values.case === 'all' || values.case === 'menu') await menuBehavior();
  if (values.case === 'all' || values.case === 'typography') await typography();
  if (values.case === 'all' || values.case === 'home') await homeBehavior();
  if (values.case === 'all' || values.case === 'native-core') await nativeCoexistence();
  assert.deepEqual(errors, [], 'No page runtime errors');
  assert.deepEqual(failures, [], 'No missing local native/custom assets');
  assert.deepEqual(blocked, [], 'No attempted external requests');
  const evidence = {synthetic:true, adapter:'canonical safe-web.py output; no test HTML or asset injection',
    browser:await browser.version(), client_sha256:hash(client), native_min_js_sha256:hash(files.get('/min.js')),
    results, pageErrors:errors, missingAssets:failures, externalRequests:blocked,
    requestedAssets:[...new Set(requests.filter(path => /\.(js|css|woff2?|ttf|json)$/.test(path)))].sort()};
  if (values['evidence-dir']) {
    await mkdir(resolve(values['evidence-dir']), {recursive:true});
    await writeFile(join(resolve(values['evidence-dir']), `browser-${values.case}.json`), JSON.stringify(evidence, null, 2) + '\n');
  }
  console.log(JSON.stringify(evidence, null, 2));
} finally {
  if (browser) await browser.close();
  await new Promise(done => server.close(done));
}

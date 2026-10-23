import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, readdir, stat, writeFile} from 'node:fs/promises';
import {join, resolve, extname, sep} from 'node:path';
import {pathToFileURL} from 'node:url';

// Read-only browser acceptance against an already generated synthetic forest.
const [outputArg, forestArg, reportArg] = process.argv.slice(2);
assert.ok(outputArg && forestArg && reportArg, 'Usage: output forest.json report.json');
const output = resolve(outputArg);
const forest = JSON.parse(await readFile(forestArg, 'utf8'));
assert.equal(forest.schema, 'forester-public-v2');
const ids = new Set();
function collect(trees) {
  for (const tree of trees) {
    if (tree.id) ids.add(tree.id);
    collect(tree.content.filter(node => node.kind === 'subtree').map(node => node.tree));
  }
}
collect(forest.trees);
const mime = {'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.json':'application/json','.woff2':'font/woff2','.woff':'font/woff','.xml':'application/xml'};
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost');
    let path = resolve(output, '.' + decodeURIComponent(url.pathname));
    assert.ok(path === output || path.startsWith(output + sep));
    if ((await stat(path)).isDirectory()) path = join(path, 'index.html');
    const data = await readFile(path);
    res.writeHead(200, {'Content-Type':mime[extname(path)] || 'application/octet-stream'});
    res.end(data);
  } catch {
    res.writeHead(404); res.end('Not found');
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = 'http://127.0.0.1:' + server.address().port;
const moduleName = process.env.PLAYWRIGHT_MODULE;
const {chromium} = await import(moduleName ? pathToFileURL(resolve(moduleName)).href : 'playwright-core');
let executablePath = process.env.HYBRID_CHROMIUM;
if (!executablePath) {
  const cache = join(process.env.HOME, '.cache/ms-playwright');
  const names = (await readdir(cache)).filter(name => name.startsWith('chromium_headless_shell-')).sort();
  assert.ok(names.length, 'No installed Chromium');
  executablePath = join(cache, names.at(-1), 'chrome-headless-shell-linux64/chrome-headless-shell');
}
const browser = await chromium.launch({headless:true, executablePath, args:['--no-sandbox']});
try {
  const page = await browser.newPage();
  const errors = [], failedLocalRequests = [], routes = [], metadataLinks = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('requestfailed', req => {if (req.url().startsWith(origin)) failedLocalRequests.push(req.url());});
  for (const id of [...ids].sort()) {
    const response = await page.goto(origin + '/' + id + '/', {waitUntil:'networkidle'});
    assert.equal(response.status(), 200, id);
    const text = await page.locator('body').innerText();
    assert.ok(text.trim().length > 0, id);
    assert.ok(!/CANARY|sourcePath|\/home\/|\/nix\/store\//.test(text), 'Unapproved data in visible page');
    const title = await page.title();
    assert.ok(title.length > 0, id);
    routes.push({id, status:response.status(), title});
    const hrefs = await page.locator('a[href]').evaluateAll(elements => elements.map(element => element.href));
    if (id === 'PERSON') {
      assert.ok(hrefs.includes('https://orcid.org/0000-0000-0000-0000'), 'Native ORCID link must not acquire a second URL prefix');
      metadataLinks.push({id, property:'orcid', href:'https://orcid.org/0000-0000-0000-0000'});
    }
    if (id === 'REFERENCE') {
      assert.ok(hrefs.includes('https://www.doi.org/10.0000/synthetic'), 'Native DOI link must not acquire a second URL prefix');
      metadataLinks.push({id, property:'doi', href:'https://www.doi.org/10.0000/synthetic'});
    }
  }
  const root = forest.trees.find(tree => tree.id === 'PUBLICA');
  assert.ok(root);
  await page.goto(origin + '/PUBLICA/', {waitUntil:'networkidle'});
  const link = page.locator('a[href="/ISLAND"], a[href="/ISLAND/"]');
  assert.ok(await link.count() > 0, 'Public island link absent');
  await link.first().click();
  await page.waitForURL(url => url.origin === origin && url.pathname.replace(/\/$/, '') === '/ISLAND');
  const islandNavigation = page.url();
  const denied = await page.request.get(origin + '/NONPUBLIC-SENTINEL/');
  assert.equal(denied.status(), 404);
  assert.deepEqual(errors, []);
  assert.deepEqual(failedLocalRequests, []);
  const report = {routes, metadataLinks, publicIds:[...ids].sort(), islandNavigation, unapprovedRouteStatus:denied.status(), pageErrors:errors, failedLocalRequests};
  await writeFile(reportArg, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}

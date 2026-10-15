// Runs Lighthouse on a page OpenPPC already opened (lab/lighthouse.py), so the load goes through that page's proxy.
// Arguments: the Lighthouse folder, the browser's DevTools address (ws://127.0.0.1:port/devtools/browser/id), the
// page's marker URL, the URL to measure, mobile or desktop, devtools or simulate, and the categories, comma-separated.
// Writes the report (LHR) to stdout.
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const [dir, endpoint, marker, url, device, method, categories] = process.argv.slice(2);
const load = (path) => import(pathToFileURL(path).href).then((m) => m.default);
const lighthouse = await load(join(dir, 'core', 'index.js'));
const config = device === 'desktop' ? await load(join(dir, 'core', 'config', 'desktop-config.js')) : undefined;
const puppeteer = await load(createRequire(join(dir, 'package.json')).resolve('puppeteer-core'));

const browser = await puppeteer.connect({ browserWSEndpoint: endpoint, defaultViewport: null });
try {
  const target = await browser.waitForTarget((t) => t.url() === marker, { timeout: 10000 });
  const page = await target.page();
  const flags = { logLevel: 'error', output: 'json', onlyCategories: categories.split(','), throttlingMethod: method };
  const result = await lighthouse(url, flags, config, page);
  if (!result) throw new Error('Lighthouse returned no report');
  process.stdout.write(JSON.stringify(result.lhr));
} finally {
  await browser.disconnect();
}

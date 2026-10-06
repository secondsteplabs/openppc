/* OpenPPC web app. The Python engine (the same code as the CLI) runs inside this tab through
   Pyodide. Files are read into the browser's memory and never uploaded; the only network calls
   are the runtime and libraries, downloaded from the pinned CDN. */
'use strict';

const REPO = 'https://github.com/secondsteplabs/openppc';
const VIEWS = ['home', 'check', 'audit', 'templates', 'rules', 'branded'];
const PAGES = { home: 'Home', templates: 'Templates', rules: 'Rules', branded: 'Branded PDF' };
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const ICONS = {
  check: '<path d="M5 12.5l4.2 4.2L19 7"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  x: '<path d="M6 6l12 12"/><path d="M18 6L6 18"/>',
  alert: '<path d="M12 4l9 16H3z"/><path d="M12 10v4"/><path d="M12 17h.01"/>',
  up: '<path d="M12 19V5"/><path d="M6 11l6-6 6 6"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  download: '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/>',
  chart: '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>',
  print: '<path d="M7 9V3h10v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M7 14h10v7H7z"/>',
  code: '<path d="M8 8l-4 4 4 4"/><path d="M16 8l4 4-4 4"/>',
};

const state = {
  view: 'home', mode: 'check', engine: 'loading', meta: null, countRun: 0, files: [], queue: [], reading: [], busy: false,
  template: null, count: 0,
  saved: { check: null, audit: null },  // results stay put when you visit another page and come back
  lastAudit: null, autorun: false, wantIndustry: '',
};
const el = {};
// The sample's results, computed when this page was built by the same engine (tools/build_web.py), so "Try the
// sample" shows them at once while the engine downloads. Used only for the untouched sample, never for your files.
const SAMPLE = () => window.OPENPPC_BUNDLE.sample;
const SAMPLE_PATH = () => window.OPENPPC_BUNDLE.sample_path;
let sampleText = null;
let markReady;
const engineReady = new Promise((resolve, reject) => { markReady = { resolve, reject }; });
engineReady.catch(() => {});  // a page that never waits for the engine must not report its failure twice

/* ---------- tiny DOM helpers (text always goes in as text, never as HTML) ---------- */
function h(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'style') node.style.cssText = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) node.append(kid);
  return node;
}
function svg(tag, attrs) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}
function icon(name, size = 16, width = 2) {
  const node = svg('svg', { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
    'stroke-width': width, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' });
  node.innerHTML = ICONS[name];  // constant markup from ICONS, never user text
  return node;
}
const num = (n) => Number(n).toLocaleString('en-US');
const plural = (n, one, many) => `${num(n)} ${n === 1 ? one : many || one + 's'}`;
const capital = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
const an = (s) => (/^[aeiou]/i.test(s) ? 'an ' : 'a ') + s;
const secs = (ms) => `${Math.max(ms / 1000, 0.1).toFixed(1)} s`;
function debounce(fn, wait) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), wait); }; }
// The engine blocks the page while it works, so long calls wait for the browser to paint a "working" state first.
const nextPaint = () => new Promise((done) => requestAnimationFrame(() => setTimeout(done, 0)));
function b64bytes(b64) { const bin = atob(b64); const out = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i); return out; }
function toast(message) {
  const node = h('div', { class: 'toast', role: 'status' }, message);
  document.body.append(node);
  setTimeout(() => node.remove(), 2800);
}
function download(name, text, type = 'text/markdown') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = h('a', { href: url, download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
async function copyText(text, done, fallback = 'Copy did not work here. Download the .md instead.') {
  try { await navigator.clipboard.writeText(text); toast(done); }
  catch { toast(fallback); }
}
function formatPeriod(start, end) {
  if (!start || !end) return '';
  const [y1, m1, d1] = start.split('-').map(Number);
  const [y2, m2, d2] = end.split('-').map(Number);
  if (y1 === y2 && m1 === m2) return `${MONTHS[m1 - 1]} ${d1} to ${d2}, ${y1}`;
  if (y1 === y2) return `${MONTHS[m1 - 1]} ${d1} to ${MONTHS[m2 - 1]} ${d2}, ${y1}`;
  return `${MONTHS[m1 - 1]} ${d1}, ${y1} to ${MONTHS[m2 - 1]} ${d2}, ${y2}`;
}
function describe(info) {
  const parts = [info.kind];
  if (info.rows !== null && info.rows !== undefined) parts.push(plural(info.rows, 'row'));
  const period = formatPeriod(info.start, info.end);
  if (period) parts.push(period);
  if (info.currency) parts.push(info.currency);
  return parts.join(' · ');
}
function industryName(key) {
  const found = state.meta && state.meta.industries.find((i) => i.key === key);
  return found ? found.name : '';
}

/* ---------- engine: runs in engine-worker.js, so a big export never freezes the page ---------- */
const engine = { worker: null, calls: new Map(), next: 1 };
class Stopped extends Error { constructor() { super('stopped'); } }
function engineStart() {
  const worker = new Worker('engine-worker.js', { type: 'module' });
  engine.worker = worker;
  return new Promise((resolve, reject) => {
    worker.onmessage = (e) => {
      const m = e.data;
      if (m.type === 'status') status(m.text, 'loading');
      else if (m.type === 'ready') resolve(m.meta);
      else if (m.type === 'failed') reject(new Error(m.error));
      else {
        const call = engine.calls.get(m.id);
        if (!call) return;
        engine.calls.delete(m.id);
        if (m.ok) call.resolve(m.result); else call.reject(new Error(m.error));
      }
    };
    worker.onerror = (e) => {
      e.preventDefault();
      const error = new Error(e.message || 'the checker stopped');
      reject(error);
      for (const call of engine.calls.values()) call.reject(error);
      engine.calls.clear();
    };
  });
}
function engineStop() {  // Python can't be interrupted mid-call: end the worker, and every waiting call
  if (engine.worker) engine.worker.terminate();
  engine.worker = null;
  for (const call of engine.calls.values()) call.reject(new Stopped());
  engine.calls.clear();
}
function enginePost(message) {
  return new Promise((resolve, reject) => {
    if (!engine.worker) { reject(new Error('the checker has not started')); return; }
    const id = engine.next++;
    engine.calls.set(id, { resolve, reject });
    engine.worker.postMessage({ ...message, id });
  });
}
const engineCall = (fn, ...args) => enginePost({ op: 'call', fn, args });
const engineWrite = (path, bytes) => enginePost({ op: 'write', path, bytes });
async function startEngine() {  // the first start, and again after Stop
  state.engine = 'loading';
  const meta = await engineStart();
  for (const f of state.files) await engineWrite(f.path, f.bytes);  // a new worker starts with no files
  state.engine = 'ready';
  return meta;
}

function status(text, kind, retry = kind === 'error') {
  el.status.className = 'status' + (kind === 'loading' ? '' : ' ' + kind);
  el.status.replaceChildren(...[kind === 'loading' ? h('span', { class: 'bar' }) : null, text,
    retry ? h('button', { class: 'link-btn', type: 'button', style: 'margin-left:6px', onclick: () => location.reload() }, 'Try again') : null]
    .filter(Boolean));
}

async function boot() {
  if (typeof WebAssembly !== 'object') {  // turned off by iPhone Lockdown Mode and some strict security settings
    state.engine = 'error';
    status(h('span', {}, "This browser has WebAssembly turned off, so the checker can't run here. iPhone Lockdown Mode "
      + "and some strict security settings do this. On an iPhone, you can turn Lockdown Mode off for this site in "
      + "Safari's page settings. Or use another browser, or ", h('a', { href: '../docs/install/' }, 'run OpenPPC on your computer'),
    '.'), 'error', false);  // trying again cannot help
    renderFiles();
    return;
  }
  state.meta = SAMPLE().meta;  // the pickers and the sample work before the engine has loaded
  fillIndustries();
  status('Downloading the checker, about 6 MB. The sample opens right away; your own files need the checker.', 'loading');
  try {
    state.meta = await startEngine();
    fillIndustries();
    for (const f of state.files) if (f.sample) await engineWrite(f.path, f.bytes);  // added while it was starting
    if (state.wantIndustry && !el.industry.value) el.industry.value = state.wantIndustry;
    status('Ready. Everything runs on this device.', 'ok');
    markReady.resolve();
    const queued = state.queue.splice(0);
    for (const q of queued) addBytes(q.name, q.bytes);
    if (queued.length === 0) renderFiles();
    updateCount();
  } catch (e) {
    state.engine = 'error';
    console.error(e);
    status(`The checker could not start: ${e.message}`, 'error');
    markReady.reject(e);
  }
}
function fillIndustries() {
  const have = new Set([...el.industry.options].map((o) => o.value));
  for (const i of state.meta.industries) if (!have.has(i.key)) el.industry.append(h('option', { value: i.key }, i.name));
}

/* ---------- files ---------- */
async function addFile(file) {
  addBytes(file.name, new Uint8Array(await file.arrayBuffer()));
}
async function addBytes(name, bytes, sample = false) {
  if (sample && state.engine !== 'ready') {  // shown at once; the engine gets the file when it starts
    const path = SAMPLE_PATH();
    state.files = state.files.filter((f) => f.path !== path).concat([{ name, path, info: SAMPLE().info, bytes, sample: true }]);
    if (state.mode === 'audit') autoTemplate();
    syncThreshold();
    renderFiles();
    refresh();
    return;
  }
  if (state.engine !== 'ready') {
    state.queue.push({ name, bytes });
    renderFiles();
    return;
  }
  const path = '/uploads/' + (name.replace(/[^\w.\- ]+/g, '_').slice(0, 120) || 'export.csv');
  state.reading.push(name);
  renderFiles();
  await nextPaint();  // a big export takes a second or two to read
  try {
    await engineWrite(path, bytes);
    const info = JSON.parse(await engineCall('inspect_file', path));
    state.files = state.files.filter((f) => f.path !== path).concat([{ name, path, info, bytes, sample }]);
  } catch (e) {
    if (!(e instanceof Stopped)) throw e;
  } finally {
    state.reading.splice(state.reading.indexOf(name), 1);
  }
  if (state.mode === 'audit') autoTemplate();
  syncThreshold();
  renderFiles();
  refresh();
  updateCount();  // the export's row names change which numbers the check judges
}
function removeFile(path) {
  state.files = state.files.filter((f) => f.path !== path);
  syncThreshold();
  renderFiles();
  refresh();
  updateCount();
}
// The waste threshold is in the export's currency and starts at that currency's default (about $20),
// until the user types their own.
function syncThreshold() {
  const f = auditFile();
  const info = f && f.info && f.info.ok ? f.info : null;
  el.minCostSign.textContent = info ? (info.currency_sign || `${info.currency || 'USD'} `) : '$';
  if (info && info.min_cost != null && !el.minCost.dataset.edited) el.minCost.value = String(info.min_cost);
}
function goodFiles() { return state.files.filter((f) => f.info.ok); }
function auditFile() {
  const good = goodFiles();
  return [...good].reverse().find((f) => f.info.templates.length) || good[good.length - 1] || null;
}
function fileRow(f) {
  const info = f.info;
  const bad = info && !info.ok;
  const meta = info ? (bad ? "Can't read this one yet" : describe(info))
    : f.reading ? 'Reading the file…' : state.engine === 'error' ? "The checker can't run in this browser" : 'Waiting for the checker to load';
  const row = h('div', { class: 'file' + (bad ? ' bad' : '') },
    h('span', { class: 'file-icon' }, icon(bad ? 'alert' : 'file', 18)),
    h('span', { class: 'file-main' }, h('span', { class: 'file-name' }, f.name), h('span', { class: 'file-meta' }, meta)),
    info ? h('button', { class: 'icon-btn', type: 'button', 'aria-label': `Remove ${f.name}`, onclick: () => removeFile(f.path) }, icon('x')) : null);
  if (!bad) return row;
  return h('div', { class: 'stack', style: 'gap:10px' }, row,
    h('p', { class: 'file-note' }, capital(info.error)),
    h('div', { class: 'guide' }, h('b', {}, 'Export a Search terms report instead'), info.hint));
}
function renderFiles() {
  el.files.replaceChildren(...state.queue.map((q) => fileRow({ name: q.name, info: null })), ...state.files.map(fileRow),
    ...state.reading.map((name) => fileRow({ name, info: null, reading: true })));
  el.drop.querySelector('.drop-t').textContent = state.files.length || state.queue.length || state.reading.length
    ? 'Add another export' : 'Add a Google Ads export';
}
function loadSample() {
  const samples = window.OPENPPC_BUNDLE.samples;
  if (state.mode === 'check') {
    el.text.value = new TextDecoder().decode(b64bytes(samples['ai_audit_sample.md']));
  }
  if (!el.industry.value) el.industry.value = 'home-services';  // the industries are listed before the engine loads
  addBytes('search_terms_acme.csv', b64bytes(samples['search_terms_acme.csv']), true);
  updateCount();
}
// The sample's result computed in advance, when what is on the page is exactly the untouched sample; else null.
function sampleResult() {
  const files = goodFiles();
  if (files.length !== 1 || !files[0].sample || el.industry.value !== 'home-services') return null;
  if (state.mode === 'check') {
    sampleText ??= new TextDecoder().decode(b64bytes(window.OPENPPC_BUNDLE.samples['ai_audit_sample.md']));
    return el.text.value === sampleText ? SAMPLE().check : null;
  }
  const brand = el.brandWrap.hidden ? '' : el.brand.value.trim();
  const fits = state.template === 'search-term-waste' && !brand && parseFloat(el.minCost.value) === SAMPLE().info.min_cost;
  return fits ? SAMPLE().audit : null;
}

/* ---------- compose ---------- */
async function updateCount() {
  const text = el.text.value;
  const run = ++state.countRun;
  let count = 0;
  if (state.engine === 'ready' && text.trim()) {
    const paths = JSON.stringify(goodFiles().map((f) => f.path));  // the export's row names change the count
    try { count = Number(await engineCall('count_numbers', text, paths)); } catch { count = 0; }
    if (run !== state.countRun) return;  // a later edit is being counted
  } else if (text.trim() && sampleResult()) {
    count = SAMPLE().count;
  }
  state.count = count;
  state.counting = false;
  el.count.textContent = !text.trim() ? ''
    : state.engine !== 'ready' && !count ? 'The numbers get counted once the checker loads.'
      : state.count ? `${plural(state.count, 'number')} found in this text` : 'No numbers found in this text yet.';
  refresh();
}
function autoTemplate() {
  const f = auditFile();
  const fits = f ? f.info.templates : [];
  if (!fits.includes(state.template)) state.template = fits[0] || state.template;
}
function renderTemplates() {
  if (!state.meta) return;
  const f = auditFile();
  const fits = f ? f.info.templates : [];
  el.templates.replaceChildren(...state.meta.templates.map((t) => {
    const fit = fits.includes(t.name);
    return h('button', {
      type: 'button', role: 'radio', class: 'tpl', 'aria-checked': String(state.template === t.name),
      disabled: f ? !fit : false, onclick: () => { state.template = t.name; refresh(); },
    }, h('span', { class: 'tpl-t' }, t.title), h('span', { class: 'tpl-s' }, t.summary),
    h('span', { class: 'tpl-f' + (fit ? ' fit' : '') }, fit ? 'Matches your file' : `Needs ${an(t.input)}`));
  }));
}
function refresh() {
  const ready = state.engine === 'ready';
  let enabled;
  let label;
  if (state.mode === 'check') {
    enabled = (ready || !!sampleResult()) && goodFiles().length > 0 && state.count > 0;
    label = state.count && !state.counting ? `Check ${plural(state.count, 'number')}` : 'Check numbers';
  } else {
    el.threshold.hidden = !['search-term-waste', 'keyword-audit'].includes(state.template);
    el.brandWrap.hidden = el.threshold.hidden;
    const f = auditFile();
    enabled = (ready || !!sampleResult()) && !!f && !!state.template && f.info.templates.includes(state.template);
    label = 'Run audit';
    renderTemplates();
  }
  if (!state.busy) {  // while a run is going, the button keeps its "Checking…" label
    el.run.disabled = !enabled;
    el.run.replaceChildren(label, icon('up', 16, 2.4));
  }
  if (state.autorun && enabled && state.mode === 'audit' && state.view === 'audit') {
    state.autorun = false;
    setTimeout(run, 0);
  }
}
function setMode(mode) {
  state.mode = mode;
  const check = mode === 'check';
  el.crumbMode.textContent = check ? 'Check an AI audit' : 'Audit my account';
  el.title.textContent = check ? "Paste an AI audit. We'll check every number." : 'Run a free audit on your export.';
  el.sub.textContent = check
    ? 'Add the Google Ads export it was written from. Each figure comes back marked traced, wrong number or wrong label.'
    : 'Code computes every figure in the report from your file, then traces each one back to it before you see it.';
  el.auditField.hidden = !check;
  el.templateField.hidden = check;
  el.threshold.hidden = true;
  el.brandWrap.hidden = true;
  if (!check) autoTemplate();
  const saved = state.saved[mode];
  if (saved) showResults(saved.nodes, saved.page); else showCompose();
  refresh();
}
function showCompose() {
  state.saved[state.mode] = null;
  el.compose.hidden = false;
  el.results.hidden = true;
  el.crumbPage.textContent = state.mode === 'check' ? 'New check' : 'New audit';
  el.newBtn.hidden = true;
}
function showResults(nodes, page) {
  state.saved[state.mode] = { nodes, page };
  el.results.replaceChildren(...nodes);
  el.compose.hidden = true;
  el.results.hidden = false;
  el.crumbPage.textContent = page;
  el.newBtn.hidden = false;
  el.newBtn.textContent = state.mode === 'check' ? 'New check' : 'New audit';
  window.scrollTo({ top: 0 });
}
async function run() {
  if (state.busy) return;
  state.busy = true;
  const f = state.mode === 'audit' ? auditFile() : null;
  const rows = f && /report$/i.test(f.info.kind || '') ? f.info.rows : 0;
  el.run.disabled = true;
  el.run.replaceChildren(state.mode === 'check' ? `Checking ${plural(state.count, 'number')}…`
    : rows ? `Auditing ${plural(rows, 'row')}…` : 'Running the audit…');
  el.stop.hidden = false;
  await nextPaint();
  try {
    if (state.mode === 'check') await runCheck(); else await runAudit();
  } catch (e) {
    if (e instanceof Stopped) toast('Stopped.');
    else { console.error(e); toast(`Something went wrong: ${e.message}`); }
  } finally {
    el.stop.hidden = true;
    state.busy = false;
    refresh();
  }
}
function stopRun() {
  engineStop();
  status('Restarting the checker…', 'loading');
  startEngine()
    .then(() => status('Ready. Everything runs on this device.', 'ok'))
    .catch((e) => { state.engine = 'error'; console.error(e); status(`The checker could not start: ${e.message}`, 'error'); })
    .finally(refresh);
}

/* ---------- check results ---------- */
async function runCheck() {
  const text = el.text.value;
  const files = goodFiles();
  const industry = el.industry.value;
  const pre = sampleResult();
  const t0 = performance.now();
  const res = pre ? structuredClone(pre) : JSON.parse(await engineCall('check', text, JSON.stringify(files.map((f) => f.path)), industry));
  const ms = performance.now() - t0;
  if (!res.ok) { toast(capital(res.error)); return; }
  const title = firstTitle(text);
  const left = h('div', { class: 'col' },
    bubble(files, industry, title, `Pasted audit · ${plural(res.counts.total, 'number')} found`),
    h('div', { class: 'col', style: 'gap:10px' }, who(pre ? 'Number check · the sample, checked in advance' : `Number check · ${secs(ms)} · on this device`), message(res)),
    annotated(text, res),
    numbersTable(res.claims),
    h('div', { class: 'chips' }, h('button', { class: 'btn', type: 'button', onclick: showCompose }, 'Edit the audit and check again')));
  const right = h('aside', { class: 'side' }, scoreCard(res.counts), sourcesCard(files, industry), trustCard());
  showResults([left, right], title || 'Number check');
}
function firstTitle(text) {
  const line = text.split(/\r?\n/).find((l) => l.trim());
  return line ? line.replace(/^\s*#{1,6}\s*/, '').replace(/\*\*/g, '').trim().slice(0, 90) : '';
}
function bubble(files, industry, title, note) {
  return h('div', { class: 'bubble' },
    h('div', { class: 'tags' }, files.map((f) => h('span', { class: 'tag mono' }, f.name)), industry ? h('span', { class: 'tag' }, industryName(industry)) : null),
    title ? h('span', { class: 'bubble-t' }, title) : null,
    h('span', { class: 'hint', style: 'color:var(--muted)' }, note));
}
function who(text) {
  const mark = h('span', { class: 'who-mark' });
  const tick = icon('check', 15, 3);
  tick.setAttribute('stroke', '#ffffff');
  mark.append(tick);
  return h('div', { class: 'who' }, mark, h('b', {}, 'OpenPPC'), h('span', {}, text));
}
function problems(res) {
  const rows = res.claims.filter((c) => FLAGGED.has(c.verdict)).map((c) => ({ line: c.line, kind: c.verdict, claim: c }));  // can't check is not a problem
  for (const k of res.contradictions) rows.push({ line: k.line, kind: 'contradiction', con: k });
  return rows.sort((a, b) => a.line - b.line || (a.kind === 'contradiction' ? -1 : 1));
}
const cleanQuote = (s) => s.replace(/^\s*(?:[-*>]\s*)?\d+[.)]\s+/, '').replace(/\*\*/g, '');
function message(res) {
  const c = res.counts;
  const bad = c.mismatch + c.not_in_data;
  const lead = h('p', { class: 'lead' });
  if (!c.total) {
    lead.append('There are no numbers to check in this text.');
  } else if (!bad && !c.contradictions) {
    const sure = c.total - (c.cant_check || 0);
    lead.append(h('b', {}, sure === c.total ? `All ${plural(c.total, 'number')}` : `All ${plural(sure, 'number')} an export can confirm`),
      ' trace to your export. No contradictions.');
  } else {
    if (bad) lead.append(h('b', {}, `${bad} of ${plural(c.total, 'number')}`), ` in this audit ${bad === 1 ? "doesn't" : "don't"} hold up against your export`);
    else lead.append(h('b', {}, `All ${plural(c.total, 'number')}`), ' trace to your export');
    if (c.contradictions) lead.append(bad ? ', and ' : ', but ', c.contradictions === 1 ? 'one sentence contradicts itself' : `${c.contradictions} sentences contradict themselves`);
    lead.append('.');
    const misses = res.claims.filter((x) => x.verdict === 'not in data');
    const money = misses.filter((x) => /^[$€£₹]/.test(x.written));
    const pool = money.length ? money : misses;
    if (pool.length) {
      const miss = pool.reduce((a, b) => (b.value > a.value ? b : a));
      lead.append(' The biggest miss: ', h('b', {}, miss.written), ` on line ${miss.line} is wrong.`);
    }
  }
  if (c.cant_check) lead.append(` ${c.cant_check} more can't be checked from an export: targets, forecasts, or the audit's own working.`);
  const card = h('div', { class: 'card msg' }, lead);
  const rows = problems(res);
  if (rows.length) {
    const list = h('ol', { class: 'items' });
    rows.forEach((r, i) => {
      let title; let detail; let quote; let pill;
      if (r.kind === 'contradiction') {
        title = `Line ${r.line} contradicts itself`;
        detail = capital(r.con.problem.replace(/^says /, 'It says ')) + '.';
        quote = r.con.context;
        pill = h('span', { class: 'pill p-con' }, 'Contradiction');
      } else {
        const mismatch = r.kind === 'mismatch';
        title = mismatch ? `“${r.claim.written}” is a real figure, on the wrong metric or row` : `“${r.claim.written}” is wrong`;
        detail = capital(r.claim.detail) + '.';
        quote = r.claim.context;
        pill = h('span', { class: 'pill ' + (mismatch ? 'p-mis' : 'p-nid') }, mismatch ? 'Wrong label' : 'Wrong number');
      }
      list.append(h('li', { class: 'item' },
        h('span', { class: 'step num' }, String(i + 1)),
        h('div', { class: 'item-main' },
          h('span', { class: 'item-t' }, title),
          h('span', { class: 'item-q' }, `“${cleanQuote(quote)}”`),
          h('span', { class: 'item-d' }, detail),
          h('button', { class: 'link-btn', type: 'button', onclick: () => jumpTo(r.line) }, `Line ${r.line}`)),
        h('span', { class: 'pills' }, pill)));
    });
    card.append(h('div', { class: 'divider' }), h('span', { class: 'lbl' }, "What's wrong"), list);
  }
  const lines = new Set(rows.map((r) => r.line));
  card.append(h('span', { class: 'lbl' }, 'Bottom line'),
    h('p', { class: 'body' }, h('b', {}, `${c.traced} of ${plural(c.total, 'number')}`), ' trace to your export',
      c.cant_check ? `, and ${c.cant_check} can't be checked from one.` : '.',
      lines.size ? ` Fix the ${plural(lines.size, 'flagged line')} before this audit goes to a client.` : ' That checks the numbers, not the advice.'));
  card.append(h('div', { class: 'actions' },
    h('button', { class: 'btn', type: 'button', onclick: () => document.getElementById('all').scrollIntoView({ behavior: 'smooth' }) }, `See all ${plural(c.total, 'number')}`),
    h('button', { class: 'btn', type: 'button', onclick: () => download('openppc-number-check.md', res.markdown) }, icon('download'), 'Download .md'),
    c.cant_check ? h('button', { class: 'btn', type: 'button', onclick: () => copyWorkingAsk(res) }, icon('copy'), 'Ask for the working') : null,
    rows.length ? h('button', { class: 'btn btn-dark', type: 'button', onclick: () => copyFixList(res) }, icon('copy'), 'Copy fix list') : null));
  return card;
}
function copyWorkingAsk(res) {
  const out = ['Please show your working for these numbers in the audit. For each one, list the rows of the export you added up, '
    + 'divided or compared, and the result. If a number is a target or a forecast rather than a figure from the export, say so.', ''];
  for (const x of res.claims.filter((k) => k.verdict === "can't check")) out.push(`- Line ${x.line}, "${x.written}": ${cleanQuote(x.context)}`);
  copyText(out.join('\n'), 'Request copied. Paste it back to whoever wrote the audit.');
}
function copyFixList(res) {
  const out = ['Please fix these numbers in the audit. OpenPPC checked every figure against the account export:', ''];
  for (const r of problems(res)) {
    if (r.kind === 'contradiction') out.push(`- Line ${r.line}: it says ${r.con.problem.replace(/^says /, '')}.`);
    else out.push(`- Line ${r.line}, "${r.claim.written}": ${r.claim.detail.replace(/your files/g, 'the export')}.`);
  }
  out.push('', 'Use only numbers that appear in the export.');
  copyText(out.join('\n'), 'Fix list copied. Paste it back to whoever wrote the audit.');
}
function jumpTo(line) {
  const node = document.getElementById('L' + line);
  if (!node) return;
  node.scrollIntoView({ behavior: 'smooth', block: 'center' });
  node.classList.remove('flash');
  void node.offsetWidth;
  node.classList.add('flash');
}
function annotated(text, res) {
  const byLine = new Map();
  for (const c of res.claims) {
    if (!byLine.has(c.line)) byLine.set(c.line, []);
    byLine.get(c.line).push(c);
  }
  const conLines = new Set(res.contradictions.map((k) => k.line));
  const doc = h('div', { class: 'doc' });
  text.split(/\r?\n/).forEach((raw, i) => {
    const n = i + 1;
    if (!raw.trim()) return;
    const claims = byLine.get(n) || [];
    const shown = raw.replace(/^\s*#{1,6}\s*/, '').replace(/\*\*/g, '');
    let tint = '';
    if (claims.some((c) => c.verdict === 'not in data')) tint = ' t-nid';
    else if (claims.some((c) => c.verdict === 'mismatch')) tint = ' t-mis';
    else if (conLines.has(n)) tint = ' t-con';
    const body = h('span', { class: 'ln-text' });
    let pos = 0;
    for (const c of claims) {
      const at = shown.indexOf(c.written, pos);
      if (at < 0) continue;
      const cls = { traced: 'T', mismatch: 'M', "can't check": 'U' }[c.verdict] || 'N';
      body.append(shown.slice(pos, at), h('mark', { class: `mk ${cls}`, title: capital(c.detail) }, c.written));
      pos = at + c.written.length;
    }
    body.append(shown.slice(pos));
    if (conLines.has(n)) body.append(h('span', { class: 'pill p-con con-note' }, 'Contradiction'));
    doc.append(h('div', { class: 'ln' + (/^\s*#{1,6}\s/.test(raw) ? ' h' : '') + tint, id: 'L' + n }, h('span', { class: 'g' }, String(n)), body));
  });
  const key = (swatch, label) => h('span', { class: 'key' }, swatch, label);
  return h('div', { class: 'card', style: 'overflow:hidden' },
    h('div', { class: 'card-head' }, h('span', { class: 'card-title' }, 'Your audit, annotated'),
      h('div', { class: 'keys' },
        key(h('span', { style: 'width:16px;border-bottom:2px solid var(--ok)' }), 'Traced'),
        key(h('span', { class: 'sw', style: 'background:var(--nid)' }), 'Wrong number'),
        key(h('span', { class: 'sw', style: 'background:var(--mis-bg);box-shadow:inset 0 -2px 0 var(--mis-line)' }), 'Wrong label'),
        key(h('span', { class: 'sw', style: 'background:#d9dedc' }), "Can't check"),
        key(h('span', { class: 'sw', style: 'background:var(--ink)' }), 'Contradiction'))),
    doc);
}
const FLAGGED = new Set(['mismatch', 'not in data']);
function pillFor(verdict) {
  const map = { traced: ['p-ok', 'Traced'], mismatch: ['p-mis', 'Wrong label'], 'not in data': ['p-nid', 'Wrong number'],
    "can't check": ['p-unc', "Can't check"] };
  const [cls, label] = map[verdict] || ['p-nid', verdict];
  return h('span', { class: 'pill ' + cls }, label);
}
function numbersTable(claims) {
  const tbody = h('tbody');
  const fill = (which) => tbody.replaceChildren(...claims
    .filter((c) => which === 'all' || (which === 'bad' ? FLAGGED.has(c.verdict) : which === 'unc' ? c.verdict === "can't check" : c.verdict === 'traced'))
    .map((c) => h('tr', {},
      h('td', { class: 'mono', style: 'color:var(--faint2)' }, String(c.line)),
      h('td', { class: 'num', style: 'font-weight:700' }, c.written),
      h('td', {}, pillFor(c.verdict)),
      h('td', {}, capital(c.detail)))));
  const bad = claims.filter((c) => FLAGGED.has(c.verdict)).length;
  const unc = claims.filter((c) => c.verdict === "can't check").length;
  const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Filter numbers' });
  const filters = [['all', `All ${num(claims.length)}`], ['bad', `Needs attention ${num(bad)}`], ['ok', `Traced ${num(claims.length - bad - unc)}`]];
  if (unc) filters.push(['unc', `Can't check ${num(unc)}`]);
  for (const [which, label] of filters) {
    seg.append(h('button', {
      type: 'button', 'aria-pressed': String(which === 'all'),
      onclick: (e) => { seg.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === e.currentTarget))); fill(which); },
    }, label));
  }
  fill('all');
  return h('div', { class: 'card', id: 'all', style: 'overflow:hidden' },
    h('div', { class: 'card-head' }, h('span', { class: 'card-title' }, `All ${plural(claims.length, 'number')}`), seg),
    h('div', { class: 'table-wrap' }, h('table', { class: 't' },
      h('thead', {}, h('tr', {}, h('th', { style: 'width:56px' }, 'Line'), h('th', { style: 'width:110px' }, 'As written'),
        h('th', { style: 'width:130px' }, 'Verdict'), h('th', {}, 'What your file says'))),
      tbody)),
    h('p', { class: 'foot' }, "A wrong number doesn't match your files: where it is clear what the figure is of, the real one is shown. It may also be rounded differently or come from data you did not include. A wrong label is a real figure on the wrong metric or row. Can't check means a target, a forecast, a what-if, or the audit's own working over rows we can't rebuild: ask for the working. This checks numbers, not advice."));
}
function scoreCard(c) {
  const R = 48;
  const C = 2 * Math.PI * R;
  const total = c.total || 1;
  const segs = [[c.traced, '#1f9d61'], [c.mismatch, '#e39a2d'], [c.not_in_data, '#c0362c'], [c.cant_check || 0, '#c9cfcc']].filter(([n]) => n > 0);
  const gap = segs.length > 1 ? 3 : 0;
  const ring = svg('svg', { width: 120, height: 120, viewBox: '0 0 120 120', 'aria-hidden': 'true' });
  ring.append(svg('circle', { cx: 60, cy: 60, r: R, fill: 'none', stroke: '#eef0ef', 'stroke-width': 12 }));
  let offset = 0;
  for (const [n, color] of segs) {
    const len = (n / total) * C;
    ring.append(svg('circle', { cx: 60, cy: 60, r: R, fill: 'none', stroke: color, 'stroke-width': 12,
      'stroke-dasharray': `${Math.max(len - gap, 0.5)} ${C}`, 'stroke-dashoffset': String(-offset), transform: 'rotate(-90 60 60)' }));
    offset += len;
  }
  const bad = c.mismatch + c.not_in_data;
  const tile = (n, color, label) => h('div', { class: 'tile' }, h('b', { class: 'num', style: `color:${color}` }, num(n)), h('span', {}, label));
  return h('div', { class: 'card score' },
    h('div', { style: 'display:flex;align-items:center;justify-content:space-between' }, h('span', { class: 'card-title' }, 'Number check score'), h('span', { class: 'hint' }, 'Just now')),
    h('div', { class: 'score-row' },
      h('div', { class: 'ring' }, ring, h('div', { class: 'ring-c' }, h('span', { class: 'ring-n num' }, num(c.traced), h('small', {}, `/${num(c.total)}`)), h('span', { class: 'ring-l' }, 'traced'))),
      h('p', { class: 'small', style: 'font-size:14px;color:var(--ink3)' }, `${num(c.traced)} of ${plural(c.total, 'number')} trace to your export.`,
        bad || c.contradictions ? ` ${num(bad + c.contradictions)} ${bad + c.contradictions === 1 ? 'needs' : 'need'} attention before this audit reaches a client.` : '',
        c.cant_check ? ` ${num(c.cant_check)} can't be checked from an export.` : '')),
    h('div', { class: 'tiles' }, tile(c.traced, '#0b8a50', 'Traced'), tile(c.not_in_data, '#c0362c', 'Wrong number'),
      tile(c.mismatch, '#b86e0c', 'Wrong label'), tile(c.contradictions, '#11181c', 'Contradiction')));
}
function sourcesCard(files, industry) {
  return h('div', { class: 'card pad stack' }, h('span', { class: 'card-title' }, 'Checked against'),
    files.map((f) => h('div', { class: 'src' }, h('span', { class: 'src-i' }, icon('file', 18, 1.9)),
      h('span', { class: 'src-t' }, h('b', { class: 'mono' }, f.name), h('span', {}, describe(f.info))))),
    industry ? h('div', { class: 'src' }, h('span', { class: 'src-i grey' }, icon('chart', 18)),
      h('span', { class: 'src-t' }, h('b', {}, industryName(industry)), h('span', {}, 'WordStream / LocaliQ 2026, US search averages'))) : null);
}
function trustCard() {
  return h('div', { class: 'card pad stack' }, h('span', { class: 'card-title' }, 'Why you can trust this'),
    h('p', { class: 'small' }, 'Traced means a figure in your file produces the number at the precision it was written. Code makes every comparison; no AI model is involved.'),
    h('a', { href: 'https://github.com/secondsteplabs/openppc', style: 'font-size:13px;font-weight:600' }, "Read the checker's code"));
}

/* ---------- audit results ---------- */
const escapeHtml = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
let markedReady = false;
function renderMarkdown(md) {
  if (!markedReady) {
    // Reports quote search terms and keywords straight from the export: show any HTML in them as text.
    window.marked.use({ renderer: { html: (token) => escapeHtml(typeof token === 'string' ? token : token.text) } });
    markedReady = true;
  }
  return window.DOMPurify.sanitize(window.marked.parse(md));
}
function reportNode(md) {
  const node = h('div', { class: 'report' });
  node.innerHTML = renderMarkdown(md);  // sanitized by DOMPurify, any HTML in the export shown as text
  return node;
}
async function runAudit() {
  const file = auditFile();
  const template = state.meta.templates.find((t) => t.name === state.template);
  const industry = el.industry.value;
  const minCost = parseFloat(el.minCost.value);
  const brand = el.brandWrap.hidden ? '' : el.brand.value.trim();
  try { localStorage.setItem('openppc.brand', brand); } catch { /* storage can be off; the field still works */ }
  const pre = sampleResult();
  const t0 = performance.now();
  const res = pre ? structuredClone(pre)
    : JSON.parse(await engineCall('audit', template.name, file.path, industry, Number.isFinite(minCost) ? minCost : null, brand));
  const ms = performance.now() - t0;
  if (!res.ok) { toast(capital(res.error)); return; }
  const cards = res.cards && res.cards.template === 'search-term-waste' ? res.cards : null;
  state.lastAudit = { res, cards, client: res.client, token: res.token, fingerprint: res.fingerprint, template,
    file: { name: file.name, info: file.info }, at: new Date() };
  const badge = res.passed
    ? h('span', { class: 'badge badge-ok' }, icon('check', 13, 3), 'Every number traced to your file')
    : h('span', { class: 'badge badge-bad' }, icon('alert', 13), 'Number check failed');
  const head = h('div', { class: 'rep-head' },
    h('div', { class: 'stack', style: 'gap:8px' }, h('h2', { class: 'rep-title' }, template.title), h('span', { class: 'hint' }, `${file.name} · ${describe(file.info)}`), badge),
    h('div', { class: 'actions' },
      h('button', { class: 'btn', type: 'button', onclick: () => copyText(res.markdown, 'Report copied as markdown') }, icon('copy'), 'Copy'),
      h('button', { class: 'btn btn-dark', type: 'button', onclick: () => download(`openppc-${template.name}.md`, res.markdown) }, icon('download'), 'Download .md')));
  const blocks = cards
    ? [h('div', { class: 'card' }, head, kpiStrip(cards.kpis)), todoCard(cards.actions), cards.waste.length ? wasteCard(cards) : null,
      h('details', { class: 'card fold' },
        h('summary', {}, h('span', { class: 'stack', style: 'gap:2px' }, h('span', { class: 'card-title' }, 'Full report'),
          h('span', { class: 'hint' }, 'The same results as text, the way the checker read them'))),
        reportNode(res.markdown))]
    : [h('div', { class: 'card' }, head, reportNode(res.markdown))];
  const left = h('div', { class: 'col' },
    bubble([file], industry, `Run the ${template.title.toLowerCase()}`,
      [!el.threshold.hidden && minCost >= 0 ? `Waste threshold ${el.minCostSign.textContent}${minCost.toLocaleString('en-US')}` : 'Free template',
        brand ? `Brand: ${brand}` : ''].filter(Boolean).join(' · ')),
    h('div', { class: 'col', style: 'gap:10px' }, who(pre ? `${template.title} · the sample, run in advance` : `${template.title} · ${secs(ms)} · on this device`), blocks[0]),
    blocks.slice(1));
  const checkCard = res.passed
    ? h('div', { class: 'green' }, h('span', { class: 'ok-dot' }, (() => { const t = icon('check', 18, 3); t.setAttribute('stroke', '#ffffff'); return t; })()),
      h('b', {}, 'Every number in this report traces back to your data.'),
      h('span', {}, 'The report went through the same checker that judges AI audits, before you saw it.'))
    : h('div', { class: 'redbox' }, h('b', {}, 'This report failed its own number check.'), 'That is a bug in OpenPPC. Please report it with the export that caused it.');
  const right = h('aside', { class: 'side' }, checkCard, sourcesCard([file], industry),
    h('div', { class: 'card pad stack' }, h('span', { class: 'card-title' }, 'Send it to a client'),
      h('p', { class: 'small' }, 'Put your logo and colors on this report and save it as a PDF. The numbers stay checked.'),
      h('a', { class: 'btn', href: '#branded' }, icon('print'), 'Make the branded PDF')),
    h('div', { class: 'card pad stack' }, h('span', { class: 'card-title' }, 'Got an AI audit of this account?'),
      h('p', { class: 'small' }, 'Check it against the same export. Every figure comes back marked traced, wrong number or wrong label.'),
      h('button', { class: 'btn', type: 'button', onclick: () => { go('check'); el.text.focus(); } }, 'Check an AI audit')));
  showResults([left, right], template.title);
}
function kpiStrip(kpis) {
  return h('div', { class: 'kpis' }, kpis.map((k) => h('div', { class: 'kpi' },
    h('span', { class: 'lbl' }, k.label), h('b', { class: 'num' }, k.value), h('span', { class: 'kpi-note' }, k.note))));
}
const TODO = { negative: ['p-nid', 'Negatives'], watch: ['p-mis', 'Watch'], review: ['p-acc', 'Review'], add: ['p-ok', 'New keywords'] };
function todoCard(actions) {
  if (!actions.length) return null;
  return h('div', { class: 'card msg' }, h('span', { class: 'lbl' }, 'What to do'),
    h('ol', { class: 'items' }, actions.map((a, i) => {
      const [cls, label] = TODO[a.kind] || ['p-acc', capital(a.kind)];
      return h('li', { class: 'item' }, h('span', { class: 'step num' }, String(i + 1)),
        h('div', { class: 'item-main' }, h('span', { class: 'item-t' }, a.title), h('span', { class: 'item-d' }, a.detail)),
        h('span', { class: 'pills' }, h('span', { class: 'pill ' + cls }, label)));
    })));
}
function chanceBar(r) {
  if (typeof r.p !== 'number') return h('span', { class: 'muted' }, r.chance || '--');
  const width = Math.round(Math.min(Math.max(r.p, 0), 1) * 100);
  return h('span', { class: 'chance' }, h('span', { class: 'chance-bar' + (r.sure ? ' sure' : '') }, h('span', { style: `width:${width}%` })),
    h('span', { class: 'num' }, r.chance));
}
function wasteCard(cards) {
  const rows = cards.waste;
  const picked = new Set(rows.flatMap((r, i) => (r.sure ? [i] : [])));
  const count = h('span', { class: 'hint', 'aria-live': 'polite' });
  const all = h('input', { type: 'checkbox', 'aria-label': 'Select every search term' });
  const boxes = rows.map((r, i) => h('input', {
    type: 'checkbox', 'aria-label': `Add “${r.term}” as a negative`,
    onchange: (e) => { if (e.currentTarget.checked) picked.add(i); else picked.delete(i); sync(); },
  }));
  function sync() {
    count.textContent = picked.size ? `${plural(picked.size, 'term')} selected` : 'None selected';
    all.checked = picked.size === rows.length;
    all.indeterminate = picked.size > 0 && picked.size < rows.length;
    boxes.forEach((b, i) => { b.checked = picked.has(i); });
  }
  all.addEventListener('change', () => { rows.forEach((_, i) => (all.checked ? picked.add(i) : picked.delete(i))); sync(); });
  sync();
  const chosen = () => rows.filter((_, i) => picked.has(i));
  const more = cards.waste_total - rows.length;
  return h('div', { class: 'card', style: 'overflow:hidden' },
    h('div', { class: 'card-head' },
      h('div', { class: 'stack', style: 'gap:2px' }, h('span', { class: 'card-title' }, 'Wasted spend, ranked'), count),
      h('div', { class: 'actions' },
        h('button', { class: 'btn', type: 'button', onclick: () => downloadNegatives(chosen()) }, icon('download'), 'Download .csv'),
        h('button', { class: 'btn btn-dark', type: 'button', onclick: () => copyNegatives(chosen()) }, icon('copy'), 'Copy as negatives'))),
    h('div', { class: 'table-wrap' }, h('table', { class: 't waste' },
      h('thead', {}, h('tr', {}, h('th', { class: 'pick' }, h('label', { class: 'hit' }, all)), h('th', {}, 'Search term'), h('th', {}, 'Cost'),
        h('th', { class: 'clicks' }, 'Clicks'), h('th', { class: 'wide-only' }, 'Share'), h('th', {}, "Chance it's bad"), h('th', { class: 'wide-only' }, 'Match type'), h('th', { class: 'wide-only' }, 'Suggested'))),
      h('tbody', {}, rows.map((r, i) => h('tr', {},
        h('td', { class: 'pick' }, h('label', { class: 'hit' }, boxes[i])),
        h('td', {}, h('span', { class: 'term' }, r.term),
          r.campaign ? h('span', { class: 'term-c' }, r.automated && r.campaign_type ? `${r.campaign} · ${r.campaign_type}` : r.campaign) : null),
        h('td', { class: 'num' }, r.cost), h('td', { class: 'num clicks' }, r.clicks), h('td', { class: 'num wide-only' }, r.share),
        h('td', {}, chanceBar(r)), h('td', { class: 'muted wide-only' }, r.match_type || '--'),
        h('td', { class: 'wide-only' }, h('span', { class: 'pill ' + (r.sure ? 'p-nid' : 'p-mis') }, r.sure ? 'Negative' : 'Watch'))))))),
    h('p', { class: 'foot' }, (more > 0 ? `Plus ${plural(more, 'more term')} in the full report. ` : '') +
      "Chance it's bad is how likely a term is to convert at under half your account's rate, given the clicks it has had. " +
      'Terms at 90% or more start ticked as negatives; the rest need more clicks before you judge them.'));
}
function copyNegatives(list) {
  if (!list.length) { toast('Tick the search terms to add as negatives first.'); return; }
  copyText(list.map((r) => `[${r.term}]`).join('\n'), `${plural(list.length, 'negative')} copied as exact match. Paste them into Google Ads.`,
    'Copy did not work here. Download the .csv instead.');
}
function csvCell(value) {
  let s = String(value ?? '');
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;  // search terms are typed by strangers: never let one run as a spreadsheet formula
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
function downloadNegatives(list) {
  if (!list.length) { toast('Tick the search terms to add as negatives first.'); return; }
  const lines = [['Campaign', 'Negative keyword', 'Match type', 'Cost', 'Clicks', "Chance it's bad"]]
    .concat(list.map((r) => [r.campaign, r.term, 'Exact', r.cost, r.clicks, r.chance]));
  download('openppc-negatives.csv', lines.map((l) => l.map(csvCell).join(',')).join('\r\n') + '\r\n', 'text/csv');
}

/* ---------- templates ---------- */
function renderGallery() {
  const list = window.OPENPPC_BUNDLE.templates || [];
  el.galleryGrid.replaceChildren(...list.map((t) => h('div', { class: 'card pad stack tcard' },
    h('div', { class: 'tcard-top' }, h('span', { class: 'pill p-ok' }, t.tier === 'free' ? 'Free' : capital(t.tier)), h('span', { class: 'hint' }, t.input)),
    h('span', { class: 'tcard-t' }, t.title),
    h('p', { class: 'small' }, t.summary),
    h('div', { class: 'tcard-actions' },
      h('button', { class: 'btn btn-dark', type: 'button', onclick: () => { state.template = t.name; state.saved.audit = null; go('audit'); } }, 'Run on my export'),
      h('a', { class: 'btn', href: `${REPO}/blob/main/openppc/templates/${t.module}.py` }, icon('code'), 'View source')))));
}

/* ---------- branded PDF ---------- */
/* The report is laid out on fixed pages here, measured block by block: whatever does not fit moves to
   the next page, and long tables continue there under their own header. Then the text of the finished
   pages goes back through the checker, and the PDF can only be saved when every number traces. */
const KIT_KEY = 'openppc.brandkit';
const LOGO_MAX = 400 * 1024;
const SWATCHES = ['#12606d', '#4b32c3', '#b4441f', '#1f2937'];
const PAPER = {
  letter: { name: 'Letter', w: 816, h: 1056, size: '8.5in 11in', cssW: '8.5in', cssH: '11in' },
  a4: { name: 'A4', w: 793.7, h: 1122.5, size: '210mm 297mm', cssW: '210mm', cssH: '297mm' },
};
const HEADINGS = {
  sans: "'Plus Jakarta Sans Variable', 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif",
  serif: "'Source Serif 4 Variable', 'Source Serif 4', Georgia, serif",
};
const TAG_CLASS = { negative: 't-block', watch: 't-watch', review: 't-review', add: 't-grow' };
const FULL_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const BLOCK_TAGS = new Set(['P', 'DIV', 'H1', 'H2', 'H3', 'LI', 'TR', 'TABLE', 'THEAD', 'TBODY', 'SECTION', 'ARTICLE', 'FIGURE', 'UL', 'OL', 'HEADER', 'FOOTER']);
const pdf = { audit: null, kit: null, model: null, run: 0, ready: false, status: null, save: null };

function loadKit() {
  const kit = { agency: '', client: '', title: '', color: SWATCHES[0], logo: '', headings: 'sans', paper: 'letter', off: [] };
  try { Object.assign(kit, JSON.parse(localStorage.getItem(KIT_KEY) || '{}')); } catch { /* no storage or a bad value: defaults */ }
  for (const key of ['agency', 'client', 'title']) if (typeof kit[key] !== 'string') kit[key] = '';
  if (!/^#[0-9a-f]{6}$/i.test(kit.color)) kit.color = SWATCHES[0];
  if (typeof kit.logo !== 'string' || !kit.logo.startsWith('data:image/')) kit.logo = '';
  if (!HEADINGS[kit.headings]) kit.headings = 'sans';
  if (!PAPER[kit.paper]) kit.paper = 'letter';
  if (!Array.isArray(kit.off)) kit.off = [];
  kit.client = '';  // client and title belong to one report; the brand kit is what carries over
  kit.title = '';
  return kit;
}
function saveKit(kit) {
  const { client, title, ...brand } = kit;
  try { localStorage.setItem(KIT_KEY, JSON.stringify(brand)); } catch { /* storage full or off: it still works this visit */ }
}

const initials = (name) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
const codeText = (text) => String(text || '').split('`').map((part, i) => (i % 2 ? h('code', {}, part) : part));
function brandTick(size) {  // the OpenPPC logo's tick, on the report cover and every page footer
  const node = svg('svg', { width: size, height: Math.round(size * 0.893), viewBox: '8.4 11 48.6 43.4', class: 'brand-tick', 'aria-hidden': 'true' });
  node.innerHTML = '<path fill="#4b32c3" d="M12.96 30.29 L24.92 41.72 L55.24 11.35 A1 1 0 0 1 56.76 12.65 L26.76 53.17 Q24.98 55.58 23.21 53.15 L9.04 33.71 A2.6 2.6 0 0 1 12.96 30.29 Z"/>';  // constant markup, never user text
  return node;
}
function seal(size) {
  const tick = icon('check', Math.round(size * 0.55), 3.2);
  tick.setAttribute('stroke', '#ffffff');
  return h('span', { class: 'seal', style: `width:${size}px;height:${size}px` }, tick);
}
function dateParts(iso) { const [y, m, d] = iso.split('-').map(Number); return { y, m: FULL_MONTHS[m - 1], d, mi: m }; }
function fullPeriod(start, end) {
  if (!start || !end) return '';
  const a = dateParts(start);
  const b = dateParts(end);
  return `${a.m} ${a.d}, ${a.y} to ${b.m} ${b.d}, ${b.y}`;
}
function compactPeriod(start, end) {
  if (!start || !end) return '';
  const a = dateParts(start);
  const b = dateParts(end);
  return a.y === b.y ? `${a.m} ${a.d} to ${b.m} ${b.d}, ${b.y}` : fullPeriod(start, end);
}
function monthLabel(start, end) {
  if (!start || !end) return '';
  const a = dateParts(start);
  const b = dateParts(end);
  return a.y === b.y && a.mi === b.mi ? `${a.m} ${a.y}` : compactPeriod(start, end);
}

/* The document: the engine's client pages when the template has them, else the report itself. */
function pdfModel(a) {
  if (a.client) return { ...a.client };
  const info = a.file.info;
  const box = h('div');
  box.innerHTML = renderMarkdown(a.res.markdown);
  const blocks = [];
  for (const node of [...box.children]) {
    const text = node.textContent.trim();
    if (node.tagName === 'HR') break;  // the report's own check line follows; the PDF runs its own check
    if (node.tagName === 'H1' || (node.tagName === 'P' && (text.startsWith('Source:') || text.startsWith('Built by OpenPPC')))) continue;
    if (/^H[2-6]$/.test(node.tagName)) blocks.push({ type: 'h2', text });
    else if (node.tagName === 'TABLE') blocks.push({ type: 'htmltable', node });
    else blocks.push({ type: 'html', node });
  }
  const period = fullPeriod(info.start, info.end);
  let data = `One export from Google Ads: \`${a.file.name}\`, the ${info.kind.toLowerCase()}`;
  if (period) data += ` for ${period}${info.days ? ` (${info.days} days)` : ''}`;
  data += `${info.currency ? `, in ${info.currency}` : ''}. Nothing in the Google Ads account was changed: this report only reads the export.`;
  const method = [{ type: 'h2', text: 'The data' }, { type: 'p', text: data }];
  if (a.fingerprint) method.push({ type: 'fingerprint', value: a.fingerprint });
  method.push({ type: 'check', file: a.file.name });
  return { title: a.template.title, period: compactPeriod(info.start, info.end), month: monthLabel(info.start, info.end),
    file: a.file.name, headline: null,
    sections: [{ id: 'found', title: 'What we found', blocks }, { id: 'method', title: 'How this report was made', blocks: method }] };
}

function coverSheet(kit, model) {
  const head = model.headline;
  const title = kit.title || model.title;
  const mark = kit.logo ? h('img', { class: 'cover-logo', src: kit.logo, alt: '' }) : kit.agency ? h('span', { class: 'cover-mark' }, initials(kit.agency)) : null;
  const date = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
  const inner = h('div', { class: 'cover-inner' },
    h('div', { class: 'cover-top' }, h('div', { class: 'cover-brand' }, mark, kit.agency ? h('span', { class: 'cover-agency' }, kit.agency) : null),
      h('span', { class: 'cover-conf' }, 'Confidential')),
    h('div', { class: 'cover-title' }, kit.client ? h('span', { class: 'cover-eyebrow' }, title) : null,
      h('h1', { class: 'cover-h1' }, kit.client || title), h('span', { class: 'cover-sub' }, ['Google Ads', model.period].filter(Boolean).join(' · '))),
    head ? h('section', { class: 'cover-headline' }, h('span', { class: 'cover-label' }, 'The headline'),
      head.value ? h('span', { class: 'cover-value' }, head.value) : null, h('span', { class: 'cover-text' }, head.text),
      head.stats.length ? h('div', { class: 'cover-rule' }) : null,
      head.stats.length ? h('div', { class: 'cover-stats' }, head.stats.map((s) => h('div', {}, h('span', { class: 'v' }, s.value), h('span', { class: 'l' }, s.label)))) : null) : null,
    h('div', { class: 'cover-foot' },
      h('div', {}, h('span', { class: 'cover-by' }, kit.agency ? `Prepared by ${kit.agency}` : 'Prepared with OpenPPC'), h('span', { class: 'cover-date' }, date)),
      h('div', { class: 'cover-seal' }, brandTick(38), h('div', {}, h('span', { class: 'cover-seal-t' }, 'Numbers checked by OpenPPC'),
        h('span', { class: 'cover-seal-s' }, "Every number traces to the account's own export.")))));
  return h('div', { class: 'sheet cover' }, h('div', { class: 'cover-band' }), inner);
}
function fitCover(cover) {
  const inner = cover.querySelector('.cover-inner');
  for (const size of ['tight', 'tighter']) {
    if (inner.scrollHeight <= inner.clientHeight + 1) return;
    cover.classList.add(size);
  }
}
function pageSheet(kit, model) {
  const mark = kit.logo ? h('img', { class: 'sheet-logo', src: kit.logo, alt: '' }) : kit.agency ? h('span', { class: 'sheet-mark' }, initials(kit.agency)) : null;
  const body = h('div', { class: 'sheet-body' });
  const sheet = h('div', { class: 'sheet' },
    h('header', { class: 'sheet-head', 'data-nocheck': '' }, h('div', { class: 'sheet-brand' }, mark, kit.agency ? h('span', { class: 'sheet-agency' }, kit.agency) : null),
      h('span', { class: 'sheet-where' }, [kit.client, model.month].filter(Boolean).join(' · '))),
    body,
    h('footer', { class: 'sheet-foot', 'data-nocheck': '' }, h('span', {}, kit.agency ? `${kit.agency} · Confidential` : 'Confidential'),
      h('span', { class: 'sheet-checked' }, brandTick(15), 'Numbers checked by OpenPPC'), h('span', { class: 'sheet-page' })));
  return { sheet, body };
}

function stepCard(b, continued, extra) {
  return h('article', { class: 'pdf-step' }, h('span', { class: 'pdf-num' }, String(b.n)),
    h('div', { class: 'pdf-step-main' },
      h('div', { class: 'pdf-step-top' }, h('h3', {}, continued ? `${b.title}, continued` : b.title),
        continued ? null : h('span', { class: `pdf-tag ${TAG_CLASS[b.kind] || 't-review'}` }, b.tag)),
      continued ? null : h('p', {}, codeText(b.text)), extra));
}
function cmpRow(who, value, width, mine) {
  return h('div', { class: `pdf-cmp ${mine ? 'you' : 'them'}` }, h('span', { class: 'pdf-cmp-who' }, who),
    h('span', { class: 'pdf-track' }, h('span', { class: 'pdf-fill', style: `width:${Math.max(width, 1)}%` })), h('span', { class: 'pdf-cmp-val' }, value));
}
function renderBlock(b) {
  switch (b.type) {
    case 'lead': return h('p', { class: 'pdf-lead' }, b.strong ? h('b', {}, b.strong) : null, b.strong && b.text ? ' ' : null, codeText(b.text));
    case 'p': return h('p', { class: 'pdf-p' }, codeText(b.text));
    case 'note': return h('p', { class: 'pdf-note' }, codeText(b.text));
    case 'caption': return h('p', { class: 'pdf-caption' }, b.text);
    case 'h2': return h('h2', { class: 'pdf-h2', 'data-keep': 'next' }, b.text);
    case 'stats': return h('div', { class: 'pdf-stats' }, h('span', { class: 'pdf-stats-t' }, b.title),
      h('div', { class: 'pdf-stats-g' }, b.items.map((i) => h('div', {}, h('span', { class: 'v' }, i.value), h('span', { class: 'l' }, i.label)))));
    case 'step': return stepCard(b, false, null);
    case 'compare': return h('article', { class: 'pdf-compare' },
      h('div', {}, h('h3', {}, b.name), h('span', { class: `pdf-tag ${b.better ? 't-grow' : 't-watch'}` }, b.read)),
      h('div', {}, cmpRow('Yours', b.yours, b.yours_width, true), cmpRow('Industry average', b.average, b.average_width, false)));
    case 'list': return h('ul', { class: 'pdf-list' }, b.items.map((t) => h('li', {}, codeText(t))));
    case 'fingerprint': return h('div', { class: 'pdf-print' }, h('span', { class: 'pdf-print-t' }, 'Fingerprint of the file'), h('code', {}, `sha256 ${b.value}`));
    case 'check': return h('section', { class: 'pdf-check', 'data-nocheck': '' }, seal(44), h('div', {},
      h('h3', {}, 'Every number in this report traces back to the export.'),
      h('p', {}, 'Before this PDF was made, OpenPPC checked all ', h('span', { class: 'pdf-check-n' }, '000'), ' numbers in it against ',
        h('code', {}, b.file), '. Code computed every figure; no AI model wrote a number.'),
      h('p', { class: 'pdf-check-s' }, 'Run OpenPPC on the same file and you get the same numbers.')));
    case 'html': { const node = b.node.cloneNode(true); node.classList.add('pdf-html'); return node; }
    default: return null;
  }
}
function tableShell(cols, align) {
  const rows = h('tbody');
  const node = h('table', { class: 'pdf-table' }, h('thead', {}, h('tr', {}, cols.map((c, i) => h('th', { class: align[i] === 'right' ? 'r' : null }, c)))), rows);
  return { node, rows };
}
const tableRows = (t) => t.rows.map((r) => h('tr', {}, r.map((c, i) => h('td', { class: t.align[i] === 'right' ? 'r' : null }, c))));
/* A block that may run over a page: a shell (its header, repeated on each page) and its rows. */
function splitter(b) {
  if (b.type === 'bars') {
    return {
      shell: (continued) => {
        const rows = h('div');
        return { rows, node: h('figure', { class: 'pdf-bars' }, h('div', { class: 'pdf-bars-head' },
          h('span', { class: 'pdf-bars-t' }, continued ? `${b.title}, continued` : b.title), h('span'),
          h('span', { class: 'pdf-col' }, b.cols[0]), h('span', { class: 'pdf-col' }, b.cols[1])), rows) };
      },
      rows: b.rows.map((r) => h('div', { class: `pdf-bar-row${r.strong ? ' strong' : ''}` }, h('span', { class: 'pdf-term' }, r.label),
        h('span', { class: 'pdf-track' }, h('span', { class: 'pdf-fill', style: `width:${Math.max(r.width, 1)}%` })),
        h('span', { class: 'pdf-cost' }, r.value), h('span', { class: 'pdf-chance' }, r.tag))),
      after: b.caption ? [{ type: 'caption', text: b.caption }] : [],
    };
  }
  if (b.type === 'table') return { shell: () => tableShell(b.cols, b.align), rows: tableRows(b), after: [] };
  if (b.type === 'step' && b.table) {
    return { shell: (continued) => { const t = tableShell(b.table.cols, b.table.align); return { rows: t.rows, node: stepCard(b, continued, t.node) }; },
      rows: tableRows(b.table), after: [] };
  }
  if (b.type === 'htmltable') {
    const head = b.node.querySelector('thead');
    return { shell: () => { const rows = h('tbody'); return { rows, node: h('table', { class: 'pdf-table' }, head ? head.cloneNode(true) : null, rows) }; },
      rows: [...b.node.querySelectorAll('tbody tr')].map((tr) => tr.cloneNode(true)), after: [] };
  }
  return null;
}

function paginate(model, kit, host) {
  host.replaceChildren();
  const cover = coverSheet(kit, model);
  host.append(cover);
  fitCover(cover);
  const sheets = [cover];
  let page = null;
  const fits = () => page.body.scrollHeight <= page.body.clientHeight + 1;
  const newPage = (section, continued) => {
    page = pageSheet(kit, model);
    page.body.append(continued ? h('span', { class: 'pdf-cont' }, `${section.title}, continued`) : h('h1', { class: 'pdf-h1' }, section.title));
    host.append(page.sheet);
    sheets.push(page.sheet);
  };
  const takeKept = () => {  // headings leave with the block that follows them, never alone at a page's foot
    const kept = [];
    while (page.body.children.length > 1 && page.body.lastElementChild.dataset.keep === 'next') {
      const last = page.body.lastElementChild;
      kept.unshift(last);
      last.remove();
    }
    return kept;
  };
  const moveOn = (section, node) => {
    node.remove();
    const kept = takeKept();
    newPage(section, true);
    page.body.append(...kept, node);
  };
  const place = (section, node) => {
    page.body.append(node);
    if (!fits()) moveOn(section, node);
  };
  for (const section of model.sections) {
    if (kit.off.includes(section.id)) continue;
    newPage(section, false);
    for (const b of section.blocks) {
      const split = splitter(b);
      if (!split) {
        const node = renderBlock(b);
        if (node) place(section, node);
        continue;
      }
      let shell = split.shell(false);
      place(section, shell.node);
      for (const row of split.rows) {
        shell.rows.append(row);
        if (fits()) continue;
        row.remove();
        if (!shell.rows.children.length) {
          moveOn(section, shell.node);
        } else {
          newPage(section, true);
          shell = split.shell(true);
          page.body.append(shell.node);
        }
        shell.rows.append(row);
      }
      for (const extra of split.after) place(section, renderBlock(extra));
    }
  }
  sheets.forEach((sheet, i) => {
    const number = sheet.querySelector('.sheet-page');
    if (number) number.textContent = `Page ${i + 1} of ${sheets.length}`;
  });
  const clipped = sheets.findIndex((sheet) => {
    const body = sheet.querySelector('.sheet-body, .cover-inner');
    return body.scrollHeight > body.clientHeight + 1;
  });
  return { sheets, clipped };
}

function textOf(node) {
  let out = '';
  for (const n of node.childNodes) {
    if (n.nodeType === Node.TEXT_NODE) { out += n.nodeValue; continue; }
    if (n.nodeType !== Node.ELEMENT_NODE || n.hasAttribute('data-nocheck')) continue;
    if (n.tagName === 'CODE') { out += ` \`${n.textContent}\` `; continue; }
    if (n.tagName === 'TD' || n.tagName === 'TH') { out += `${textOf(n)} | `; continue; }
    const inner = textOf(n);
    out += BLOCK_TAGS.has(n.tagName) ? `\n${inner}\n` : `${inner} `;
  }
  return out;
}
const pagesText = (sheets) => sheets.map((s) => textOf(s).split('\n').map((l) => l.replace(/\s+/g, ' ').trim()).filter(Boolean).join('\n')).join('\n\n');

function measureHost() {
  let host = document.getElementById('pdf-measure');
  if (!host) {
    host = h('div', { id: 'pdf-measure', 'aria-hidden': 'true' });
    document.body.append(host);
  }
  return host;
}
function applyBrand() {
  const kit = pdf.kit;
  const paper = PAPER[kit.paper];
  for (const node of [el.pdfPages, document.getElementById('pdf-measure')]) {
    if (!node) continue;
    node.style.setProperty('--brand', kit.color);
    node.style.setProperty('--head', HEADINGS[kit.headings]);
    node.style.setProperty('--sheet-w', paper.cssW);
    node.style.setProperty('--sheet-h', paper.cssH);
  }
}
function setPageSize(paper) {
  let style = document.getElementById('page-size');
  if (!style) {
    style = h('style', { id: 'page-size' });
    document.head.append(style);
  }
  style.textContent = `@page { size: ${paper.size}; margin: 0; }`;
}
function scaleSheets() {
  if (!pdf.kit || !el.pdfPages || !el.pdfPages.isConnected) return;
  const paper = PAPER[pdf.kit.paper];
  const s = Math.min(1, el.pdfPages.clientWidth / paper.w);
  for (const wrap of el.pdfPages.children) {
    wrap.style.width = `${paper.w * s}px`;
    wrap.style.height = `${paper.h * s}px`;
    wrap.firstElementChild.style.transform = `scale(${s})`;
  }
}

async function relayout() {
  const run = ++pdf.run;
  const kit = pdf.kit;
  pdf.ready = false;
  if (pdf.save) pdf.save.disabled = true;
  measureHost();
  applyBrand();
  setPageSize(PAPER[kit.paper]);
  try {
    await Promise.all([document.fonts.load("800 38px 'Plus Jakarta Sans Variable'"), document.fonts.load("400 12px 'Geist Mono Variable'"),
      kit.headings === 'serif' ? document.fonts.load("700 38px 'Source Serif 4 Variable'") : null]);
    await document.fonts.ready;
  } catch { /* a font that fails to load falls back; the pages are measured with what shows */ }
  if (run !== pdf.run || state.view !== 'branded') return;
  const { sheets, clipped } = paginate(pdf.model, kit, measureHost());
  const names = [kit.agency, kit.client, kit.title].filter(Boolean);
  if (!pdf.audit.token) {  // the sample's audit was run in advance: run it once in the engine, which keeps it to check against
    pdf.status.textContent = 'Checking the numbers once the checker has loaded…';
    try {
      await engineReady;
      await engineWrite(SAMPLE_PATH(), b64bytes(window.OPENPPC_BUNDLE.samples['search_terms_acme.csv']));
      const real = JSON.parse(await engineCall('audit', 'search-term-waste', SAMPLE_PATH(), 'home-services', SAMPLE().info.min_cost, ''));
      pdf.audit.token = real.token;
    } catch (e) {
      console.error(e);
      pdf.status.className = 'pdf-status bad';
      pdf.status.replaceChildren(h('b', {}, 'Saving is off.'), ' The checker could not start in this browser.');
      return;
    }
    if (run !== pdf.run || state.view !== 'branded') return;
  }
  const res = JSON.parse(await engineCall('verify', pdf.audit.token, pagesText(sheets), JSON.stringify(names)));
  if (run !== pdf.run || state.view !== 'branded') return;
  el.pdfPages.replaceChildren(...sheets.map((s) => h('div', { class: 'sheet-wrap' }, s)));
  scaleSheets();
  const count = res.ok ? res.total.toLocaleString('en-US') : '0';
  for (const n of el.pdfPages.querySelectorAll('.pdf-check-n')) n.textContent = count;
  const pages = plural(sheets.length, 'page');
  if (!res.ok) {
    pdf.status.className = 'pdf-status bad';
    pdf.status.replaceChildren(h('b', {}, 'Saving is off.'), capital(res.error));
  } else if (res.problems.length) {
    for (const c of el.pdfPages.querySelectorAll('.pdf-check')) {
      c.classList.add('bad');
      c.querySelector('h3').textContent = 'This report has numbers the checker could not trace.';
    }
    pdf.status.className = 'pdf-status bad';
    pdf.status.replaceChildren(h('b', {}, `${plural(res.problems.length, 'number')} on these pages did not trace, so saving is off.`),
      h('ul', {}, res.problems.slice(0, 6).map((p) => h('li', {}, p.written ? `${p.written}: ${p.detail}` : capital(p.detail)))),
      'That is a bug in OpenPPC. Please report it with the export that caused it.');
  } else if (clipped >= 0) {
    pdf.status.className = 'pdf-status bad';
    pdf.status.replaceChildren(h('b', {}, `Something on page ${clipped + 1} is taller than a page and would be cut, so saving is off.`),
      'Shorten the client name or report title, or turn off that page.');
  } else {
    pdf.ready = true;
    pdf.status.className = 'pdf-status ok';
    pdf.status.replaceChildren(h('b', {}, `${pages}, ${plural(res.total, 'number')} checked, all traced to ${pdf.audit.file.name}.`),
      'Each page saves exactly as shown. Nothing is cut: what does not fit moves to the next page.');
  }
  if (pdf.save) pdf.save.disabled = !pdf.ready;
}
const relayoutSoon = debounce(relayout, 250);

function savePdf() {
  if (!pdf.ready) return;
  const kit = pdf.kit;
  const before = document.title;
  document.title = [kit.client, kit.title || pdf.model.title, pdf.model.month].filter(Boolean).join(' - ');
  window.print();
  document.title = before;
}

function brandControls() {
  const kit = pdf.kit;
  const change = (key, value, layout = true) => {
    kit[key] = value;
    saveKit(kit);
    if (layout) relayoutSoon(); else applyBrand();
  };
  const text = (key, label, placeholder) => h('div', { class: 'control' }, h('label', { for: `kit-${key}` }, label),
    h('input', { id: `kit-${key}`, class: 'text-input', type: 'text', value: kit[key], placeholder, maxlength: 80, autocomplete: 'off',
      oninput: (e) => change(key, e.currentTarget.value) }));
  const seg = (label, key, options) => h('div', { class: 'control' }, h('span', { class: 'ctl-label' }, label),
    h('div', { class: 'seg', role: 'group', 'aria-label': label }, options.map(([value, name]) => h('button', {
      type: 'button', 'aria-pressed': String(kit[key] === value),
      onclick: (e) => {
        e.currentTarget.parentElement.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === e.currentTarget)));
        change(key, value);
      },
    }, name))));
  const color = h('input', { id: 'kit-color', type: 'color', class: 'color-input', value: kit.color,
    oninput: (e) => { swatches.forEach((s) => s.setAttribute('aria-pressed', 'false')); change('color', e.currentTarget.value, false); } });
  const swatches = SWATCHES.map((c) => h('button', {
    type: 'button', class: 'swatch', style: `background:${c}`, 'aria-label': `Brand color ${c}`, 'aria-pressed': String(kit.color === c),
    onclick: (e) => { swatches.forEach((s) => s.setAttribute('aria-pressed', String(s === e.currentTarget))); color.value = c; change('color', c, false); },
  }));
  const file = h('input', { id: 'kit-logo', type: 'file', accept: 'image/png,image/jpeg,image/webp,image/svg+xml', class: 'sr-only' });
  const removeLogo = h('button', { class: 'link-btn', type: 'button', hidden: !kit.logo, onclick: () => { removeLogo.hidden = true; change('logo', ''); } }, 'Remove logo');
  file.addEventListener('change', () => {
    const f = file.files[0];
    file.value = '';
    if (!f) return;
    if (f.size > LOGO_MAX) { toast('Use a logo under 400 KB.'); return; }
    const reader = new FileReader();
    reader.onload = () => { removeLogo.hidden = false; change('logo', String(reader.result)); };
    reader.readAsDataURL(f);
  });
  const pages = h('div', {}, h('label', { class: 'toggle' }, h('input', { type: 'checkbox', checked: true, disabled: true }), h('span', {}, 'Cover')),
    pdf.model.sections.map((s) => h('label', { class: 'toggle' }, h('input', {
      type: 'checkbox', checked: !kit.off.includes(s.id),
      onchange: (e) => change('off', e.currentTarget.checked ? kit.off.filter((id) => id !== s.id) : [...kit.off, s.id]),
    }), h('span', {}, s.title))));
  pdf.save = h('button', { class: 'btn btn-dark', type: 'button', disabled: true, onclick: savePdf }, icon('print'), 'Save as PDF');
  return [
    h('div', { class: 'card pad stack' }, h('span', { class: 'card-title' }, 'This report'),
      text('client', 'Client', 'e.g. Acme Plumbing'), text('title', 'Report title', pdf.model.title)),
    h('div', { class: 'card pad stack' }, h('span', { class: 'card-title' }, 'Your brand'),
      text('agency', 'Your agency', 'Shown on every page'),
      h('div', { class: 'control' }, h('span', { class: 'ctl-label' }, 'Logo'),
        h('div', { class: 'row' }, h('label', { class: 'btn', for: 'kit-logo' }, 'Choose a logo', file), removeLogo),
        h('span', { class: 'hint' }, 'PNG, JPG, WebP or SVG, under 400 KB. It stays in this browser.')),
      h('div', { class: 'control' }, h('label', { for: 'kit-color' }, 'Brand color'), h('div', { class: 'row' }, swatches, color)),
      seg('Headings', 'headings', [['sans', 'Sans'], ['serif', 'Serif']])),
    h('div', { class: 'card pad stack' }, h('span', { class: 'card-title' }, 'Pages'), pages, seg('Paper', 'paper', [['letter', 'Letter'], ['a4', 'A4']])),
    h('div', { class: 'card pad stack' }, pdf.save,
      h('p', { class: 'small' }, 'Your browser opens its print dialog: choose Save as PDF. Chrome and Edge keep the layout exactly.'),
      h('a', { href: '#audit', class: 'back-link' }, 'Back to the audit')),
  ];
}

function renderBranded() {
  const a = state.lastAudit;
  const heading = h('div', { class: 'no-print' }, h('h1', {}, 'Branded PDF'),
    h('p', { class: 'sub' }, 'Your brand on the audit you ran, page by page as it will print. Every number on these pages is checked before you can save.'));
  if (!a) {
    el.brandedMain.replaceChildren(heading, h('div', { class: 'card pad stack' },
      h('span', { class: 'card-title' }, 'Run an audit first'),
      h('p', { class: 'small' }, 'The branded PDF wraps an audit you ran on this page. Run one on your export, or try it on the sample account.'),
      h('div', { class: 'chips' }, h('a', { class: 'btn btn-dark', href: '#audit' }, 'Audit my export'),
        h('button', { class: 'btn', type: 'button', onclick: trySample }, 'Try the sample account'))));
    el.brandedSide.replaceChildren();
    return;
  }
  if (pdf.audit !== a) {
    pdf.audit = a;
    pdf.kit = loadKit();
    pdf.model = pdfModel(a);
  }
  el.pdfPages = h('div', { id: 'pdf-pages', class: 'pdf-pages' });
  pdf.status = h('div', { class: 'pdf-status no-print', role: 'status', 'aria-live': 'polite' }, 'Laying out the pages…');
  el.brandedMain.replaceChildren(heading, pdf.status, el.pdfPages);
  el.brandedSide.replaceChildren(...brandControls());
  relayout();
}
window.addEventListener('resize', debounce(scaleSheets, 100));

/* ---------- pages ---------- */
function go(view) {
  if (location.hash !== '#' + view) history.pushState(null, '', '#' + view);
  route();
}
function route() {
  const asked = location.hash.slice(1);
  const view = VIEWS.includes(asked) ? asked : 'home';
  state.view = view;
  if (view !== 'branded') document.getElementById('page-size')?.remove();  // the PDF's page size is for the PDF only
  document.querySelectorAll('.rail [data-mode], .rail [data-view]').forEach((n) => {
    if ((n.dataset.mode || n.dataset.view) === view) n.setAttribute('aria-current', 'page'); else n.removeAttribute('aria-current');
  });
  const pages = { home: el.home, templates: el.gallery, rules: el.rules, branded: el.branded };
  for (const node of Object.values(pages)) node.hidden = true;
  if (view === 'check' || view === 'audit') {
    setMode(view);
  } else {
    el.compose.hidden = true;
    el.results.hidden = true;
    el.newBtn.hidden = true;
    el.crumbMode.textContent = 'OpenPPC';
    el.crumbPage.textContent = PAGES[view];
    if (view === 'templates') renderGallery();
    if (view === 'branded') renderBranded();
    pages[view].hidden = false;
  }
  window.scrollTo({ top: 0 });
}
function trySample() {
  state.template = 'search-term-waste';
  state.saved.audit = null;
  go('audit');
  state.autorun = true;  // after go(): an export already loaded must not run in the sample's place
  loadSample();
}

/* ---------- wiring ---------- */
function init() {
  Object.assign(el, {
    text: document.getElementById('audit-text'), count: document.getElementById('num-count'),
    files: document.getElementById('files'), drop: document.getElementById('drop'), input: document.getElementById('file-input'),
    industry: document.getElementById('industry'), minCost: document.getElementById('min-cost'), threshold: document.getElementById('threshold'),
    minCostSign: document.getElementById('min-cost-sign'),
    templates: document.getElementById('templates'), templateField: document.getElementById('template-field'), auditField: document.getElementById('audit-field'),
    run: document.getElementById('run-btn'), stop: document.getElementById('stop-btn'), sample: document.getElementById('sample-btn'), status: document.getElementById('engine-status'),
    compose: document.getElementById('compose'), results: document.getElementById('results'), newBtn: document.getElementById('new-btn'),
    crumbMode: document.getElementById('crumb-mode'), crumbPage: document.getElementById('crumb-page'),
    brand: document.getElementById('brand'), brandWrap: document.getElementById('brand-wrap'),
    title: document.getElementById('compose-title'), sub: document.getElementById('compose-sub'),
    home: document.getElementById('home'), gallery: document.getElementById('gallery'), galleryGrid: document.getElementById('gallery-grid'),
    rules: document.getElementById('rules'), branded: document.getElementById('branded'),
    brandedMain: document.getElementById('branded-main'), brandedSide: document.getElementById('branded-side'),
  });
  document.querySelectorAll('[data-mode]').forEach((b) => b.addEventListener('click', () => go(b.dataset.mode)));
  el.input.addEventListener('change', async () => { for (const f of el.input.files) await addFile(f); el.input.value = ''; });
  for (const type of ['dragenter', 'dragover']) el.drop.addEventListener(type, (e) => { e.preventDefault(); el.drop.classList.add('over'); });
  for (const type of ['dragleave', 'drop']) el.drop.addEventListener(type, (e) => { e.preventDefault(); el.drop.classList.remove('over'); });
  el.drop.addEventListener('drop', async (e) => { for (const f of e.dataTransfer.files) await addFile(f); });
  // the old count goes the moment the text changes, so the button never names a number it is not about to check
  el.text.addEventListener('input', () => {
    state.countRun++;
    state.counting = true;
    el.count.textContent = el.text.value.trim() ? 'Counting the numbers…' : '';
    refresh();
  });
  el.text.addEventListener('input', debounce(updateCount, 250));
  el.minCost.addEventListener('input', () => { el.minCost.dataset.edited = '1'; });
  el.run.addEventListener('click', run);
  el.stop.addEventListener('click', stopRun);
  el.sample.addEventListener('click', loadSample);
  el.newBtn.addEventListener('click', () => { showCompose(); window.scrollTo({ top: 0 }); });
  document.getElementById('home-sample').addEventListener('click', trySample);
  window.addEventListener('hashchange', route);
  try { el.brand.value = localStorage.getItem('openppc.brand') || ''; } catch { /* no storage: start empty */ }
  route();
  boot();
}
init();

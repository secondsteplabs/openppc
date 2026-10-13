/* The Site view, only in the copy of the app that `openppc-online app` serves: it runs `openppc-online site` for
   this page through the job API, from this computer. openppc.si never loads this file.
   It reuses app.js's helpers, which a classic script loaded after app.js can see. APP names every one it uses;
   tests/test_site_view.py checks each is still declared at the top of web/app.js. */
(() => {
  const token = document.querySelector('meta[name="openppc-local"]')?.getAttribute('content') || '';
  if (!token) return;
  const APP = { h, svg, icon, reportNode, download, toast, route, plural, num };  // a missing one stops here, not mid-run
  const POLL = 800;  // ms between looks at a running job
  const GONE = 'openppc-online stopped answering. Start it again (openppc-online app), then reload this page.';

  async function api(path, body) {
    const init = body === undefined ? { headers: { 'X-OpenPPC-Token': token } }
      : { method: 'POST', headers: { 'X-OpenPPC-Token': token, 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    let res;
    try { res = await fetch(path, init); } catch { throw new Error(GONE); }
    let out;
    try { out = await res.json(); } catch { throw new Error(GONE); }
    return { status: res.status, ...out };
  }
  const wait = (ms) => new Promise((done) => setTimeout(done, ms));
  const lines = (text) => text.split('\n').map((s) => s.trim()).filter(Boolean);
  const read = (file) => file.text().then((text) => ({ name: file.name, text }));

  function globe() {
    const node = svg('svg', { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2,
      'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' });
    node.append(svg('circle', { cx: 12, cy: 12, r: 9 }), svg('path', { d: 'M3 12h18' }), svg('path', { d: 'M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18' }));
    return node;
  }
  function check(label, hint, checked = false) {
    const input = h('input', { type: 'checkbox', checked });
    return { input, node: h('label', { class: 'site-check' }, input, h('span', {}, h('b', {}, label), hint ? h('span', { class: 'hint' }, ` ${hint}`) : null)) };
  }
  function control(label, input, opt) {
    const id = `site-${Math.random().toString(36).slice(2, 9)}`;
    input.id = id;
    return h('div', { class: 'control' }, h('label', { for: id }, label, opt ? h('span', { class: 'opt' }, ` (${opt})`) : null), input);
  }

  const f = {
    url: h('input', { class: 'text-input site-wide', type: 'text', inputmode: 'url', autocomplete: 'url', spellcheck: 'false', placeholder: 'example.com' }),
    maxPages: h('input', { class: 'text-input', type: 'number', min: '1', step: '1', placeholder: 'No limit' }),
    minutes: h('input', { class: 'text-input', type: 'number', min: '1', step: '1', placeholder: 'No limit' }),
    external: check('Check links to other sites', 'that they still answer', true),
    fast: check('Fast', 'many requests at once with no pause: your own site only'),
    private: check('Allow private addresses', 'localhost, or a staging server on your network'),
    render: check('Load pages in Chromium', '(--render): tags and events, consent, accessibility, Web Vitals'),
    renderUrls: h('textarea', { class: 'site-area', spellcheck: 'false', placeholder: '/thank-you' }),
    consent: h('input', { class: 'text-input site-wide', type: 'text', spellcheck: 'false', placeholder: '#accept-cookies' }),
    crux: h('input', { class: 'text-input site-wide', type: 'password', autocomplete: 'off', spellcheck: 'false' }),
    packs: h('input', { type: 'file', multiple: true, accept: '.json' }),
    baseline: h('input', { type: 'file', accept: '.json' }),
  };
  const renderInstall = h('p', { class: 'hint', hidden: true });
  const renderMore = h('div', { class: 'controls', hidden: true },
    control('Also render', f.renderUrls, 'pages no link leads to, one per line'),
    control('Consent banner accept button', f.consent, 'CSS selector'));
  f.render.input.addEventListener('change', () => { renderMore.hidden = !f.render.input.checked; });
  const runBtn = h('button', { type: 'button', class: 'btn btn-dark', onclick: run }, 'Audit the site');
  const stopBtn = h('button', { type: 'button', class: 'btn', hidden: true, onclick: stop }, 'Stop');
  const status = h('div', { class: 'status', role: 'status', 'aria-live': 'polite' });
  f.url.addEventListener('keydown', (e) => { if (e.key === 'Enter') run(); });

  const form = h('div', { class: 'col' },
    h('div', {}, h('h1', {}, 'Audit a website'),
      h('p', { class: 'sub' }, 'SEO, links, indexing, structured data, HTTPS and tags, from a crawl of the site. Every number in the report is checked against the crawl.')),
    h('div', { class: 'card composer' },
      h('div', { class: 'field' }, h('label', { class: 'lbl', for: 'site-url' }, 'The site'), f.url),
      h('div', { class: 'controls' }, control('Max pages', f.maxPages, 'optional'), control('Minutes', f.minutes, 'optional')),
      h('div', { class: 'site-checks' }, f.external.node, f.fast.node, f.private.node, f.render.node, renderInstall),
      renderMore,
      h('details', { class: 'site-more' }, h('summary', {}, 'Rule packs, a baseline and real-visitor data'),
        h('div', { class: 'controls' },
          control('Rule packs', f.packs, '.json, rules and suppressions'),
          control('Baseline', f.baseline, 'an earlier .json result: report what is new'),
          control('CrUX API key', f.crux, 'adds real visitors\u2019 Web Vitals from Google'))),
      h('div', { class: 'controls' }, runBtn, stopBtn),
      status));
  f.url.id = 'site-url';
  const results = h('div', { class: 'col', hidden: true });
  const again = h('button', { type: 'button', class: 'btn', hidden: true, onclick: () => show(false) }, 'Audit another site');
  const side = h('div', { class: 'side' },
    h('div', { class: 'card pad stack' }, h('span', { class: 'card-title' }, 'This goes online'),
      h('p', { class: 'small' }, 'Unlike the rest of this app, a site audit connects from this computer to the site you name and to the sites it links to, as openppc-online, politely and within its robots.txt. Audit sites you are allowed to.')),
    h('div', { class: 'card pad stack' }, h('span', { class: 'card-title' }, 'Same as the command line'),
      h('p', { class: 'small' }, 'This runs ', h('code', {}, 'openppc-online site'), ' on this computer. Its report and downloads are the same as the command\u2019s.')),
    again);
  const view = h('section', { class: 'view', id: 'site', hidden: true }, form, results, side);
  document.getElementById('main').append(view);

  const railBtn = h('button', { type: 'button', class: 'ri', 'data-local-view': 'site' }, globe(), 'Site');
  document.querySelector('.rail [data-mode="audit"]').after(railBtn);
  railBtn.addEventListener('click', open);
  document.querySelector('.rail').addEventListener('click', (e) => {
    const item = e.target.closest('a, button');
    if (item && item !== railBtn) close(!item.dataset.localView);
  });
  window.addEventListener('hashchange', () => close());

  function open() {
    for (const node of document.querySelectorAll('.main > .view')) node.hidden = true;
    view.hidden = false;
    document.querySelectorAll('.rail [aria-current]').forEach((n) => n.removeAttribute('aria-current'));
    railBtn.setAttribute('aria-current', 'page');
    document.getElementById('crumb-mode').textContent = 'OpenPPC';
    document.getElementById('crumb-page').textContent = 'Site audit';
    document.getElementById('new-btn').hidden = true;
    document.title = 'Site audit · OpenPPC';
    window.scrollTo({ top: 0 });
  }
  function close(back = true) {
    if (view.hidden) return;
    view.hidden = true;
    railBtn.removeAttribute('aria-current');
    // after the click's own navigation, as a link to the hash showing fires no hashchange; another local view shows itself
    if (back) setTimeout(route, 0);
  }
  function show(result) {
    form.hidden = result;
    results.hidden = !result;
    again.hidden = !result;
    window.scrollTo({ top: 0 });
  }
  function busy(on) {
    runBtn.disabled = on;
    stopBtn.hidden = !on;
    stopBtn.disabled = false;
  }
  function say(text, kind = '') {
    status.className = `status ${kind}`;
    status.textContent = text;
  }

  let current = null;
  async function run() {
    if (runBtn.disabled) return;
    const url = f.url.value.trim();
    if (!url) { say('Give the address of the site to audit, e.g. example.com.', 'error'); f.url.focus(); return; }
    busy(true);
    say('Starting…');
    try {
      const body = {
        kind: 'site', url, fast: f.fast.input.checked, external: f.external.input.checked,
        allow_private: f.private.input.checked, render: f.render.input.checked,
        max_pages: f.maxPages.value ? Number(f.maxPages.value) : null,
        max_time: f.minutes.value ? Number(f.minutes.value) * 60 : null,
        configs: await Promise.all([...f.packs.files].map(read)),
      };
      if (body.render) { body.render_urls = lines(f.renderUrls.value); body.consent_selector = f.consent.value.trim(); }
      if (f.crux.value.trim()) body.crux_key = f.crux.value.trim();
      if (f.baseline.files[0]) body.baseline = await read(f.baseline.files[0]);
      const start = await api('/api/jobs', body);
      if (start.status === 409 && start.kind === 'site') toast(`${start.error} This shows it.`);
      else if (!start.ok) { say(start.error, 'error'); return; }
      await follow(start.id);
    } catch (e) {
      say(e.message, 'error');
    } finally {
      busy(false);
      current = null;
    }
  }
  async function follow(id) {
    current = id;
    for (;;) {
      const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
      if (!job.ok) { say(job.error, 'error'); return; }
      if (job.state === 'failed') { say(job.error, 'error'); return; }
      if (job.state === 'done') { say(''); showResult(job.result); return; }
      say(job.stopping ? `Stopping after this step… ${job.progress}` : job.progress, 'loading');
      await wait(POLL);
    }
  }
  async function stop() {
    if (!current) return;
    stopBtn.disabled = true;
    try { await api(`/api/jobs/${encodeURIComponent(current)}/stop`, {}); } catch (e) { say(e.message, 'error'); }
  }

  function showResult(r) {
    const base = `openppc-site-${new URL(r.origin).host.replace(/[^\w.-]/g, '_')}`;
    const save = (ext, type) => () => download(`${base}.${ext}`, r.texts[ext], type);
    const badge = r.passed
      ? h('span', { class: 'badge badge-ok' }, icon('check', 13, 3), 'Every number traced to the crawl')
      : h('span', { class: 'badge badge-bad' }, icon('alert', 13), 'Number check failed');
    const head = h('div', { class: 'rep-head' },
      h('div', { class: 'stack', style: 'gap:8px' }, h('h2', { class: 'rep-title' }, 'Site audit'),
        h('span', { class: 'hint' }, `${r.origin} · ${plural(r.findings, 'finding')}, ${num(r.high)} high`), badge),
      h('div', { class: 'actions' },
        h('button', { class: 'btn btn-dark', type: 'button', onclick: save('md', 'text/markdown') }, icon('download'), 'Download .md')),
      h('p', { class: 'hint exports' }, 'Also as ',
        h('button', { class: 'link-btn', type: 'button', onclick: save('html', 'text/html') }, '.html'), ', a page to open or send, ',
        h('button', { class: 'link-btn', type: 'button', onclick: save('json', 'application/json') }, '.json'), ' for your own tools (and a later baseline), or ',
        h('button', { class: 'link-btn', type: 'button', onclick: save('sarif', 'application/sarif+json') }, '.sarif'), ' for code scanning.'));
    const warn = r.inconclusive
      ? h('div', { class: 'redbox' }, h('b', {}, 'This scan was too broken to judge the site.'), `The reason: ${r.inconclusive}. The report says what was seen.`)
      : null;
    const broken = r.passed ? null
      : h('div', { class: 'redbox' }, h('b', {}, 'This report failed its own number check.'), 'That is a bug in OpenPPC. Please report it, with the site you audited.');
    results.replaceChildren(...[h('h1', { class: 'sr-only' }, 'Site audit'), warn, broken,
      h('div', { class: 'card' }, head, reportNode(r.texts.md))].filter(Boolean));
    show(true);
  }

  api('/api/info').then((info) => {
    if (info.ok && !info.render) {
      f.render.input.disabled = true;
      renderInstall.hidden = false;
      renderInstall.textContent = `${info.render_install}.`;
    }
  }).catch(() => {});  // the server stopped: Run says so
})();

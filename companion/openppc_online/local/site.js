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
  const AGENCY_MAX = 80;  // characters of the agency name printed on the summary; it never leaves this page
  const RANK = { high: 3, medium: 2, low: 1, info: 0 };
  // PageSpeed Insights' colours: the ring, and text dark enough to read on white
  const BAND = [[90, 'good', '#0cce6b', '#008800'], [50, 'average', '#ffa400', '#c33300'], [0, 'poor', '#ff4e42', '#cc0000']];
  const MEASURE = { FCP: 'fcp', LCP: 'lcp', TBT: 'tbt', CLS: 'cls', SI: 'si' };

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
    single: check('One page only', '(--single): this page, not the whole site'),
    psi: check('Measure with PageSpeed Insights', '(--psi): Google\u2019s speed score and Lighthouse audits, on a phone and a desktop; public pages only'),
    render: check('Load pages in Chromium', '(--render): tags and events, consent, accessibility, Web Vitals'),
    renderUrls: h('textarea', { class: 'site-area', spellcheck: 'false', placeholder: '/thank-you' }),
    consent: h('input', { class: 'text-input site-wide', type: 'text', spellcheck: 'false', placeholder: '#accept-cookies' }),
    crux: h('input', { class: 'text-input site-wide', type: 'password', autocomplete: 'off', spellcheck: 'false' }),
    psiKey: h('input', { class: 'text-input site-wide', type: 'password', autocomplete: 'off', spellcheck: 'false' }),
    agency: h('input', { class: 'text-input site-wide', type: 'text', maxlength: String(AGENCY_MAX), autocomplete: 'organization', spellcheck: 'false' }),
    packs: h('input', { type: 'file', multiple: true, accept: '.json' }),
    baseline: h('input', { type: 'file', accept: '.json' }),
  };
  const renderInstall = h('p', { class: 'hint', hidden: true });
  const renderMore = h('div', { class: 'controls', hidden: true },
    control('Also render', f.renderUrls, 'pages no link leads to, one per line'),
    control('Consent banner accept button', f.consent, 'CSS selector'));
  f.render.input.addEventListener('change', () => { renderMore.hidden = !f.render.input.checked; });
  const runBtn = h('button', { type: 'button', class: 'btn btn-dark', onclick: () => run() }, 'Audit the site');
  // the quick check of one page: Google or this computer, chosen each time and never kept
  const quickPsi = h('button', { type: 'button', class: 'btn', onclick: () => run({ single: true, psi: true, render: canRender }) },
    'Check with Google PageSpeed');
  const quickLocal = h('button', { type: 'button', class: 'btn', onclick: () => run({ single: true, psi: false, render: canRender }) },
    'Check on this computer only');
  const quickLocalHint = h('span', { class: 'hint' }, 'Chromium loads the page here: speed, tags and consent; nothing goes to Google.');
  let canRender = true;
  const stopBtn = h('button', { type: 'button', class: 'btn', hidden: true, onclick: stop }, 'Stop');
  const status = h('div', { class: 'status', role: 'status', 'aria-live': 'polite' });
  f.url.addEventListener('keydown', (e) => { if (e.key === 'Enter') run(); });

  const form = h('div', { class: 'col' },
    h('div', {}, h('h1', {}, 'Audit a website'),
      h('p', { class: 'sub' }, 'SEO, links, indexing, structured data, HTTPS and tags, from a crawl of the site. Every number in the report is checked against the crawl.')),
    h('div', { class: 'card composer' },
      h('div', { class: 'field' }, h('label', { class: 'lbl', for: 'site-url' }, 'The site'), f.url),
      h('div', { class: 'site-quick' }, h('span', { class: 'card-title' }, 'Quick check of this one page'),
        h('div', { class: 'site-quick-row' },
          h('div', { class: 'stack' }, quickPsi, h('span', { class: 'hint' }, 'Sends the address to Google; Google\u2019s test loads fire the page\u2019s tags.')),
          h('div', { class: 'stack' }, quickLocal, quickLocalHint))),
      control('Your agency', f.agency, 'optional, printed on the summary'),
      h('div', { class: 'controls' }, control('Max pages', f.maxPages, 'optional'), control('Minutes', f.minutes, 'optional')),
      h('div', { class: 'site-checks' }, f.single.node, f.external.node, f.fast.node, f.private.node, f.psi.node,
        f.render.node, renderInstall),
      renderMore,
      h('details', { class: 'site-more' }, h('summary', {}, 'Rule packs, a baseline, real-visitor data and API keys'),
        h('div', { class: 'controls' },
          control('Rule packs', f.packs, '.json, rules and suppressions'),
          control('Baseline', f.baseline, 'an earlier .json result: report what is new'),
          control('CrUX API key', f.crux, 'adds real visitors\u2019 Web Vitals from Google'),
          control('PageSpeed Insights API key', f.psiKey, 'optional, for when Google\u2019s shared quota runs out'))),
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
  let lastBody = null;  // the last run as sent, keys included, in this page's memory only: Re-check sends it again
  async function run(choice = {}) {
    if (runBtn.disabled) return;
    const url = f.url.value.trim();
    if (!url) { say('Give the address of the site to audit, e.g. example.com.', 'error'); f.url.focus(); return; }
    busy(true);
    say('Starting…');
    try {
      const body = {
        kind: 'site', url, fast: f.fast.input.checked, external: f.external.input.checked,
        allow_private: f.private.input.checked, render: f.render.input.checked,
        single: f.single.input.checked, psi: f.psi.input.checked,
        max_pages: f.maxPages.value ? Number(f.maxPages.value) : null,
        max_time: f.minutes.value ? Number(f.minutes.value) * 60 : null,
        configs: await Promise.all([...f.packs.files].map(read)),
        ...choice,
      };
      if (body.render) { body.render_urls = lines(f.renderUrls.value); body.consent_selector = f.consent.value.trim(); }
      if (f.crux.value.trim()) body.crux_key = f.crux.value.trim();
      if (f.psiKey.value.trim()) body.psi_key = f.psiKey.value.trim();
      if (f.baseline.files[0]) body.baseline = await read(f.baseline.files[0]);
      await submit(body);
    } catch (e) {
      say(e.message, 'error');
    } finally {
      busy(false);
      current = null;
    }
  }
  async function rerun(changes) {
    if (runBtn.disabled || !lastBody) return;
    show(false);
    busy(true);
    say('Starting…');
    try {
      await submit({ ...lastBody, ...changes });
    } catch (e) {
      say(e.message, 'error');
    } finally {
      busy(false);
      current = null;
    }
  }
  async function submit(body) {
    if (!body.psi) delete body.psi_key;  // a key alone would ask Google: "this computer only" means it
    const start = await api('/api/jobs', body);
    if (start.status === 409 && start.kind === 'site') toast(`${start.error} This shows it.`);
    else if (!start.ok) { say(start.error, 'error'); return; }
    else {
      lastBody = { ...body };
      delete lastBody.baseline;
    }
    await follow(start.id);
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
    let doc = null;
    try { doc = JSON.parse(r.texts.json); } catch { /* the report below still shows */ }
    results.replaceChildren(...[h('h1', { class: 'sr-only' }, 'Site audit'), warn, broken,
      doc && !r.inconclusive ? summary(r, doc) : null,
      h('div', { class: 'card site-full' }, head, reportNode(r.texts.md))].filter(Boolean));
    show(true);
  }

  // The summary a client can read: four answers, the scores, the top fixes and one next step, from the JSON report.
  // Its numbers are the report's, which passed the number check; it adds none of its own.
  const band = (score) => BAND.find(([line]) => score >= line);
  const plain = (text) => text.replace(/`/g, '');
  const agencyName = () => f.agency.value.replace(/[\u0000-\u001f\u007f-\u009f]/g, '').trim().slice(0, AGENCY_MAX);
  const has = (doc, rule) => doc.findings.some((x) => x.rule === rule);

  function answers(doc) {
    const out = [];
    const start = (doc.speed || []).find((s) => s.device === 'mobile' && s.url === doc.start && s.score !== null);
    const phones = (doc.field_data || []).filter((d) => d.device === 'phone' && d.verdict);
    const visitors = phones.find((d) => !d.origin) || phones[0];
    if (start) {
      const [line, name] = band(start.score);
      out.push(['Loads fast on phones', line >= 90 ? 'pass' : line >= 50 ? 'warn' : 'fail',
        `Speed score ${start.score} of 100 on a phone (${name}), from ${start.source}.`]);
    } else if (visitors) {
      out.push(['Loads fast on phones', visitors.verdict === 'passed' ? 'pass' : 'fail',
        `Real phone visitors: Core Web Vitals ${visitors.verdict}${visitors.origin ? ', for the whole site' : ''}.`]);
    } else {
      out.push(['Loads fast on phones', 'unknown', 'Check with PageSpeed: a lab load on this computer is only a rough estimate.']);
    }
    if (!doc.rendered) {
      out.push(['The tags fire', 'unknown', 'Needs the page loaded in Chromium.']);
      out.push(['Consent works', 'unknown', 'Needs the page loaded in Chromium.']);
    } else {
      const fired = Object.values(doc.tags || {}).filter((t) => t.before || t.after || t.ping).length;
      out.push(['The tags fire', has(doc, 'site-no-analytics') ? 'fail' : has(doc, 'site-tag-no-hit') ? 'warn' : fired ? 'pass' : 'warn',
        has(doc, 'site-no-analytics') ? 'No analytics tag was found.'
          : has(doc, 'site-tag-no-hit') ? 'Some tags loaded but sent nothing.'
            : fired ? `${plural(fired, 'tag')} sent hits.` : 'No tag sent anything.']);
      const soft = ['site-no-consent-banner', 'site-consent-not-clicked', 'site-consent-mode-missing'].find((x) => has(doc, x));
      out.push(['Consent works', has(doc, 'site-tag-before-consent') ? 'fail' : soft ? 'warn' : 'pass',
        has(doc, 'site-tag-before-consent') ? 'Tags send data before the visitor agrees.'
          : soft ? doc.findings.find((x) => x.rule === soft).title + '.' : 'Nothing was sent before consent.']);
    }
    const ad = doc.ad_params;
    out.push(['Ad click IDs survive redirects', !ad ? 'unknown' : ad.dropped.length ? 'fail' : 'pass',
      !ad ? 'Not checked: the start page wasn\u2019t fetched with them.'
        : ad.dropped.length ? `A redirect drops ${ad.dropped.join(', ')}.`
          : ad.redirects ? `Kept through ${plural(ad.redirects, 'redirect')} (server redirects only).`
            : 'No redirect: they reach the page (server redirects only).']);
    return out;
  }

  function gauge(score, label, source) {
    const [, , ring, ink] = band(score);
    const r = 34;
    const c = 2 * Math.PI * r;
    const node = svg('svg', { width: 84, height: 84, viewBox: '0 0 84 84', role: 'img', 'aria-label': `${label}: ${score} of 100` });
    node.append(svg('circle', { cx: 42, cy: 42, r, fill: 'none', stroke: '#eeeeee', 'stroke-width': 7 }),
      svg('circle', { cx: 42, cy: 42, r, fill: 'none', stroke: ring, 'stroke-width': 7, 'stroke-linecap': 'round',
        'stroke-dasharray': `${(c * score) / 100} ${c}`, transform: 'rotate(-90 42 42)' }));
    const text = svg('text', { x: 42, y: 49, 'text-anchor': 'middle', 'font-size': 22, 'font-weight': 700, fill: ink });
    text.textContent = String(score);
    node.append(text);
    return h('div', { class: 'site-gauge' }, node, h('b', {}, label), h('span', { class: 'site-badge' }, source));
  }

  function measureValue(key, value, seconds = true) {  // as the report shows it: PSI's in seconds, lab loads' in ms
    if (value === null || value === undefined) return 'not measured';
    if (key === 'cls') return seconds ? value.toFixed(3) : String(value);
    if (key === 'tbt' || !seconds) return `${num(Math.round(value))} ms`;
    return `${(value / 1000).toFixed(1)} s`;
  }

  function devicePanel(doc, words, device) {
    const s = (doc.speed || []).find((x) => x.device === device && x.url === doc.start && x.score !== null);
    const lab = (doc.rendered?.vitals || []).find((v) => v.device === device && v.runs);
    const rows = [];
    if (s) {
      for (const m of s.metrics) {
        const key = MEASURE[m.acronym];
        if (!key) continue;
        const [, name, , ink] = band(Math.round((m.score ?? 0) * 100));
        rows.push(h('li', {}, h('b', {}, words.measures[key][0]), ' ',
          h('span', { style: `color:${ink}` }, `${measureValue(key, m.value)} (${name})`),
          h('span', { class: 'hint' }, ` ${words.measures[key][1]}`)));
      }
      return h('div', { class: 'stack' }, h('p', { class: 'small' }, `From ${s.source}, Lighthouse ${s.lighthouse}.`), h('ul', { class: 'site-measures' }, rows));
    }
    if (lab) {
      for (const key of ['lcp', 'cls', 'tbt']) {
        if (!(key in lab.median)) continue;
        rows.push(h('li', {}, h('b', {}, words.measures[key][0]), ` ${measureValue(key, lab.median[key], false)}`,
          h('span', { class: 'hint' }, ` ${words.measures[key][1]}`)));
      }
      return h('div', { class: 'stack' }, h('p', { class: 'small' }, 'A lab load on this computer: a rough estimate, not PageSpeed\u2019s score.'),
        h('ul', { class: 'site-measures' }, rows));
    }
    return h('p', { class: 'small' }, `Not measured on a ${device === 'mobile' ? 'phone' : 'desktop'}.`);
  }

  function summary(r, doc) {
    const words = r.words;
    const host = new URL(doc.site).host;
    const agency = agencyName();
    const icons = { pass: ['check', 'Pass'], warn: ['alert', 'Check'], fail: ['x', 'Fail'], unknown: ['alert', 'Not checked'] };
    const row = h('div', { class: 'site-answers' }, answers(doc).map(([q, state, why]) =>
      h('div', { class: `site-answer site-${state}` }, h('span', { class: 'site-state' }, icon(icons[state][0], 14, 3), icons[state][1]),
        h('b', {}, q), h('span', { class: 'small' }, why))));
    // Performance as a gauge only when it is a Lighthouse speed score: points from lab loads here are a rough estimate
    const speedScored = (doc.speed || []).some((s) => s.score !== null);
    const scored = Object.entries(doc.scores || {}).filter(([area, s]) => s.score !== null && (area !== 'performance' || speedScored));
    const gauges = scored.length ? h('div', { class: 'site-gauges' }, scored.map(([area, s]) =>
      gauge(s.score, words.areas[area] || area, area === 'performance' ? s.method : 'OpenPPC checks'))) : null;
    const phones = (doc.field_data || []).filter((d) => d.device === 'phone' && d.verdict);
    const seen = phones.find((d) => !d.origin) || phones[0];
    const banner = seen ? h('p', { class: `site-visitors site-${seen.verdict === 'passed' ? 'pass' : 'fail'}` },
      h('b', {}, `Real phone visitors: Core Web Vitals ${seen.verdict}`),
      ` (Chrome UX Report, ${seen.origin ? 'the whole site' : 'this page'}${seen.period ? `, ${seen.period}` : ''}).`) : null;
    const devices = ['mobile', 'desktop'].filter((d) => (doc.speed || []).some((s) => s.device === d && s.score !== null)
      || (doc.rendered?.vitals || []).some((v) => v.device === d && v.runs));
    let tabs = null;
    if (devices.length) {
      const panel = h('div', {});
      const buttons = devices.map((d) => h('button', { type: 'button', class: 'btn site-tab', 'aria-pressed': 'false', onclick: () => pick(d) },
        d === 'mobile' ? 'Phone' : 'Desktop'));
      const pick = (d) => {
        buttons.forEach((b, i) => b.setAttribute('aria-pressed', String(devices[i] === d)));
        panel.replaceChildren(devicePanel(doc, words, d));
      };
      pick(devices[0]);
      tabs = h('div', { class: 'stack' }, h('p', { class: 'small' }, words.why), h('div', { class: 'controls', role: 'group', 'aria-label': 'Device' }, buttons), panel);
    }
    const top = doc.findings.filter((x) => x.severity !== 'info')
      .sort((a, b) => RANK[b.severity] - RANK[a.severity] || b.items.length - a.items.length).slice(0, 3);
    const fixes = top.length ? h('div', { class: 'stack' }, h('span', { class: 'card-title' }, 'Fix these first'),
      h('ol', { class: 'site-fixes' }, top.map((x) => h('li', {}, h('b', {}, plain(x.title)),
        h('span', { class: 'hint' }, ` ${x.severity}; who: ${x.who || 'developer'}; effort: ${x.effort}`), h('div', { class: 'small' }, plain(x.fix)))))) : null;
    let next;
    if (!speedScored) {
      next = ['Check with PageSpeed to compare: Google measures the page as pagespeed.web.dev does.',
        'Check with PageSpeed (sends the address to Google)', { psi: true }];
    } else if (!doc.rendered && canRender) {
      next = ['Load the page in Chromium to check that the tags fire and consent works.', 'Load in Chromium', { render: true }];
    } else if (top.length) {
      next = ['Fix these, then re-check: the new report says what changed.', null, null];
    } else {
      next = ['Nothing to fix. Re-check after the next change to the site.', null, null];
    }
    const recheck = h('button', { type: 'button', class: 'btn', onclick: () => rerun({ baseline: { name: 'previous result.json', text: r.texts.json } }) },
      'Re-check');
    const used = (words.glossary || []).filter(([term]) => r.texts.md.includes(`**${term}:**`));
    const node = h('div', { class: 'card pad stack site-summary' },
      h('div', { class: 'site-summary-head' },
        h('div', { class: 'stack', style: 'gap:4px' }, h('h2', { class: 'site-summary-title' }, `Landing page check: ${host}`),
          h('span', { class: 'hint' }, `${doc.start} \u00b7 ${new Date().toLocaleDateString()}${agency ? ` \u00b7 prepared by ${agency}` : ''}`)),
        h('button', { type: 'button', class: 'btn site-print', onclick: () => window.print() }, icon('print'), 'Print or save as PDF')),
      row, gauges, banner, tabs, fixes,
      r.passed ? h('p', { class: 'small' }, icon('check', 13, 3), ' Every number here is from the report below, and every number in it was checked against the crawl.') : null,
      h('div', { class: 'site-next' }, h('b', {}, 'Next step: '), next[0], ' ',
        next[1] ? h('button', { type: 'button', class: 'btn btn-dark', onclick: () => rerun(next[2]) }, next[1]) : null, ' ', recheck),
      used.length ? h('details', { class: 'site-glossary' }, h('summary', {}, 'Glossary'),
        h('dl', {}, used.flatMap(([term, line]) => [h('dt', {}, term), h('dd', {}, line)]))) : null);
    return node;
  }

  api('/api/info').then((info) => {
    if (info.ok && !info.render) {
      canRender = false;
      quickLocal.textContent = 'Tags and page checks only (no speed)';
      quickLocalHint.textContent = 'Without Chromium on this computer: the page\u2019s HTML, its links and its tags as written.';
      f.render.input.disabled = true;
      renderInstall.hidden = false;
      renderInstall.textContent = `${info.render_install}.`;
    }
  }).catch(() => {});  // the server stopped: Run says so
})();

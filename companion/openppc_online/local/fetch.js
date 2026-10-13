/* The Download view, only in the copy of the app that `openppc-online app` serves: it runs `openppc-online fetch`
   for this page through the job API, from this computer, and hands the files to the audit in this tab.
   openppc.si never loads this file. Like site.js it reuses app.js's helpers; APP names every one it uses, and
   tests/test_site_view.py checks each is still declared at the top of web/app.js. */
(() => {
  const token = document.querySelector('meta[name="openppc-local"]')?.getAttribute('content') || '';
  if (!token) return;
  const APP = { h, icon, download, toast, addBytes, go, route, plural };  // a missing one stops here, not mid-run
  const POLL = 800;  // ms between looks at a running job
  const GONE = 'openppc-online stopped answering. Start it again (openppc-online app), then reload this page.';
  const PLATFORMS = {
    google: {
      title: 'Google Ads', account: '123-456-7890', hint: 'the customer ID at the top of Google Ads',
      credentials: [['GOOGLE_ADS_DEVELOPER_TOKEN', 'Developer token'], ['GOOGLE_ADS_CLIENT_ID', 'OAuth client ID'],
        ['GOOGLE_ADS_CLIENT_SECRET', 'OAuth client secret'], ['GOOGLE_ADS_REFRESH_TOKEN', 'Refresh token'],
        ['GOOGLE_ADS_LOGIN_CUSTOMER_ID', 'Manager account ID', 'optional: for an account under a manager account']],
    },
    microsoft: {
      title: 'Microsoft Advertising', account: '149123456', hint: 'the account ID, all digits',
      credentials: [['MICROSOFT_ADS_DEVELOPER_TOKEN', 'Developer token'], ['MICROSOFT_ADS_CLIENT_ID', 'App (client) ID'],
        ['MICROSOFT_ADS_REFRESH_TOKEN', 'Refresh token'], ['MICROSOFT_ADS_CUSTOMER_ID', 'Customer ID', 'the manager account'],
        ['MICROSOFT_ADS_CLIENT_SECRET', 'Client secret', 'optional: a web app registration only']],
    },
    meta: {
      title: 'Meta', account: 'act_123456789', hint: 'the ad account ID',
      credentials: [['META_ACCESS_TOKEN', 'Access token', 'with the ads_read permission']],
    },
  };

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

  function control(label, input, opt) {
    const id = `fetch-${Math.random().toString(36).slice(2, 9)}`;
    input.id = id;
    return h('div', { class: 'control' }, h('label', { for: id }, label, opt ? h('span', { class: 'opt' }, ` (${opt})`) : null), input);
  }
  const secret = () => h('input', { class: 'text-input site-wide', type: 'password', autocomplete: 'off', spellcheck: 'false' });

  const f = {
    platform: h('select', { class: 'text-input' }, ...Object.entries(PLATFORMS).map(([key, p]) => h('option', { value: key }, p.title))),
    account: h('input', { class: 'text-input site-wide', type: 'text', autocomplete: 'off', spellcheck: 'false' }),
    days: h('input', { class: 'text-input', type: 'number', min: '1', max: '365', step: '1', value: '30' }),
    conversion: h('input', { class: 'text-input site-wide', type: 'text', autocomplete: 'off', spellcheck: 'false', placeholder: 'lead' }),
  };
  const secrets = {};
  const groups = {};
  for (const [key, p] of Object.entries(PLATFORMS)) {
    groups[key] = h('div', { class: 'controls fetch-keys', hidden: key !== 'google' },
      ...p.credentials.map(([name, label, opt]) => { secrets[name] = secret(); return control(label, secrets[name], opt); }));
  }
  const accountHint = h('span', { class: 'hint' });
  const conversionRow = h('div', { class: 'controls', hidden: true },
    control('Conversion', f.conversion, 'the action type that counts, such as lead; leave empty to see the account\u2019s'));
  function pick() {
    const key = f.platform.value;
    for (const [k, node] of Object.entries(groups)) node.hidden = k !== key;
    conversionRow.hidden = key !== 'meta';
    f.account.placeholder = PLATFORMS[key].account;
    accountHint.textContent = PLATFORMS[key].hint;
  }
  f.platform.addEventListener('change', pick);
  pick();

  const runBtn = h('button', { type: 'button', class: 'btn btn-dark', onclick: run }, 'Download');
  const stopBtn = h('button', { type: 'button', class: 'btn', hidden: true, onclick: stop }, 'Stop');
  const status = h('div', { class: 'status', role: 'status', 'aria-live': 'polite' });
  f.account.addEventListener('keydown', (e) => { if (e.key === 'Enter') run(); });

  const form = h('div', { class: 'col' },
    h('div', {}, h('h1', {}, 'Download an ad account'),
      h('p', { class: 'sub' }, 'Your own API access downloads the account\u2019s reports as the files OpenPPC audits. Nothing in the account changes.')),
    h('div', { class: 'card composer' },
      h('div', { class: 'controls' }, control('Platform', f.platform), control('Days', f.days, 'the last full days')),
      h('div', { class: 'field' }, h('label', { class: 'lbl', for: 'fetch-account' }, 'The account'), f.account, accountHint),
      conversionRow,
      h('details', { class: 'site-more', open: true }, h('summary', {}, 'Your API credentials'), ...Object.values(groups)),
      h('div', { class: 'controls' }, runBtn, stopBtn),
      status));
  f.account.id = 'fetch-account';
  const results = h('div', { class: 'col', hidden: true });
  const again = h('button', { type: 'button', class: 'btn', hidden: true, onclick: () => show(false) }, 'Download another');
  const side = h('div', { class: 'side' },
    h('div', { class: 'card pad stack' }, h('span', { class: 'card-title' }, 'This goes online'),
      h('p', { class: 'small' }, 'Unlike the rest of this app, a download connects from this computer to the platform\u2019s API, and only to the addresses it needs, read-only. The credentials go to openppc-online on this computer for the one download and are dropped when it ends; nothing saves them.')),
    h('div', { class: 'card pad stack' }, h('span', { class: 'card-title' }, 'Same as the command line'),
      h('p', { class: 'small' }, 'This runs ', h('code', {}, 'openppc-online fetch'), ' on this computer, which reads the same credentials from environment variables. Its files are the same as the command\u2019s.')),
    again);
  const view = h('section', { class: 'view', id: 'fetch', hidden: true }, form, results, side);
  document.getElementById('main').append(view);

  const railBtn = h('button', { type: 'button', class: 'ri', 'data-local-view': 'fetch' }, icon('download', 20), 'Download');
  (document.querySelector('.rail [data-local-view="site"]') || document.querySelector('.rail [data-mode="audit"]')).after(railBtn);
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
    document.getElementById('crumb-page').textContent = 'Download';
    document.getElementById('new-btn').hidden = true;
    document.title = 'Download · OpenPPC';
    window.scrollTo({ top: 0 });
  }
  function close(back = true) {
    if (view.hidden) return;
    view.hidden = true;
    railBtn.removeAttribute('aria-current');
    if (back) setTimeout(route, 0);  // after the click's own navigation; another local view shows itself
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
    const key = f.platform.value;
    const account = f.account.value.trim();
    if (!account) { say(`Give the account to download: ${PLATFORMS[key].hint}.`, 'error'); f.account.focus(); return; }
    const credentials = {};
    for (const [name] of PLATFORMS[key].credentials) if (secrets[name].value.trim()) credentials[name] = secrets[name].value.trim();
    const days = Number(f.days.value || 30);
    busy(true);
    say('Starting…');
    try {
      const body = { kind: 'fetch', platform: key, account, days, credentials };
      if (key === 'meta' && f.conversion.value.trim()) body.conversion = f.conversion.value.trim();
      const start = await api('/api/jobs', body);
      if (!start.ok) { say(start.error, 'error'); return; }
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
      if (job.state === 'done') {
        for (const input of Object.values(secrets)) input.value = '';  // kept after a failure, to correct one
        say('');
        showResult(job.result);
        return;
      }
      say(job.stopping ? `Stopping… ${job.progress}` : job.progress, 'loading');
      await wait(POLL);
    }
  }
  async function stop() {
    if (!current) return;
    stopBtn.disabled = true;
    try { await api(`/api/jobs/${encodeURIComponent(current)}/stop`, {}); } catch (e) { say(e.message, 'error'); }
  }

  function audit(r) {
    const encode = new TextEncoder();
    close(false);
    go('audit');  // route() leaves this view alone: it closes itself first
    for (const [name, text] of Object.entries(r.files)) addBytes(name, encode.encode(text));
    toast(`${plural(Object.keys(r.files).length, 'file')} from ${PLATFORMS[r.platform].title} added. Pick a template to run.`);
  }
  function showResult(r) {
    const names = Object.keys(r.files);
    const rows = names.map((name) => h('div', { class: 'fetch-file' },
      h('span', {}, h('b', {}, name), h('span', { class: 'hint' }, ` for ${r.templates[name]}`)),
      h('button', { class: 'link-btn', type: 'button', onclick: () => download(name, r.files[name], name.endsWith('.json') ? 'application/json' : 'text/csv') }, 'Save')));
    const head = h('div', { class: 'rep-head' },
      h('div', { class: 'stack', style: 'gap:8px' }, h('h2', { class: 'rep-title' }, `Downloaded from ${PLATFORMS[r.platform].title}`),
        h('span', { class: 'hint' }, plural(names.length, 'file'))),
      h('div', { class: 'actions' },
        h('button', { class: 'btn btn-dark', type: 'button', onclick: () => audit(r) }, 'Audit them here')));
    const notes = r.notes.length ? h('ul', { class: 'fetch-notes' }, ...r.notes.map((n) => h('li', {}, n))) : null;
    results.replaceChildren(h('h1', { class: 'sr-only' }, 'Download'),
      h('div', { class: 'card pad stack' }, head, ...rows, notes));
    show(true);
  }
})();

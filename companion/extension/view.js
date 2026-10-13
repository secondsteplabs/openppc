// SPDX-License-Identifier: MIT
// The popup's report, built from a cleaned reading (inspect.js) with text nodes only: page text never
// becomes markup.
import { summarize } from './match.js';
import { TIMING_BUFFER } from './inspect.js';

/** @param {string} tag @param {string} [cls] @param {...(Node|string|null)} children */
function el(tag, cls, ...children) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  node.append(...children.filter((c) => c !== null && c !== undefined));
  return node;
}

function table(rows, head) {
  const t = el('table');
  if (head) t.append(el('thead', '', el('tr', '', ...head.map((h) => el('th', '', h)))));
  t.append(el('tbody', '', ...rows.map((cells) => el('tr', '', ...cells.map(([value, cls]) => el('td', cls, value))))));
  return t;
}

const yes = (n) => (n ? `yes (${n})` : 'no');
const sized = (value, missing) => (value ? `${value} (${value.length} characters)` : missing);
const states = (pairs) => pairs.map(([k, v]) => `${k} ${v}`).join(', ') || 'no states';

function tagsPart(s, reading) {
  if (!s.tags.length) {
    return [el('p', 'muted', `No known tag among the ${reading.loaded} addresses this page loaded.`)];
  }
  return [table(s.tags.map((t) => [
    [t.name], [t.kind], [yes(t.loads)], [yes(t.hits), t.hits ? 'good' : 'bad'], [t.events.join(', '), 'value'],
  ]), ['Tag', 'Kind', 'Script loaded', 'Sent data', 'Events'])];
}

function layerPart(layer) {
  if (!layer) return [el('p', 'muted', 'The page\'s dataLayer couldn\'t be read.')];
  return [el('p', layer.events.length ? 'value' : 'muted', layer.events.join(', ') || 'No events pushed.')];
}

function consentPart(s, layer) {
  const lines = [
    s.consent.length ? `Consent banner: ${s.consent.join(', ')}.` : 'No known consent banner loaded.',
    s.consentMode
      ? `Google Consent Mode is on${s.deniedPings ? `, with ${s.deniedPings} cookieless ping(s) sent before consent` : ''}.`
      : 'Google Consent Mode not seen in any Google hit.',
  ];
  if (layer?.tcf) lines.push('An IAB TCF consent API (__tcfapi) is on the page.');
  for (const c of layer?.consent ?? []) lines.push(`Consent Mode ${c.command}: ${states(c.states)}.`);
  return lines.map((line) => el('p', '', line));
}

function basicsPart(r) {
  const rows = [
    ['Title', sized(r.title, 'missing'), !r.title], ['Description', sized(r.description, 'missing'), !r.description],
    ['Main headings (h1)', String(r.h1), r.h1 !== 1], ['Canonical', r.canonical || 'missing', !r.canonical],
    ['Robots', r.robots || '(none: indexable)', /noindex/i.test(r.robots)], ['Language', r.lang || 'missing', !r.lang],
    ['Viewport', r.viewport || 'missing', !r.viewport],
    ['Open Graph', r.ogTitle && r.ogImage ? 'title and image' : 'title or image missing', !(r.ogTitle && r.ogImage)],
    ['Structured data', r.types.join(', ') || 'none', !r.types.length],
  ];
  return [table(rows.map(([label, value, bad]) => [[label], [value, bad ? 'value bad' : 'value']]))];
}

/** Fills root with the report on a reading from inspect(). */
export function render(root, reading, signatures) {
  const s = summarize(reading.resources, reading.url, signatures);
  const parts = [
    el('p', 'url muted', reading.url),
    el('h2', '', 'Tags on this page'), ...tagsPart(s, reading),
    el('h2', '', 'Events in the dataLayer'), ...layerPart(reading.layer),
    el('h2', '', 'Consent'), ...consentPart(s, reading.layer),
    el('h2', '', 'Unknown third parties'),
    el('p', 'muted', s.unknownHosts.length
      ? `${s.unknownHosts.join(', ')}: not in OpenPPC's tag list. Check what they are before they count as harmless.`
      : 'None.'),
    el('h2', '', 'Page basics'), ...basicsPart(reading),
  ];
  if (reading.loaded >= TIMING_BUFFER) {
    parts.push(el('p', 'note', `This page loaded ${reading.loaded} addresses. Browsers list the first `
      + `${TIMING_BUFFER} unless the page asks for more, so tags loaded later may be missing.`));
  }
  root.replaceChildren(...parts);
}

export function renderError(root, late = false) {
  root.replaceChildren(el('p', 'bad', late
    ? 'This page didn\'t answer within 5 seconds. Reload it and try again.'
    : 'This page can\'t be read: the browser keeps extensions out of its own pages and the extension store.'));
}

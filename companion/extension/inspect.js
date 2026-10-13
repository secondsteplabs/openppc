// SPDX-License-Identifier: MIT
// What the extension reads from a tab, once, when the toolbar button is pressed. readPage and readLayer run
// inside the page, so they use nothing from this module. The page can answer readLayer with anything, so
// clean() keeps strings only, cut to size, whatever came back.

export const MAX_URLS = 3000;
export const URL_CHARS = 2000;
export const TEXT_CHARS = 300;
export const MAX_EVENTS = 200;
export const EVENT_CHARS = 100;
export const MAX_CONSENT = 20;
export const MAX_STATES = 20;
export const STATE_CHARS = 50;
export const MAX_TYPES = 50;
export const TIMING_BUFFER = 250;    // the browser's default Resource Timing buffer

/** Runs in the extension's isolated world in the page: every address the page loaded, and the SEO basics. */
export function readPage() {
  const meta = (sel) => document.querySelector(sel)?.getAttribute('content') ?? '';
  const types = [];
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const walk = (x) => {
        if (Array.isArray(x)) x.forEach(walk);
        else if (x && typeof x === 'object') {
          if (x['@type']) types.push(...[x['@type']].flat());
          if (x['@graph']) walk(x['@graph']);
        }
      };
      walk(JSON.parse(s.textContent ?? ''));
    } catch { types.push('(unreadable JSON-LD)'); }
  }
  for (const el of document.querySelectorAll('[itemscope][itemtype]')) {
    types.push((el.getAttribute('itemtype') ?? '').split('/').pop());
  }
  return {
    url: location.href,
    resources: performance.getEntriesByType('resource').map((e) => e.name),
    title: document.title, description: meta('meta[name="description"]'),
    canonical: document.querySelector('link[rel="canonical"]')?.getAttribute('href') ?? '',
    robots: meta('meta[name="robots"]'), lang: document.documentElement.lang,
    h1: document.querySelectorAll('h1').length, viewport: meta('meta[name="viewport"]'),
    ogTitle: meta('meta[property="og:title"]'), ogImage: meta('meta[property="og:image"]'),
    types: [...new Set(types)],
  };
}

/**
 * Runs in the page's own world, where the dataLayer is: the events pushed to it (without GTM's own gtm.*),
 * Consent Mode's default and update commands, and whether an IAB TCF banner API is there.
 */
export function readLayer() {
  const layer = Array.isArray(window.dataLayer) ? window.dataLayer.slice(0, 2000) : [];
  const events = [];
  const consent = [];
  for (const e of layer) {
    if (e && typeof e.event === 'string' && !e.event.startsWith('gtm.')) events.push(e.event.slice(0, 100));
    else if (e && e[0] === 'consent' && (e[1] === 'default' || e[1] === 'update')) {
      const states = {};
      for (const [k, v] of Object.entries(typeof e[2] === 'object' && e[2] ? e[2] : {})) {
        if (typeof v === 'string') states[k] = v;
      }
      consent.push({ command: e[1], states });
    }
  }
  return { events, consent, tcf: typeof window.__tcfapi === 'function' };
}

const isObject = (x) => !!x && typeof x === 'object' && !Array.isArray(x);
const text = (x, n = TEXT_CHARS) => (typeof x === 'string' ? x.slice(0, n) : '');
const texts = (x, max, n) => (Array.isArray(x)
  ? x.filter((s) => typeof s === 'string').slice(0, max).map((s) => s.slice(0, n)) : []);

function consentOf(c) {
  if (!isObject(c) || (c.command !== 'default' && c.command !== 'update')) return null;
  const states = Object.entries(isObject(c.states) ? c.states : {})
    .filter(([, v]) => typeof v === 'string').slice(0, MAX_STATES)
    .map(([k, v]) => [k.slice(0, STATE_CHARS), v.slice(0, STATE_CHARS)]);
  return { command: c.command, states };
}

/** What the popup shows from, whatever page and layer hold: layer is null when the page's world couldn't be read. */
export function clean(page, layer) {
  const p = isObject(page) ? page : {};
  const l = isObject(layer) ? layer : null;
  return {
    url: text(p.url, URL_CHARS),
    resources: texts(p.resources, MAX_URLS, URL_CHARS),
    loaded: Array.isArray(p.resources) ? p.resources.length : 0,
    title: text(p.title), description: text(p.description), canonical: text(p.canonical, URL_CHARS),
    robots: text(p.robots), lang: text(p.lang), viewport: text(p.viewport),
    ogTitle: text(p.ogTitle), ogImage: text(p.ogImage, URL_CHARS),
    h1: Number.isSafeInteger(p.h1) && p.h1 >= 0 ? p.h1 : 0,
    types: texts(p.types, MAX_TYPES, TEXT_CHARS),
    layer: l && {
      events: [...new Set(texts(l.events, MAX_EVENTS, EVENT_CHARS))],
      consent: (Array.isArray(l.consent) ? l.consent.slice(0, MAX_CONSENT) : []).map(consentOf).filter(Boolean),
      tcf: l.tcf === true,
    },
  };
}

/** Reads the tab: throws when the browser doesn't let extensions in (its own pages, the extension store). */
export async function inspect(tabId) {
  const [{ result: page }] = await chrome.scripting.executeScript({ target: { tabId }, func: readPage });
  let layer = null;
  try {
    [{ result: layer }] = await chrome.scripting.executeScript({ target: { tabId }, world: 'MAIN', func: readLayer });
  } catch {
    layer = null;
  }
  return clean(page, layer);
}

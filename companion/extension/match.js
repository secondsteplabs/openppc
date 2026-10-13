// SPDX-License-Identifier: MIT
// Which tag an address belongs to, by the patterns in signatures.json: the same rules as
// openppc_online/siteaudit/tags.py, checked against the same cases (companion/tests/tag_cases.json).

/** @param {string} host @param {string} suffix */
const hostIs = (host, suffix) => host === suffix || host.endsWith(`.${suffix}`);

/** @param {string} url */
function parts(url) {
  try {
    const u = new URL(url);
    return { host: u.hostname.toLowerCase(), path: u.pathname, query: u.search.slice(1), params: u.searchParams };
  } catch {
    return null;
  }
}

/** @param {{host?: string, path?: string, contains?: string}} p @param {string} url */
function matches(p, url) {
  const u = parts(url);
  return !!u && (!p.host || hostIs(u.host, p.host)) && u.path.startsWith(p.path ?? '')
    && `${u.path}?${u.query}`.includes(p.contains ?? '');
}

/** [vendor id, "hit" or "load"] for an address, or null. A hit (the tag sending data) wins over a load. */
export function vendorOf(url, signatures) {
  for (const kind of ['hit', 'load']) {
    const v = signatures.vendors.find((vendor) => vendor[kind].some((p) => matches(p, url)));
    if (v) return [v.id, kind];
  }
  return null;
}

export const EVENT_CHARS = 100;

/** [vendor id, the events a tag hit names in its address], or null for an address that isn't a hit. */
export function eventsOf(url, signatures) {
  const found = vendorOf(url, signatures);
  if (!found || found[1] !== 'hit') return null;
  const v = signatures.vendors.find((x) => x.id === found[0]);
  const fixed = v.hit.find((p) => p.event && matches(p, url))?.event;
  if (fixed) return [found[0], [fixed]];
  const query = new URLSearchParams(parts(url)?.query ?? '');
  const key = (v.events ?? []).find((k) => query.get(k));
  return [found[0], key ? [query.get(key).slice(0, EVENT_CHARS)] : []];
}

/** A host a known tag uses, whatever the request to it was for. */
export function knownHost(host, signatures) {
  return signatures.vendors.some((v) => [...v.load, ...v.hit].some((p) => p.host && hostIs(host, p.host)));
}

export function consentPlatformOf(url, signatures) {
  const u = parts(url);
  return u ? signatures.consent.find((c) => c.hosts.some((h) => hostIs(u.host, h)))?.id ?? null : null;
}

/** A Google hit carrying a denied consent state (gcs=G100, G101 or G110): Consent Mode's cookieless ping. */
export function consentModePing(url) {
  const gcs = parts(url)?.params.get('gcs') ?? '';
  return gcs.length === 4 && gcs.startsWith('G1') && gcs.slice(2).includes('0');
}

/** A Google hit carrying a consent state (gcs or gcd): Consent Mode is set, however it was set. */
export function consentModeOn(url, signatures) {
  const u = parts(url);
  const id = vendorOf(url, signatures)?.[0];
  return !!u && !!(u.params.get('gcs') || u.params.get('gcd')) && (id === 'ga4' || id === 'google-ads');
}

/** The registrable-ish site of a host: the last two labels, or three for hosts like shop.example.co.uk. */
export function siteOf(host) {
  const labels = host.split('.');
  const n = labels.length > 2 && labels.at(-2).length <= 3 && labels.at(-1).length === 2 ? 3 : 2;
  return labels.slice(-n).join('.');
}

/**
 * What a page's addresses show: each tag found and the events it named, consent banners, Consent Mode,
 * and unknown third parties.
 */
export function summarize(urls, pageUrl, signatures) {
  const page = parts(pageUrl);
  const tags = new Map();
  const platforms = new Set();
  const unknown = new Set();
  let modeOn = false;
  let pings = 0;
  for (const url of urls) {
    const found = vendorOf(url, signatures);
    if (found) {
      const [id, kind] = found;
      const v = signatures.vendors.find((x) => x.id === id);
      const tag = tags.get(id) ?? { id, name: v.name, kind: v.kind, loads: 0, hits: 0, events: [] };
      tag[kind === 'hit' ? 'hits' : 'loads'] += 1;
      for (const name of eventsOf(url, signatures)?.[1] ?? []) {
        if (!tag.events.includes(name)) tag.events.push(name);
      }
      tags.set(id, tag);
    }
    const platform = consentPlatformOf(url, signatures);
    if (platform) platforms.add(platform);
    modeOn ||= consentModeOn(url, signatures);
    pings += consentModePing(url) ? 1 : 0;
    const u = parts(url);
    if (u && page && siteOf(u.host) !== siteOf(page.host) && !found && !platform && !knownHost(u.host, signatures)) {
      unknown.add(u.host);
    }
  }
  return {
    tags: [...tags.values()].sort((a, b) => a.name.localeCompare(b.name)),
    consent: [...platforms].map((id) => signatures.consent.find((c) => c.id === id).name),
    consentMode: modeOn,
    deniedPings: pings,
    unknownHosts: [...unknown].sort(),
  };
}

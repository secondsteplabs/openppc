// SPDX-License-Identifier: MIT
// The extension's matcher (companion/extension/match.js) gives the answers tags.py gives (tag_cases.json),
// and sums a page's addresses up. Run with: node --test companion/tests/js/
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import {
  clean, EVENT_CHARS, MAX_CONSENT, MAX_EVENTS, MAX_STATES, MAX_URLS, STATE_CHARS, TEXT_CHARS, URL_CHARS,
} from '../../extension/inspect.js';
import {
  consentModeOn, consentModePing, consentPlatformOf, eventsOf, knownHost, siteOf, summarize, vendorOf,
} from '../../extension/match.js';

const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const signatures = read('../../extension/signatures.json');
const cases = read('../tag_cases.json');

test('the matcher gives tags.py\'s answers', () => {
  const checks = {
    vendor_of: (url) => vendorOf(url, signatures),
    events_of: (url) => eventsOf(url, signatures),
    known_host: (host) => knownHost(host, signatures),
    consent_platform_of: (url) => consentPlatformOf(url, signatures),
    consent_mode_ping: (url) => consentModePing(url),
    consent_mode_on: (url) => consentModeOn(url, signatures),
  };
  for (const [name, check] of Object.entries(checks)) {
    assert.ok(cases[name].length > 0, name);
    for (const [given, expected] of cases[name]) assert.deepEqual(check(given), expected, `${name}(${given})`);
  }
  const others = ['about', 'in_text']; // in_text is the WordPress plugin's
  assert.deepEqual(Object.keys(cases).filter((k) => !others.includes(k)).sort(), Object.keys(checks).sort());
});

test('a page summary lists each tag\'s events once, in the order first named', () => {
  const s = summarize([
    'https://www.facebook.com/tr/?ev=PageView', 'https://www.facebook.com/tr/?ev=PageView',
    'https://www.google-analytics.com/g/collect?v=2&en=purchase', 'https://www.facebook.com/tr/?ev=Lead',
  ], 'https://shop.test/', signatures);
  assert.deepEqual(s.tags.map((t) => [t.id, t.events]), [['ga4', ['purchase']], ['meta', ['PageView', 'Lead']]]);
});

test('a page summary lists tags, banners and unknown third parties', () => {
  const s = summarize([
    'https://shop.example.co.uk/',
    'https://cdn.example.co.uk/app.js',
    'https://www.googletagmanager.com/gtag/js?id=G-ABC123',
    'https://region1.google-analytics.com/g/collect?v=2&gcs=G100',
    'https://connect.facebook.net/en_US/fbevents.js',
    'https://cdn.cookielaw.org/scripttemplates/otSDKStub.js',
    'https://cdn.taboola.com/libtrc/x.js',
    'not a url',
  ], 'https://shop.example.co.uk/', signatures);
  assert.deepEqual(s.tags.map((t) => [t.id, t.loads, t.hits]), [['ga4', 1, 1], ['meta', 1, 0]]);
  assert.deepEqual(s.consent, ['OneTrust']);
  assert.ok(s.consentMode);
  assert.equal(s.deniedPings, 1);
  assert.deepEqual(s.unknownHosts, ['cdn.taboola.com']);
  assert.equal(siteOf('www.example.com'), 'example.com');
});

test('a reading keeps what a page sends back in shape and in size', () => {
  const long = 'x'.repeat(5000);
  const r = clean({
    url: 'https://shop.test/', resources: [...Array(MAX_URLS + 10).fill(long), 7], title: long, h1: -1,
    types: ['Product', { '@type': 'x' }], description: { toString: () => 'no' },
  }, {
    events: ['add_to_cart', 'add_to_cart', long, null, ...Array(MAX_EVENTS + 5).fill(0).map((_, i) => `e${i}`)],
    consent: [
      { command: 'default', states: { ad_storage: 'denied', analytics_storage: 3, [long]: long } },
      { command: 'set', states: {} }, null, 'consent',
      ...Array(MAX_CONSENT).fill({ command: 'update', states: Object.fromEntries(
        Array(MAX_STATES + 5).fill(0).map((_, i) => [`k${i}`, 'granted'])) }),
    ],
    tcf: 'yes',
  });
  assert.equal(r.resources.length, MAX_URLS);
  assert.equal(r.loaded, MAX_URLS + 11);
  assert.ok(r.resources.every((u) => u.length === URL_CHARS));
  assert.equal(r.title.length, TEXT_CHARS);
  assert.equal(r.description, '');
  assert.equal(r.h1, 0);
  assert.deepEqual(r.types, ['Product']);
  assert.equal(r.layer.events[0], 'add_to_cart');
  assert.equal(r.layer.events[1].length, EVENT_CHARS);
  assert.equal(r.layer.events.length, MAX_EVENTS - 1);  // the repeated add_to_cart counted once
  assert.deepEqual(r.layer.consent[0], {
    command: 'default', states: [['ad_storage', 'denied'], ['x'.repeat(STATE_CHARS), 'x'.repeat(STATE_CHARS)]],
  });
  assert.equal(r.layer.consent.length, MAX_CONSENT - 3);
  assert.ok(r.layer.consent.slice(1).every((c) => c.command === 'update' && c.states.length === MAX_STATES));
  assert.equal(r.layer.tcf, false);
});

test('a page whose world can\'t be read, or that answers nonsense, still gives a reading', () => {
  for (const [page, layer] of [[null, null], ['page', []], [[1, 2], 'layer'], [{ resources: 'x' }, { events: 'x' }]]) {
    const r = clean(page, layer);
    assert.deepEqual(r.resources, []);
    assert.equal(r.url, '');
    assert.ok(r.layer === null || (r.layer.events.length === 0 && r.layer.consent.length === 0));
  }
  assert.equal(clean({}, null).layer, null);
});

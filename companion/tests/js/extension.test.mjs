// SPDX-License-Identifier: MIT
// The extension's matcher (companion/extension/match.js) gives the answers tags.py gives (tag_cases.json),
// and sums a page's addresses up. Run with: node --test companion/tests/js/
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

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
  assert.deepEqual(Object.keys(cases).filter((k) => k !== 'about').sort(), Object.keys(checks).sort());
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

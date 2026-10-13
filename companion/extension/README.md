# OpenPPC Tag Inspector

A browser extension for Chrome and Edge. Click it on any page to see:

- the marketing tags the page loaded, and whether each one sent data (Google Analytics 4, Google Ads, Meta,
  TikTok, LinkedIn, Microsoft Advertising and the rest of `signatures.json`), with the events each named
- the events the page pushed to its Google Tag Manager dataLayer
- the consent banner it loaded, Google Consent Mode's default and update states, the cookieless pings sent
  before consent, and whether an IAB TCF consent API is there
- third parties that aren't in OpenPPC's tag list
- the page basics: title, description, main headings, canonical, robots, language, viewport, Open Graph and
  structured data

It uses the same tag rules as `openppc-online site --render`, which checks a whole site the same way.

## Install it from this folder

1. Open `chrome://extensions` (or `edge://extensions`) and turn on **Developer mode**.
2. Click **Load unpacked** and choose this `extension` folder.
3. Pin the extension, open a page, and click it.

To package it for a store, zip the contents of this folder. Everything in it ships, and a test keeps it that way.

## What it can and can't do

It reads the page once, when you click, and only that tab. Nothing is stored, and nothing is sent anywhere:
the extension has no permission to reach any site, its pages may only load their own files, and a test fails
if its code gains a way to send data.

What it reads:

- the addresses the page has loaded, from the browser's own list (Resource Timing)
- the page's `dataLayer`
- the page's head and headings

The limits that come with reading the page instead of watching its traffic:

- The browser lists the first 250 addresses a page loads unless the page asks for more. The popup says when
  a page reached that.
- Requests made inside other sites' frames aren't listed.
- A page can clear the list, or answer with anything it likes. The popup cuts what it gets to size and shows
  it as text only, but treat a reading as the page's own account of itself.
- Events a tag batches in a POST body don't show in its address. The dataLayer usually names the same events.

## Permissions

| Permission | Why |
| --- | --- |
| `activeTab` | Lets the extension read the tab you clicked it on, for that click only. |
| `scripting` | Runs the two reading functions in that tab: one for the addresses and page basics, one for the dataLayer. |

It asks for no host permissions, no storage, no background worker and no network access.

## Store listing (draft)

**Name:** OpenPPC Tag Inspector

**Summary:** The marketing tags a page loaded and fired, their events, consent and Consent Mode, and SEO basics.
Sends nothing.

**Privacy:** collects no data. It reads the current tab only when you click the extension, keeps nothing
after the popup closes, and sends nothing to anyone.

Icons and screenshots come with the store submission.

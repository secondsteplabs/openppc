# Changelog: openppc-online

Semantic versioning, as in OpenPPC. Each release names the `openppc` versions it works with.

## Unreleased (0.5.0)

Needs `openppc` 0.4.

### Added

- **`openppc-online fetch google|microsoft|meta ACCOUNT --out DIR`**: downloads an ad account's reports with your
  own API credentials, from environment variables, and writes them as the files `openppc audit` reads, printing
  the audit command for each. Google Ads API v25 gives `search_terms.csv` (Performance Max's search terms
  included), `keywords.csv`, `account.json` and `account_structure.json`; Microsoft Advertising's Reporting API v13
  the first three; Meta's Graph API v25.0 `account.json` and `account_structure.json`, with `--conversion` naming
  the action type that counts. `--days` (30 by default, at most 365) and `--force`.
- Each platform's calls are checked against a list of methods, hosts and paths before connecting; no redirect is
  followed, nothing in an account changes, and no credential reaches a file, the output or an error. Nothing is
  written until every report is in.
- `fetch/versions.py`: each API version with its sunset date. The command warns within 60 days of one, and a test
  fails then.
- **The Download view in `openppc-online app`:** the same download from a form, its files listed and saved, and
  **Audit them here**, which opens the audit with them loaded. The credentials go in the request, live in that job
  only and are cleared when it ends; Stop ends a download with nothing.
- THREAT_MODEL.md: the `fetch` section, and the job API's download.

### Changed

- The job API's 409 names the kind of job already running, and the Site view follows only a site audit.
- On a phone, the app's rail sizes its items by their labels, so seven fit at 360 px.

## Unreleased (0.4.0)

### Added

- **The Tag Inspector browser extension** (`extension/`, its own version 0.1.0), for Chrome and Edge. Click it on
  a page to see the tags the page loaded and fired, their events, the dataLayer's events, the consent banner,
  Consent Mode's default and update states, cookieless pings, unknown third parties and the SEO basics. It asks
  for `activeTab` and `scripting` only and sends nothing. Not in a store yet: load it from the folder.
- The extension and the crawler use the same `signatures.json`, and `tests/tag_cases.json` holds the answers both
  must give.
- **OpenPPC Site Check, a WordPress plugin** (`wordpress/openppc-site-check/`, its own version 0.1.0, WordPress
  5.8+, PHP 7.4+): five checks in Tools > Site Health (indexing, the home page's search basics, ad and analytics
  tags, a consent banner when there are tags, a sitemap in robots.txt), each naming the `openppc-online site`
  command for the full check. It reads only its own site and follows no redirect. Not in the plugin directory yet.

### Changed

- The crawler reads the tag patterns ASCII-only (`\d` and `\b` as PHP's PCRE reads them), so it, the extension and
  the plugin give the same answers: a tag ID written with non-ASCII digits is no longer a tag.

## Unreleased (0.3.0)

Needs `openppc` 0.4.

### Added

- **`openppc-online site --render`**: Chromium loads the home page and one page per section to see which tags fire
  before and after consent, the events they send, links only JavaScript adds (then crawled), accessibility
  problems (axe-core 4.10.3, shipped in the package) and lab Web Vitals on a simulated phone. With
  `--render-pages`, `--vitals-pages`, `--render-url`, `--consent-selector` and `--screenshots`. Install it with
  `pip install "openppc-online[render]"` and `playwright install chromium`.
- The browser reaches the network only through a proxy on 127.0.0.1 that applies the crawler's guard, loopback
  included.
- THIRD_PARTY_LICENSES.md: axe-core (MPL-2.0) and Playwright.
- **The Site view in `openppc-online app`:** a form for `openppc-online site` (with `--render` when installed),
  its report on the page, downloads as .md, .html, .json and .sarif, and Stop. It is in the copy of the app this
  command serves only; openppc.si is unchanged.
- The app's job API behind it: `POST /api/jobs`, `GET /api/jobs/<id>`, `POST /api/jobs/<id>/stop`, for this
  page only (THREAT_MODEL.md).

### Fixed

- `openppc-online app`: on some Windows machines a page load stalled for half a minute and came up without
  `app.js`. The server now writes in 8 KB pieces.

### Changed

- The checks that need a browser say "run again with `--render`" instead of "a browser, which this version doesn't
  run", and the rulebook's 12 browser rules are live.

## Unreleased (0.2.0)

Needs `openppc` 0.4.

### Added

- **`openppc-online site`**: crawls a website and checks its SEO, links, indexing, structured data, HTTPS, AI
  crawler access and the tags in its HTML, in a scored report where every number is traced. robots.txt and
  Crawl-delay are obeyed; `--max-pages`, `--max-time`, `--max-per-pattern`, `--fast`, `--no-external`.
- Rule packs and project configs (`--config`, with three examples), `--baseline` to fail only on new problems,
  `--fail-on`, and `--format md|json|html|sarif`, the JSON with its own schema. The HTML is the `openppc` report
  page.
- `--crux-key`: real visitors' Web Vitals from Chrome's UX Report, with your own Google API key.
- `--post-to`: POST the JSON result to a webhook, `https://` or `http://` to this computer.
- Exit codes 2 (a finding at `--fail-on`), 3 (the report failed its own number check) and 4 (a scan too broken to
  judge).
- Every connection goes through one guard that refuses private, link-local and cloud-metadata addresses after each
  DNS lookup, unless `--allow-private` (metadata never), and caps sizes, redirects and decompression.
- `rulebook/`: each check with its source, checked by the tests as `openppc`'s is.
- THREAT_MODEL.md: the crawler's section.

The browser pass (rendered pages, consent, tracking events, accessibility and lab Web Vitals) is not in 0.2.0;
the report says which checks wait for it.

## Unreleased (0.1.0)

Needs `openppc` 0.4.

### Added

- **`openppc-online app`**: the OpenPPC app, served from this computer on 127.0.0.1 (port 8766, or any free one),
  with `--port` and `--no-browser`. Audits and checks run in the browser tab, as on openppc.si; the page says when
  openppc-online is serving it.
- [THREAT_MODEL.md](THREAT_MODEL.md): what the server guards and how, each defence with its test.

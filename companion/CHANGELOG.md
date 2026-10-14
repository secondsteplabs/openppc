# Changelog: openppc-online

Semantic versioning, as in OpenPPC. Each release names the `openppc` versions it works with.

## Unreleased (0.6.0)

### Added

- **Measuring sends no visits to the site's analytics.** The Web Vitals loads answer tag hits (GA4, Google Ads,
  Meta, LinkedIn and the rest of `signatures.json`) with an empty 204 on this computer; the tag scripts still load,
  so their cost is measured. The report says how many were answered, and the JSON's `vitals` items gain
  `hits_answered`. The tags and consent pass stays a real visit.
- **`--psi`: Google PageSpeed Insights' numbers in the report.** The start page and each `--render-url` page (at
  most 5) are measured on a phone and a desktop by PSI, through the guard; no key needed (`--psi-key KEY` or
  `OPENPPC_PSI_KEY` for your own quota). The Performance area becomes PSI's speed score for the start page on a
  phone, and its findings cost no points of their own; lab LCP, CLS and TBT findings come from Lighthouse's numbers;
  a Speed section shows each page's score and five metrics; an "All Lighthouse audits" section lists every audit,
  what affects the ad click first, mapped to OpenPPC's own rules by a parity matrix
  (`siteaudit/lab/lighthouse-13.csv`). Pages PSI measured aren't measured again with `--render`. It needs no
  browser on this computer. Public pages only: `--allow-private`, private hosts and secret-looking addresses are
  refused before anything is sent, and Google is asked only once robots.txt is read, for the pages it lets OpenPPC
  fetch. A dropped connection to PSI is tried once more.
- **`--single`: one page, not the whole site.** The start page and any `--render-url` pages, no sitemap, no links
  followed or checked; whole-site rules (shared titles, the sitemap, the missing-page probe, other sites' links)
  don't run, and the report says so. With `--render`, Web Vitals on a phone and a desktop.
- **Real visitors' data as PageSpeed Insights shows it:** good, needs-improvement and poor shares, and p75, for LCP,
  INP, CLS, FCP and TTFB; the Core Web Vitals assessment (passed, failed or none); phones and desktops; the page's
  data first and the whole site's when the page has too few visitors. From PSI with `--psi`, or from the CrUX API
  with `--crux`, which now asks for desktops, histograms, FCP and TTFB too.
- **Ad click IDs through server redirects** (`site-ad-params-dropped`): the start page is asked for once more with
  `gclid`, `gbraid`, `wbraid`, `msclkid`, `fbclid` and the five `utm_` parameters set to `OPENPPC-TEST`, and a
  redirect that loses or changes any of them is a high finding. Server redirects only, for now: a redirect in
  JavaScript, or a script that rewrites the address, isn't seen. The site's logs and CRM may record the test value.
- **Plain words for clients:** a "What the speed measures mean" section (what each measure means for someone who
  clicked an ad), a line in plain words on the ten Lighthouse audits that fail most on landing pages, and a glossary
  of the terms the report uses (`siteaudit/words.py`).
- **A summary a client can read, in the app's Site view,** above the full report: pass, warn or fail answers to
  four questions (loads fast on phones, the tags fire, consent works, ad click IDs survive redirects), score gauges in
  PageSpeed's colours with their source, the real-visitor verdict, phone and desktop measures in plain words, the
  top three fixes with who usually makes each, one next step, Re-check (this result becomes the baseline), a
  glossary, an agency name and a print layout for a one-page PDF. A quick check of one page offers "Check with Google
  PageSpeed" and "Check on this computer only" as equal buttons, chosen each run. "Loads fast on phones" comes only
  from PageSpeed or real visitors; Performance shows no gauge when it is the rough estimate.
- JSON: `who` on findings (developer, hosting, tag manager) and `ad_params` (the redirect check's result).
- The app's Site form gains "One page only", "Measure with PageSpeed Insights" and a PSI key field.
- JSON: a top-level `speed` list (each Lighthouse result, its metrics, categories and audits, and its real-visitor
  data), `single`, `scores.<area>.method`, and `device`, `shares`, `verdict` and `source` on `field_data` items and
  `device` on `vitals` items. Additive, so `format_version` stays 1.
- Rulebook rows for the speed score, PSI's limits, each Lighthouse category, the real-visitor assessment and
  `--single`.

### Changed

- **Lab Web Vitals are measured from a trace, as Lighthouse 13.5 measures one** (`siteaudit/lab/metrics.py`, ported
  from Lighthouse, its trace engine and speedline): First Contentful Paint and Largest Contentful Paint of the main
  frame, Total Blocking Time between First Contentful Paint and Time to Interactive, Cumulative Layout Shift over
  the frame tree in session windows, time to first byte, and the new **Speed Index** from the trace's screenshots.
  A load waits as Lighthouse's does: for the network and the main thread to go quiet, 45 seconds at most. The
  report shows the load Lighthouse CI would pick (nearest the middle FCP and TTI) with the range of all loads, and
  says when the loads disagree more than Lighthouse CI accepts. JSON `vitals` items gain `representative`, `shown`,
  `range`, `unstable` and `no_tti`; `median` stays.
- **`--runs N`** (1 to 9, default 3): loads of the first measured page per device; later pages get one each. With
  one load, a lab number less than 20% over its good line isn't a finding; the report notes it instead.
- Speed loads run in Chromium's new headless mode, which paints as a visitor's Chrome does, not the headless shell.
  Its own calls home (update checks, sign-in, push, Google's search preconnect and AI Mode check) are refused before
  any name is resolved, and the JSON's `rendered.browser_calls` lists the hosts it tried. The guard refuses names
  under `.invalid` without looking them up.
- **Lab Web Vitals load the page as Lighthouse loads its own tab** (`siteaudit/lab/throttle.py`): a Moto G Power
  screen (412x823 at 1.75x, was 2.625x) with Lighthouse's mobile user agent, and its mobile throttling as DevTools
  applies it: 562.5 ms latency, 1.44 Mbps down, 675 Kbps up, 4x CPU. The old 150 ms and 1.6 Mbps were the inputs of
  Lighthouse's simulator, which made lab numbers look better than the phone they named. Expect slower numbers.
- A load still going after 45 seconds is measured as it is then, as Lighthouse does, and the report says so; it
  used to wait 60 seconds and then lose the measurement. The JSON's `vitals` items gain `capped`.
- The report and README say "throttled phone (rough estimate)", not "simulated phone": Lighthouse's own score
  simulates the slow phone, and this lab doesn't.
- **`--crux` turns on real visitors' data, and `--crux-key KEY` gives the key** (and turns it on). `--crux` alone
  reads `OPENPPC_CRUX_KEY`. The old `--crux-key` with no key took the next argument, a URL included, as the key.
- CrUX's requests go through the site check's guard, with its size and time limits, like every other connection.
  An API key never follows a redirect.
- `--render-url` works with `--psi` as well as `--render`.
- The real-visitor findings read phones' whole-site data, as before; the table now shows phones and desktops.

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

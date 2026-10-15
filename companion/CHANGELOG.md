# Changelog: openppc-online

Semantic versioning, as in OpenPPC. Each release names the `openppc` versions it works with.

## Unreleased (0.6.0)

### Added

- **Measuring sends no visits to the site's analytics.** The Web Vitals loads answer the page's tag hits (GA4,
  Google Ads, Meta, LinkedIn and the rest of `signatures.json`) with an empty 204 on this computer; the tag scripts
  still load, so their cost is measured. A tag inside another site's frame, or in a worker, isn't caught, and the
  report says so. The report says how many were answered, and the JSON's `vitals` items gain `hits_answered`. The
  tags and consent pass stays a real visit.
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
  redirect that loses or changes any of them is a high finding. Server redirects here; what the page's scripts do
  is `site-ad-params-dropped-js`, below. The site's logs and CRM may record the test value.
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
- **Lighthouse's insights on each measured page,** with what fixing each would save: render-blocking files, image
  delivery, the main image found late, document latency, layout shift culprits, cache lifetimes, third parties and
  the rest of Lighthouse 13.5's insight audits. One more load at full speed per page and device is traced, and the
  DevTools trace engine Lighthouse pins (`@paulirish/trace_engine` 0.0.65, vendored as
  `siteaudit/vendor/trace-engine.js` with its licences) simulates the slow phone or desktop on it as Lighthouse
  does, in a blank page of the same browser. On the calibration pages its results match Lighthouse's with simulated
  throttling. JSON: `vitals` items gain `insights`, `insights_error` and `trace_engine`.
- **What each tag costs:** from the same full-speed load, the bytes and main-thread time of each known tag's and
  consent platform's files, counted as Lighthouse's third-parties insight counts them; hits the load answered on this
  computer are left out, since what they cost isn't the vendor's. JSON: `vitals` items gain `tag_costs`.
- **JavaScript errors on the page** (`site-js-errors`): the tags and consent pass notes uncaught script errors and
  console errors (at most 10 a page, not files that failed to load, which the crawl and the guard report), and a
  page with any is a medium finding showing the first. JSON: `rendered.pages` items gain `errors`.
- **Ad click IDs through the page's scripts** (`site-ad-params-dropped-js`): with `--render`, the start page is also
  loaded in Chromium with the test parameters, and a click ID the server's redirects kept but the address no longer
  has once its scripts ran is a medium finding. Tag hits, and any request taking the test value to another host from
  any frame or worker, are answered on this computer. JSON: `rendered.ad_params`.
- **A consent banner that pushes the page** (`site-consent-banner-shift`): layout shifts before the banner is
  accepted, in which a node in the banner moved, content moved by the banner's height, or that came within half a
  second of the banner going in, are added up; at Cumulative Layout Shift's good line (0.1) or more, a medium finding.
  The report's consent line gives the number. JSON: `rendered.pages` items gain `banner_shift`.
- **`--lighthouse FOLDER`: your own Lighthouse 13, on this computer.** The pages `--psi` would measure (the start
  page and up to 4 `--render-url` pages) are measured by the Lighthouse installed in FOLDER, in OpenPPC's browser
  through the guard, on a phone and a desktop with simulated throttling and PSI's four categories: the same report
  as `--psi`, with no key, nothing sent to Google, and private or staging pages allowed with `--allow-private`. Its
  loads fire the page's tags, as PSI's do. Needs Node.js and the `render` extra; can't be combined with `--psi`.
- **Speed budgets** in `--config` files: per page glob and device, a `max` for each timing (`fcp`, `lcp`, `tbt`,
  `cls`, `si`, `ttfb`) or size by Lighthouse's file types (`script-kb` and the rest) and a `min` speed score. A page
  over a line is a finding of the budget's severity, its note naming the line and the number's source: Lighthouse's
  result with `--psi` or `--lighthouse`, else the lab's timings with `--render`. A budget nothing measured is an info
  finding, not a pass. Example: `examples/rulepacks/landing-speed.json`; schema: `budgets` in
  `site-config.schema.json`.
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
- **An OpenPPC lab score, uncalibrated:** Lighthouse's speed score formula on the load shown, 0 to 100 with
  PageSpeed's colours, for each page and device measured here. It isn't PageSpeed's score and doesn't count toward
  Performance until the lab is checked against Lighthouse on the same computer. Beside it, a fixed explanation of
  why lab numbers differ from PageSpeed's, and this computer's Lighthouse benchmark index, with Lighthouse's
  slow-CPU warning at 1000 or below. JSON: `score` and `score_label` on `vitals` items, `rendered.benchmark_index`.
  The app's summary shows the score and all six measures for lab loads.
- **The lab is checked against Lighthouse itself:** a calibration harness (`tests/calibration`, the scheduled
  `calibration` workflow) loads 19 local pages with OpenPPC's lab and with Lighthouse 13.5 (devtools throttling),
  alternating, in the same browser through the same guard, and gates the medians on the plan's tolerances; it also
  times the guard's proxy and records Lighthouse's simulated numbers. Lighthouse attaches over a DevTools port on
  127.0.0.1 to a page OpenPPC opened (`siteaudit/lab/lighthouse.py`), and the guard refuses that port to every page.
  The lab score stays labelled uncalibrated until the gate passes. The pages are served over HTTPS and HTTP/2 as
  real sites are (`--plain` for the old HTTP/1.1), with one host on HTTP/1.1 only and a page whose web font swaps
  in late; two more pages fire GA4 and Adobe hits, chained pixel included, and their numbers are published three
  ways, not gated: OpenPPC answering the hits itself (as it measures), OpenPPC sending them, and Lighthouse.
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
- `--render-url` works with `--psi` and `--lighthouse` as well as `--render`.
- The real-visitor findings read phones' whole-site data, as before; the table now shows phones and desktops.
- A PSI or CrUX key with anything but letters, digits, `-` and `_` is refused before anything is sent. A CrUX error
  is shown as written, in a code span, so its numbers don't fail the report's own check.
- A stop while PageSpeed Insights works (Ctrl-C or the app's Stop) keeps what was crawled, starts no more PSI calls
  and retries none. An answer from PSI or CrUX that isn't what Google sends is an error on that page, not the run.
- The app: "Check on this computer only" sends no CrUX key either; Re-check sends only the findings as its
  baseline; the next step's re-run keeps the form's keys, extra pages and consent button; the `psi` field is always
  checked, and a PSI key without it asks Google nothing; the Performance gauge shows only when Performance is
  PageSpeed's score.
- The ad click ID check is sent only when robots.txt allows it on the start page's host as well as where the start
  page moved to.
- On Windows, a large file a throttled speed load was still reading could arrive cut short through the browser's
  proxy (`ERR_CONNECTION_RESET` or `ERR_CONTENT_LENGTH_MISMATCH`), so its paint never counted: Windows dropped what
  the proxy had buffered when the connection closed. The proxy's sends to the browser now finish only once the
  browser has the bytes. Found by the calibration's heavy-image page.
- The app: a refused request (another site's, a wrong token, not JSON) could get a connection reset instead of its
  answer on Windows, since the app closed without reading what was sent. It now waits up to 2 seconds for the
  client to finish sending, throws that away and then closes.
- Layout shift on a phone could read 0 where Lighthouse counted the shift, a web font swapping in for one. Chrome
  marks shifts soon after the screen size is set as following input, and Lighthouse forgives that for 500 ms from the
  page's first screen-size event; OpenPPC counted from the blank page before it, so the 500 ms had run out before the
  page loaded. Found by the calibration's web-font page.

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

# openppc-online

The optional companion to [OpenPPC](https://github.com/secondsteplabs/openppc), for the jobs that need more than a
browser tab or an offline command: each runs only when you run it.

OpenPPC itself never goes online. `pip install openppc` never installs this, and the `openppc` command never calls
it. This is a separate install with its own command, so that stays true without exceptions.

It is not released yet. Version 0.1.0 is its foundation, the app on your computer; 0.2.0 adds the website check,
`openppc-online site`, 0.3.0 its browser pass, `--render`, 0.4.0 the Tag Inspector browser extension, and 0.5.0
downloads with your own API credentials, `openppc-online fetch`.

## What it promises

These are pledges 6 to 9 in OpenPPC's [GOVERNANCE.md](https://github.com/secondsteplabs/openppc/blob/main/GOVERNANCE.md#the-online-companion):

- **Off unless you install it and run it.** Installing `openppc` never installs it, and OpenPPC never calls it.
- **Read-only.** It reads reports and pages. It never creates, changes or deletes anything in an ad account or on a
  site.
- **Your own credentials.** It uses API keys and tokens you create, kept on your machine. OpenPPC never ships,
  proxies or stores one.
- **Only the hosts it declares.** Each command below lists every host it connects to.

## Commands

### `openppc-online app`

```
openppc-online app
openppc-online app --port 8800 --no-browser
```

Opens the OpenPPC app from this computer, at `http://127.0.0.1:8766/` (or any free port if that one is taken). It is
the same app as [openppc.si/app](https://openppc.si/app/): audits and checks run in the browser tab, and your files
stay on your computer. The line at the top of the page names openppc-online when this server is serving it.

It adds one view openppc.si doesn't have: **Site**, in the left rail, runs `openppc-online site` (below) from a
form. It has the start page, page and time limits, fast, external links, private addresses, `--render` with its
extra pages and consent selector, `--single`, `--psi`, rule packs, a baseline, and CrUX and PSI keys. A quick check
of one page has two equal buttons, "Check with Google PageSpeed" (the address goes to Google) and "Check on this
computer only", chosen each run and never kept. Above the report, a summary a client can read: four pass, warn or
fail answers (loads fast on phones, the tags fire, consent works, ad click IDs survive redirects), the scores as
gauges, real visitors' verdict, phone and desktop measures in plain words, the top three fixes with who usually makes
each, one next step, and Re-check, which runs it again with this result as the baseline. An agency name, typed on
the form, is printed on it, and printing it (or saving as PDF) gives the summary alone. The report downloads as
.md, .html, .json or .sarif. Stop ends the run at its next step and keeps what was crawled, as Ctrl-C does.
`--post-to` and `--screenshots` are command-line only.

**Download**, below it, runs `openppc-online fetch` (below) from a form: the platform, the account, the days, Meta's
conversion, and your API credentials, typed into the page. It lists the files, saves each one, and **Audit them
here** opens the audit with them loaded, in the same tab. The credentials go to this server for that one download
and are dropped when it ends; nothing saves them, the page never sends them back, and the form empties once a
download succeeds. Stop ends a download with
nothing.

Runs happen in this process, one at a time; the page keeps the last few results in memory and writes nothing to
disk.

- **Hosts:** it answers only on 127.0.0.1. Serving the app connects to nothing; the page loads its Python runtime,
  libraries and fonts from cdn.jsdelivr.net, as on openppc.si. A site audit connects to what
  `openppc-online site` connects to, and a download to what `openppc-online fetch` connects to.
- **Security:** it answers only to its own address, and the page gets a new token on each run, which every call to
  this server needs; a site audit or a download can be started only by that page.
  [THREAT_MODEL.md](https://github.com/secondsteplabs/openppc/blob/main/companion/THREAT_MODEL.md) has the details.

Exit codes: 0 when it stops normally (Ctrl-C), 1 for bad input, as `openppc` uses them.

### `openppc-online site`

```
openppc-online site https://example.com
openppc-online site example.com --max-pages 200 --format html --out site.html
openppc-online site https://example.com --config openppc-site.json --baseline last.json --fail-on high
openppc-online site https://example.com --render --render-url /thank-you
openppc-online site https://example.com/landing --single --psi
```

Crawls the site from the page you name and checks what a landing page needs before ads point at it: SEO, broken
links and redirects, indexing (robots.txt, sitemaps, canonicals, noindex), structured data, HTTPS and security
headers, which AI crawlers robots.txt lets in, and the tracking tags in the HTML. The report is scored, and every
number in it is traced, as in an `openppc` audit.

It reads robots.txt first and obeys it, Crawl-delay included, and asks two pages at a time, half a second apart
(`--fast` asks eight at a time with no pause, for your own site). It keeps no cookies and fills in no forms.

To see whether the ad click survives the landing page's redirects, it asks for the start page once more with the ad
platforms' click IDs (`gclid`, `gbraid`, `wbraid`, `msclkid`, `fbclid`) and the five `utm_` parameters set to
`OPENPPC-TEST`, and checks the address it ends on still has them. That request looks like an ad click to the
server, so the site's logs, and a CRM that reads those parameters on the server, may record `OPENPPC-TEST`; no tag
fires, since no browser runs it. Only server redirects are checked for now.

Check only sites you own or have permission to check. It names itself in every request, as
`OpenPPC-SiteAudit/<version> (+https://openppc.si)` in its user agent. robots.txt rules for `OpenPPC`, or for every
crawler, apply to it, so a site's owner can see it in their logs and turn it away.

- **Hosts:** the site you name (and the host its start page moves to), the hosts it links to (one `HEAD` or `GET`
  per link, which `--no-external` skips), with `--render` the hosts the rendered pages load from (tags, fonts,
  CDNs), chromeuxreport.googleapis.com only with `--crux`, pagespeedonline.googleapis.com only with `--psi`, and
  the webhook's host only with `--post-to`. Nothing else.
- **Private addresses:** it refuses to connect to private, local, link-local and cloud-metadata addresses, checked
  on every connection and redirect, the browser's included. `--allow-private` opens private and local ones, to
  check localhost or a staging server on your network; link-local and metadata addresses never open.

**`--render`** loads the home page and one page per section (5 by default) in Chromium, to see what only
JavaScript shows: which tags fire before and after the consent banner is accepted, the events they send, links
that appear only after JavaScript runs (which it then crawls), accessibility problems (axe-core, against WCAG A
and AA), and lab Web Vitals on a throttled phone: three loads of the home page (`--runs N` for more), set up as
Lighthouse sets up its own tab, traced, and measured as Lighthouse measures a trace (First Contentful Paint, Largest
Contentful Paint, Total Blocking Time, Cumulative Layout Shift, Speed Index, time to first byte), and the load
Lighthouse CI would pick shown with the range of all of them, and an OpenPPC lab score from Lighthouse's formula,
labelled uncalibrated and kept out of the Performance score. A rough estimate, since Lighthouse's own score simulates
the slow phone instead (the report explains the difference, and gives this computer's benchmark index); with one
load, a number just over a line isn't made a finding. Without it, those checks say
they need it instead of passing. It needs Playwright and Chromium:

```
pip install "openppc-online[render]"
playwright install chromium
```

The browser keeps no cookies between pages, runs no service workers, downloads nothing, and reaches the network
only through the check's own guard, on 127.0.0.1, for as long as the pass runs. Chromium's own calls home (update
checks, sign-in, Google's search preconnect) are refused before any name is looked up, and the report lists the hosts
it tried. The Web Vitals loads answer tag
hits the page sends themselves, so measuring a page sends no visits to its analytics or ad accounts (a tag inside
another site's frame, or in a worker, isn't caught); the tags and consent pass is
a real visit.

**`--psi`** asks Google PageSpeed Insights to measure the start page (and each `--render-url` page, at most 5 in
all) on a phone and on a desktop, as [pagespeed.web.dev](https://pagespeed.web.dev) does: Google loads them on its
own servers with Lighthouse. The report then has PSI's 0 to 100 speed score as its Performance score, the five lab
metrics, real visitors' data from Chrome's UX Report (the page's, or the whole site's when the page has too few
visitors), the Core Web Vitals assessment, and every Lighthouse audit, with what affects the ad click first. It
needs no browser on this computer and no key: Google's shared quota is used, and when it runs out, a free key of
your own (`--psi-key KEY`, or `OPENPPC_PSI_KEY`) gets you your own. The pages' addresses go to Google, so `--psi`
measures public pages only: it refuses `--allow-private`, a page that isn't on a public address, and an address
with a secret-looking value (`token=`, `session=` and the like) before anything is sent. The key travels in a
header, never in a URL, and is never shown.

**`--single`** checks one page instead of the whole site: the start page, and any `--render-url` pages. No sitemap,
no links followed, no links to other sites checked; the checks that need the whole site (titles shared between
pages, the sitemap, how a missing page answers) don't run, and the report says so. With `--render`, Web Vitals are
measured on a phone and a desktop. `--single --psi` is the quick check of one landing page.

| Flag | What it does |
| --- | --- |
| `--max-pages N`, `--max-time SECONDS` | Stop after this many pages or seconds (default: no limit; Ctrl-C keeps what was crawled) |
| `--max-per-pattern N` | Pages per URL pattern such as `/product/*` (default 500; 0 lifts the cap) |
| `--no-external`, `--fast`, `--allow-private` | As above |
| `--render` | The browser pass, as above |
| `--render-pages N`, `--vitals-pages N` | With `--render`: pages to render (default 5), and how many of them to measure Web Vitals on (default 1, the home page; 0 skips them; pages after the first get one load each) |
| `--runs N` | With `--render`: loads of the first measured page per device, 1 to 9 (default 3) |
| `--render-url URL` | With `--render`, also render this page, such as a thank-you page no link leads to, to see which events its tags send; with `--psi`, also measure it (a path or a full address on the site; repeat for more) |
| `--consent-selector CSS` | With `--render`, your consent banner's accept button, when it isn't one the check recognises |
| `--screenshots DIR` | With `--render`, save each rendered page as first loaded there; they show whatever the page shows, so nothing is saved without it |
| `--crux`, `--crux-key KEY` | Add real visitors' Web Vitals from Chrome's UX Report, with your own Google API key: `--crux-key KEY` (which turns `--crux` on), or `--crux` alone to read `OPENPPC_CRUX_KEY` and keep the key out of your shell history |
| `--psi`, `--psi-key KEY` | Measure with Google PageSpeed Insights, as above; `--psi-key KEY` (which turns `--psi` on), or `OPENPPC_PSI_KEY`, uses your own key instead of the shared quota |
| `--single` | Check the start page (and `--render-url` pages) only, not the whole site |
| `--config FILE` | A rule pack or project config: your own rules, suppressions and tag signatures (repeat for more; examples in [`examples/rulepacks`](examples/rulepacks)) |
| `--baseline FILE` | An earlier `--format json` result: report what's new and fixed, and fail only on new problems |
| `--fail-on high\|medium\|low` | Exit 2 when a finding is this severe or worse |
| `--format md\|json\|html\|sarif` | Markdown (default), data, one HTML page, or SARIF for code scanning |
| `--out FILE` | Write the report there instead of printing it |
| `--post-to URL` | Also POST the JSON result to a webhook (`https://`, or `http://` to this computer), naming only its host in the output |

API keys and webhook paths never appear in a report or a message, and secret-looking query values in the site's
URLs are masked. The JSON follows [`site-report.schema.json`](openppc_online/schemas/site-report.schema.json), and
rule packs [`site-config.schema.json`](openppc_online/schemas/site-config.schema.json).

Exit codes: 0 clean, 1 bad input, 2 a finding at `--fail-on` (with `--baseline`, a new one), 3 the report failed its
own number check (a bug: please report it), 4 with `--fail-on`, a scan too broken to judge (bot protection,
robots.txt failing, the start page not loading).

### `openppc-online fetch`

```
openppc-online fetch google 123-456-7890 --out exports
openppc-online fetch microsoft 149123456 --out exports --days 90
openppc-online fetch meta act_123456789 --out exports --conversion lead
```

Downloads one ad account's reports through the platform's API, with your own credentials, and writes them as the
files `openppc audit` reads. It prints the `openppc audit` command for each file, so the audit stays offline and
the same as for a file you exported yourself.

| Platform | Files | API |
| --- | --- | --- |
| `google` | `search_terms.csv` (Performance Max's search terms included), `keywords.csv`, `account.json`, `account_structure.json` | Google Ads API v25, SELECT queries only |
| `microsoft` | `search_terms.csv`, `keywords.csv`, `account.json` | Microsoft Advertising Reporting API v13 |
| `meta` | `account.json`, `account_structure.json` (Meta has no search terms or keywords) | Meta Graph API v25.0, GET only |

`account.json` compares the last `--days` full days (30 by default, at most 365) with as many days just before.
For Meta, `--conversion` names the action type that counts, such as `lead`; without it, the error lists the
account's action types with their counts.

The credentials come from environment variables, never from the command line, so they stay out of your shell's
history:

| Platform | Environment variables |
| --- | --- |
| `google` | `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`; `GOOGLE_ADS_LOGIN_CUSTOMER_ID` for an account under a manager account |
| `microsoft` | `MICROSOFT_ADS_DEVELOPER_TOKEN`, `MICROSOFT_ADS_CLIENT_ID`, `MICROSOFT_ADS_REFRESH_TOKEN`, `MICROSOFT_ADS_CUSTOMER_ID` (the manager account); `MICROSOFT_ADS_CLIENT_SECRET` for a web app registration only |
| `meta` | `META_ACCESS_TOKEN`, with the `ads_read` permission |

A missing one is named before anything connects. No credential reaches a file, the output or an error message;
an API's error is shown by its codes, never its free text.

Nothing is written until every report is in, and `--out` is checked first: a file of the same name already there
is replaced only with `--force`. When the API version a platform is called with is within 60 days of its sunset,
it says so after the files.

- **Hosts:** `google`: oauth2.googleapis.com and googleads.googleapis.com. `microsoft`: login.microsoftonline.com,
  reporting.api.bingads.microsoft.com, and the address each report's answer gives to download it from (https on a
  host name, once, without credentials). `meta`: graph.facebook.com. Nothing else, each call checked against its
  platform's list of methods and paths before it is made, and no redirect followed.
- **Read-only:** Google's searchStream only answers SELECT queries, Microsoft's Reporting service only builds
  reports, and Meta's calls are GETs. Nothing in the account changes.

Exit codes: 0 when the files are written, 1 for bad input, a missing credential or an API's refusal.

## The Tag Inspector extension

A browser extension for Chrome and Edge, in [`extension/`](extension/). Click it on a page to see the tags the page
loaded and fired, the events they sent, its consent banner and Consent Mode states, and its SEO basics. It uses
the same tag rules as `openppc-online site --render`, for one page you already have open.

It reads the page only when you click, asks for no host permissions, stores nothing and contacts no host. It is not
in a store yet: [extension/README.md](extension/README.md) says how to load it from the folder, and what it can't
see.

## The WordPress plugin

OpenPPC Site Check, in [`wordpress/openppc-site-check/`](wordpress/openppc-site-check/), adds five checks to
Tools > Site Health: search engines may index the site, the home page has the search basics, its HTML loads ad or
analytics tags, a page with tags has a consent banner, and robots.txt names a sitemap. It uses the same tag rules as
`openppc-online site`, and each check names the command that checks the same thing in a real browser.

It reads only its own home page and robots.txt, follows no redirect, stores nothing and adds no settings. It needs
WordPress 5.8 and PHP 7.4 or later. It is not in the WordPress plugin directory yet: zip the `openppc-site-check`
folder and upload it in Plugins > Add New > Upload Plugin.

## Install

Once it is released:

```
pip install openppc-online
```

It needs `openppc` 0.4, which it installs. In a clone of the repository:

```
pip install -e .
pip install -e companion
openppc-online app
```

A clone serves its own `web/` folder. The wheel carries a copy, made by `python tools/stage_companion_web.py`
before `python -m build companion`.

## Tests

```
pytest companion          # with Node.js 22 and PHP 7.4 or later installed, the extension's and plugin's tests too
pytest -m e2e companion   # in Chromium: pip install -e "companion[e2e]", then playwright install chromium
```

WordPress's coding standards for the plugin, with Composer: `composer install` and `vendor/bin/phpcs` in
`companion/wordpress/`.

The lab's calibration against Lighthouse 13 (hours; the scheduled `calibration` workflow runs it), offline on 17
local pages, OpenPPC's loads and Lighthouse's alternating in the same browser through the same guard:

```
cd companion/calibration && npm ci --ignore-scripts && cd ../tests
python -m calibration.harness --device mobile --runs 9 --lighthouse ../calibration --proxy-gate --simulate
```

The lab score says "uncalibrated" until this gate passes on both devices.

MIT license, like OpenPPC.

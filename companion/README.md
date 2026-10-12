# openppc-online

The optional companion to [OpenPPC](https://github.com/secondsteplabs/openppc), for the jobs that need more than a
browser tab or an offline command: each runs only when you run it.

OpenPPC itself never goes online. `pip install openppc` never installs this, and the `openppc` command never calls
it. This is a separate install with its own command, so that stays true without exceptions.

It is not released yet. Version 0.1.0 is its foundation, the app on your computer; 0.2.0 adds the website check,
`openppc-online site`, without a browser. Its browser pass (rendered pages, consent, tracking events, lab Web
Vitals) and downloads with your own API credentials (`openppc-online fetch`) are planned.

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

- **Hosts:** it answers only on 127.0.0.1. It connects to nothing itself; the page loads its Python runtime,
  libraries and fonts from cdn.jsdelivr.net, as on openppc.si.
- **Security:** it answers only to its own address, and the page gets a new token on each run, which every call to
  this server needs. [THREAT_MODEL.md](https://github.com/secondsteplabs/openppc/blob/main/companion/THREAT_MODEL.md)
  has the details.

Exit codes: 0 when it stops normally (Ctrl-C), 1 for bad input, as `openppc` uses them.

### `openppc-online site`

```
openppc-online site https://example.com
openppc-online site example.com --max-pages 200 --format html --out site.html
openppc-online site https://example.com --config openppc-site.json --baseline last.json --fail-on high
```

Crawls the site from the page you name and checks what a landing page needs before ads point at it: SEO, broken
links and redirects, indexing (robots.txt, sitemaps, canonicals, noindex), structured data, HTTPS and security
headers, which AI crawlers robots.txt lets in, and the tracking tags in the HTML. The report is scored, and every
number in it is traced, as in an `openppc` audit.

It reads robots.txt first and obeys it, Crawl-delay included, and asks two pages at a time, half a second apart
(`--fast` asks eight at a time with no pause, for your own site). It keeps no cookies and fills in no forms.

- **Hosts:** the site you name (and the host its start page moves to), the hosts it links to (one `HEAD` or `GET`
  per link, which `--no-external` skips), chromeuxreport.googleapis.com only with `--crux-key`, and the webhook's
  host only with `--post-to`. Nothing else.
- **Private addresses:** it refuses to connect to private, local, link-local and cloud-metadata addresses, checked
  on every connection and redirect. `--allow-private` opens private and local ones, to check localhost or a
  staging server on your network; link-local and metadata addresses never open.
- **This version runs no browser.** The checks that need one (the rendered page, consent banners, the tracking
  events a page sends, accessibility and lab Web Vitals) say so in the report instead of passing.

| Flag | What it does |
| --- | --- |
| `--max-pages N`, `--max-time SECONDS` | Stop after this many pages or seconds (default: no limit; Ctrl-C keeps what was crawled) |
| `--max-per-pattern N` | Pages per URL pattern such as `/product/*` (default 500; 0 lifts the cap) |
| `--no-external`, `--fast`, `--allow-private` | As above |
| `--crux-key [KEY]` | Add real visitors' Web Vitals from Chrome's UX Report, with your own Google API key; the flag alone reads `OPENPPC_CRUX_KEY` |
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
pytest companion
pytest -m e2e companion   # in Chromium: pip install -e "companion[e2e]", then playwright install chromium
```

MIT license, like OpenPPC.

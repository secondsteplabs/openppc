# Changelog: openppc-online

Semantic versioning, as in OpenPPC. Each release names the `openppc` versions it works with.

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

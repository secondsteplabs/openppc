# Changelog: openppc-online

Semantic versioning, as in OpenPPC. Each release names the `openppc` versions it works with.

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

The browser pass (rendered pages, consent, tracking events, accessibility and lab Web Vitals) is not in this
version; the report says which checks wait for it.

## Unreleased (0.1.0)

Needs `openppc` 0.4.

### Added

- **`openppc-online app`**: the OpenPPC app, served from this computer on 127.0.0.1 (port 8766, or any free one),
  with `--port` and `--no-browser`. Audits and checks run in the browser tab, as on openppc.si; the page says when
  openppc-online is serving it.
- [THREAT_MODEL.md](THREAT_MODEL.md): what the server guards and how, each defence with its test.

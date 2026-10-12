# Changelog

OpenPPC follows [semantic versioning](https://semver.org) for 0.x releases: a patch release (0.1.x) never changes
behaviour that [docs/compatibility.md](docs/compatibility.md) lists, except to fix a wrong number. A minor release
(0.x.0) may, and only with an entry under **Breaking** that says what changed and what to do.

## Unreleased (0.1.11)

### Fixed

- **French and Swiss exports read correctly.** Numbers written with a narrow no-break space or an apostrophe between
  the thousands (`1 254,40 €`, `1'234.56`), or with the currency after the number, read as €0.00 cost, so the audit
  found no waste. They now read as written. Indian grouping (`₹1,19,168.00`) and `Rs.` keep working.
- **An impossible waste threshold is refused.** `--min-cost nan`, `inf` or a negative amount, and text in the app or
  over MCP, now stop with a message instead of producing a report that flags nothing.
- **Windows doesn't crash on `₹` or `€`.** Printing a report to a console or pipe that uses a legacy code page
  stopped with `UnicodeEncodeError`; output is now UTF-8.
- **Grey text in the app is easier to read.** Hints such as "(optional)" and the line under each template were 3.1:1
  against white, under the 4.5:1 that WCAG AA asks for. The two grey tones are now a little darker and pass.

### Internal

- The test suite passes on Windows; CI runs on Windows and macOS as well as Linux, and lints with ruff.
- `.gitattributes` checks text out with LF, so `web/engine.js` builds byte for byte the same on every OS.
- `tools/build_web.py` bundles an explicit list of modules, and a test keeps that list complete.
- Golden files freeze every report, card, check result, MCP answer and page title (`tools/build_golden.py`), and a
  fixture corpus covers real-world export formats (`tools/build_fixtures.py`).
- Tests pin the promises word for word, check that the engine imports nothing that reaches the network, and run
  every command with the network switched off.
- Browser tests drive the app in Chromium (`pytest -m e2e tests/e2e`, their own CI job), including an accessibility
  scan on desktop and phone sizes. An accuracy test holds the checker to recall 0.95 and precision 0.99 on a
  labelled set of claims (0.964 and 1.000 today), and a performance test times a 20,000-row export.
- `GOVERNANCE.md` and `THIRD_PARTY_LICENSES.md`, as drafts for review. A test fails if the app loads something from
  its CDN that the license list does not name.

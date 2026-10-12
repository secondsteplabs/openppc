# Changelog

OpenPPC follows [semantic versioning](https://semver.org) for 0.x releases: a patch release (0.1.x) never changes
behaviour that [docs/compatibility.md](docs/compatibility.md) lists, except to fix a wrong number. A minor release
(0.x.0) may, and only with an entry under **Breaking** that says what changed and what to do.

## Unreleased (0.2.0)

### Breaking

- **A usage mistake exits 1, not 2.** A typo in a command, an unknown template or a flag that needs a value used to
  exit 2, the same code as "the check found wrong numbers", so a script could not tell them apart. It now exits 1,
  like any other bad input, and 2 means only that the check found problems (ADR-3). A script that treats 2 as "I
  typed the command wrong" should check for 1 instead.

### Added

- **Compare two periods from two exports.** `account-read` takes two exports of the same report, one per period
  (`openppc audit account-read july.csv june.csv`), and adds up each one. The file with the later dates is the
  current period. Two files that aren't two periods of one report (different reports, currencies or overlapping
  dates, or no dates) are refused with the reason. MCP: `prior_path` on `audit_account`, `prior_text` and
  `prior_name` on `audit_export`. In the app, add both files: account-read is picked, and if the two can't be
  compared, the line under Run says why. `check` traces a period-over-period report against the same two files.
  New sample: `examples/search_terms_acme_june.csv`.
- **Google Ads Editor exports (experimental).** `account-structure` reads a whole-account export from Google Ads
  Editor, in the app too. New sample: `examples/editor_acme.csv`.
- **Microsoft Advertising reports (experimental).** Search terms and keyword reports from Microsoft Advertising read
  like Google's; the report's header names the platform.
- **Two new account-structure checks.** Ads and keywords held back by policy (disapproved, or approved with limits),
  over every campaign type, and budget caps: campaigns limited by budget, with what Google may spend in a day (2x the
  daily budget) and a month (30.4x). A file that doesn't say which campaigns are limited gets "not in this file"
  instead of a pass.
- A Google Ads Editor export given to a report template says to use `account-structure`.

### Changed

- Account-structure reports have the two new checks, so their "N of M checks" counts change. The header names the
  currency only when the file has one.
- The header row of a report is looked for in the first 50 lines, up from 15.

### Fixed

- **A Search check no longer passes when there is nothing to judge.** With no live Search campaigns, the Search
  checks said "passed"; they now say "No live Search campaigns".
- **`check` traces an account-structure report's summary counts.** The live campaign, ad group, keyword and ad
  counts and "N of M checks" were reported as not in the data.
- **"Search Network with Display Select" campaigns count as Search.** Google's older campaign type was grouped with
  the automated campaigns, so the waste audit listed its terms with Performance Max instead of Search.

## Unreleased (0.1.13)

### Added

- **The app says what it is doing.** A long audit or check shows each step under the Run button (reading the file,
  running the audit, checking every number in the report). Stop still works at any step.
- **A greyed-out Run button says why.** The same line under it names what is missing: the export, the audit, a
  matching template, or the checker still loading.

### Fixed

- **The engine is downloaded once.** The app fetched `engine.js` a second time inside its worker; the page now hands
  the worker the copy it already has.
- **Accessibility in the app.** Every view has a main heading and its own page title, and an unknown page goes home.
  A skip link reaches the main content. Messages are announced from one live region and no longer cover each other on
  a phone. The template list moves with the arrow keys, the drop zone shows keyboard focus, wide tables scroll from
  the keyboard, and small text and links meet contrast and target-size minimums. Copy works on plain HTTP, where the
  clipboard API is missing. Results say "Checked at" a time, a file it can't read says "Can't read this file", and the
  form no longer flashes before the home page loads. axe now finds nothing on any view, the results or the branded
  PDF, on a desktop or a phone.
- **Accessibility on the website.** Phones get a menu with every link, the GitHub button has a name, footer headings
  are in order, code blocks in the install guide scroll from the keyboard, and faint text meets contrast. axe finds
  nothing on any page at either width. The app gets a preview card when its link is shared.

## Unreleased (0.1.12)

### Fixed

- **Excel's Windows "CSV" reads its euro signs and curly quotes.** A file saved as Windows-1252 was read as Latin-1,
  which turns `€` and `’` into control characters. Windows-1252 is now tried first, and UTF-16 files without a byte
  order mark are recognised too.
- **A name with a `|` in it passes its own number check.** A search term or campaign such as `Birch Lane | Search`
  split its table cell in two, so the report's check could not match the row and failed it.
- **Rows in two currencies are refused.** Their costs were added up as if they were one currency; the message now
  asks for one account or one currency per file.
- **Clearer refusals.** A folder given where a file belongs, an export with a header row but no rows (a date range
  with no traffic), an `--out` folder that doesn't exist, and JSON that isn't valid (now with its line and column)
  each get a sentence saying what to do. `check` reads an audit saved as Windows-1252 or UTF-16.

### Added

- **Reports say how the file was read.** A line under the title says when numbers were read with decimal commas, or
  when the file was not Unicode, so accented names are worth a look.
- **"Report this file" in the app.** Under a file it can't read, the app offers a GitHub issue filled in with the
  message and the file's column names only. It shows exactly what will be sent; nothing leaves the page unless you
  submit the issue on GitHub. Two issue forms come with it: a file OpenPPC can't read, and a finding that looks wrong.
- `openppc check --data a.csv b.csv` takes several exports after one flag (repeating `--data` still works).
- `--debug`, before or after the command, prints the full traceback when OpenPPC crashes.
- The install guide lists the number formats and encodings it reads.

### Changed

- **A crash exits 3 in one line.** An unexpected error printed a Python traceback and exited 1, the code for bad
  input. It now prints one line that says it is a bug and where to report it, and exits 3, OpenPPC's code for
  "OpenPPC got it wrong". Bad input still exits 1.

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

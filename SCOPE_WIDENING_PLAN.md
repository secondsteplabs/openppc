# OpenPPC: widening scope with what `openppc-2-test` offers (v9, in execution)

Status: final after eight critique rounds (appendix B), now being executed (appendix C). v7 brought the network half
of the fork into scope at the owner's request: API downloads, the local app, the website crawler, the Chrome
extension and the WordPress plugin. v8 added what the fork executed poorly (section 3b). v9 corrects four points
that execution proved wrong. Owner decisions are marked **[Owner]**. Every claim about "0.1.10 today" was re-checked
against the code and the CLI on Oct 11, 2026 (appendix A).

**Where things stand:** Phases 0a, 0b (engineering half), 1, 2, 3, 4a, 4b, 5 and 6 are committed locally on
`stagging` (appendix C has each commit). Nothing has been pushed, released or deployed; that, the version bumps,
and the deployed-app checks are the owner's. Left: 4c (hosted connector, waits on `chatgpt-app`), Phases 7–9 of
the companion, and the open owner questions 7, 9 and 10.

## 1. Summary

`openppc-2-test` (the fork) is OpenPPC 0.1.4 plus about 300 files of new work. The current app is 0.1.10, with a
newer checker, a streaming reader, the Stop button and the articles, none of which the fork has. So we **port feature
by feature onto 0.1.10, and never merge**. We also never copy fork files wholesale, because the fork's `site.css`,
`trace.py`, `checkfacts.py` and waste template are older than ours.

About half of the fork keeps OpenPPC's promise ("read-only, never connects to your account, makes no network calls,
every number traced") and fits PPC freelancers and agencies. That half is worth taking:

- reading real exports correctly: French and Swiss numbers, Windows encodings, and notes in the report on how a file
  was read
- Google Ads Editor import, a two-period comparison from two exports, and policy and budget checks
- Microsoft Advertising exports, and later Meta Ads Manager exports, which the current roadmap already lists
- HTML, JSON and SARIF output, app downloads, and a call to action in the branded PDF
- a GitHub Action, Docker, and a hardened MCP connector for the "coming soon" hosted connector
- app accessibility, plus test and CI depth

The other half needs the network or an ad-account login: API downloads (`fetch`), the local credentials app, the
website crawler, the Chrome extension and the WordPress plugin. **It is in scope too, as an optional companion**
(ADR-7) that never weakens what OpenPPC promises today:

- It is a **separate install with its own command**, `openppc-online` (working name, **[Owner]**). Installing
  `openppc` never pulls it in, and the `openppc` command never goes online, with or without the companion installed.
  So "makes no network calls" stays literally true of `openppc`, and "never connects to your account" stays true of
  OpenPPC and its app.
- **The app at openppc.si doesn't change.** Its security policy and its build stay the same, and the companion's
  local views ship only in the companion's own copy of the app, served from 127.0.0.1.
- **The companion keeps promises of its own:** it is off unless you install and run it, read-only, uses your own
  credentials, and contacts only the hosts it declares. Tests enforce each one, just as they enforce the core's.
- **It is pitched where it fits PPC.** The crawler leads as the "landing page and tracking check" (what an ad click
  lands on: tags, consent, conversion events, broken pages), not as a general SEO tool. API downloads are for
  agencies that already have API access. Neither appears in the hero.

The order is the landing-page and tracking check first (no credentials, so the widest audience and the lowest risk),
then API downloads, then the extension and the WordPress plugin, which reuse the crawler's tag list.

The first release is a hotfix in week 1. 0.1.10 reads a French export as **€0.00 total cost**, so the waste audit
says there is nothing to cut while the real waste is €767.60, and the report's self-check still passes. In a product
whose promise is "every number traced", that is a P0.

Overall:
- **Core track (Phases 0a–5):** eight `openppc` releases (0.1.11 to 0.1.13, 0.2.0, three Phase 4 slices from 0.3.0,
  and Meta in 0.3.x), about 14 weeks.
- **Companion track (Phases 6–9):** four `openppc-online` releases, about 11 weeks plus store review time.

That is about 25 weeks for one senior engineer, or about 17 weeks with two, since the companion track can start once
Phase 4b ships. None of the releases changes the hero, the promises, the app's navigation, the existing routes or the
existing pages' titles.

## 2. What must not change

These stay exactly as they are, and section 4 turns each one into a test:

- **Positioning:** "Read-only Google Ads audits where every number is traced back to your own export. For PPC
  freelancers and agencies…" Google Ads stays the headline everywhere. Other platforms are named only in docs, the FAQ
  and the changelog.
- **Promises:** "never connects to your account", "makes no network calls", "nothing is uploaded", "no API keys", and
  the README's "Configuration: None." They describe the `openppc` package and command, the app at openppc.si, and
  the MCP server, and they stay literally true of all four. The companion is described separately, under its own
  name, and never in sentences that carry these promises.
- **Product surface:** the two jobs (Audit, Check), the app's navigation and hash routes (`#home`, `#check`,
  `#audit`, `#templates`, `#rules`, `#branded`), the branded PDF flow and its page-by-page number check, the Stop button, and the
  existing CLI flags and MCP tool signatures.
- **Site and SEO:** the hero, the H1 and the titles, meta descriptions and canonicals of every existing page (the SEO
  baseline from #29), plus the articles and their charts. New pages are additive. The home page gains at most one
  card (Phase 4b) and one "Optional companion" section below the existing ones (Phase 7, **[Owner]** approves the
  copy), which says plainly that the companion is a separate install that goes online.
- **Numbers users already see:** any change to a sample's report is a reviewed bug fix, never a side effect.

## 3. Inventory: every fork offering and the verdict

Fit: **A** = keeps every promise and matters to PPC freelancers and agencies; **B** = keeps the promises, but low
value or high cost; **C** = goes online, so it is in scope only inside the optional companion (ADR-7); **X** = breaks
a current promise as the fork built it, so it is not ported.

| Offering (fork location) | Fit | Verdict | Phase |
|---|---|---|---|
| French and Swiss thousands separators: narrow and no-break spaces, apostrophe (`ingest/google_ads_csv.py`) | A | Port only what's missing; 0.1.10 already tells `1.234,56` from `1,234.56` | **0a** |
| `--min-cost` validation (`templates/_common.py: threshold`); 0.1.10 accepts `nan` and `-5` and prints "$nan" | A | Port | **0a** |
| UTF-8 console output on Windows (0.1.10 crashes printing `₹`) | A | New work, informed by the fork | **0a** |
| cp1252 in place of Latin-1 as the last-resort encoding; UTF-16 without a BOM | A | Port | 1 |
| Reading notes in the report header: "read with decimal commas", "not in Unicode, read as Western European" (`Report.warnings`) | A | Port. Keep 0.1.10's refusal of negative costs (ADR-4); the fork turned it into a warning | 1 |
| Clearer refusals: a folder given, a missing `--out` folder, a header-only export, a bad JSON naming the file, audit file encodings (C2–C8) | A | Port | 1 |
| Escaped `\|` in table cells (B2), `-$50.00` money format (B3) | A | Port | 1 |
| `--debug`, and exit 3 on an internal crash | A | Port (ADR-3, additive) | 1 |
| argparse usage errors exit 1 instead of 2 | A | Port (ADR-3, breaking, so in a minor version) | 3 |
| `check --data a.csv b.csv`: several files after one flag (`action="extend", nargs="+"`); `--data a --data b` keeps working | A | Port | 1 |
| Contributor docs for lint, types and optional-extra tests (`CONTRIBUTING.md`) | A | Port the parts that match what Phase 0b adds | 0b |
| "Wrong finding" issue template (`.github/ISSUE_TEMPLATE/wrong_finding.yml`) | A | Adapt to audits and checks | 1 |
| Fixture corpus, property, accuracy and performance tests; Windows and macOS CI; ruff (`tools/build_fixtures.py`, `tests/test_{properties,accuracy,performance,fixtures}.py`) | A | Port, adapting each test file | 0b |
| Typed template contract (`Template` protocol), mypy on the template surface, `py.typed` | A | Port mypy and the protocol; ship `py.typed` only once ADR-2 names the stable API | 0b / 4b |
| App progress by step: reading, auditing, checking (`run_loaded(progress=...)`, `compose.js` STEPS) | A | Port onto 0.1.10's worker | 2 |
| App accessibility and UX fixes U1–U23; site fixes W1–W5 (`project-issues.md`) | A | Port the ones that still apply | 2 |
| `web/app.js` split into ES modules with `@ts-check`, `types/`, `tsconfig` (`web/js/*`) | A | **Defer** (trigger in section 7): the fork split an older `app.js` that has no Stop button and no streaming | — |
| Google Ads Editor export for `account-structure` (`ingest/editor.py`) | A | Port, fixing the fork's two bugs | 3 |
| Two exports, one per period, for `account-read` (`templates/account_read.py: load`) | A | Port | 3 |
| Policy check (`policy-disapproved`), and a live budget check (`all-budget-spend-caps`) | A | Port, run only when the input carries the data | 3 |
| Microsoft Advertising search-term and keyword CSVs | A | Port; fix "Search & content" campaigns; label experimental | 3 |
| `--format html` for `audit` and `check`; web downloads as .md, .html and .json; branded PDF call to action | A | Port | 4a |
| `--format json` / `sarif`, JSON Schemas, `format_version` (`formats.py`, `schemas/audit-report`, `schemas/check-report`) | A | Port; the `site-*` schemas come with the crawler | 4b |
| GitHub Action (`action.yml`); Dockerfile with CLI and MCP targets; Dependabot for the Docker image | A | Port; the `render` target comes with the crawler, in the companion's image | 4b |
| "Command line and CI" docs page (`site/pages/docs/command-line.html`) | A | Rewrite on today's site; never copy fork site files | 4b |
| MCP limits: one process per call, timeout, workers, rate limit, bearer token, `/healthz`, request size, counts-only logs (`mcp_limits.py`) | A | Port, after `origin/chatgpt-app` lands | 4c |
| Meta Ads Manager CSV for `account-read` (totals only) | A | Port, experimental, docs-only (the current roadmap lists Meta) | 5 |
| `GOVERNANCE.md`, `THIRD_PARTY_LICENSES.md` | A | Port, with pledges matching today's README word for word | 0b |
| `TRADEMARK.md` | B | **[Owner]** a legal and brand call | — |
| SPDX headers on every file | B | Skip: touches every file and rebuilds the bundle, for no user value | — |
| Template plugins (entry points) | B | Park; plugins aren't covered by the no-network promise | parked |
| Local server (`localapp.py`): 127.0.0.1 only, Host check against DNS rebinding, a per-run token in the page, a job API, uploads; the app's local views (`web/js/local.js`, `connect.js`, `site-view.js`) | C | In scope as `openppc-online app`. Ship a packaged web build in the companion's wheel, so it works without a clone (the fork needs one) | 6 |
| `openppc site` crawler (`siteaudit/`): polite crawl, private and metadata address refusal, SEO, links, indexing, structured data, HTTPS and security headers, AI crawlers, scoring, inconclusive exit 4 | C | In scope as `openppc-online site`, pitched as the landing-page and tracking check | 7 |
| Crawler `--render` (Playwright): tags before and after consent, the events each tag sent, Consent Mode, axe accessibility, lab Web Vitals, screenshots; the Docker `render` target | C | In scope, as the companion's `render` extra and image | 7 |
| Crawler `--crux-key` (field Web Vitals), `--post-to` webhook, `--baseline`, `--fail-on`, SARIF; rule packs (`examples/rulepacks/`) and `--config`; `site-*` schemas | C | In scope. `--post-to` takes https only (the fork also accepts `http://`) | 7 |
| About 55 `site-*` rulebook rows | C | In scope, each with a trace test, under their own category | 7 |
| `openppc fetch` through the Google Ads, Microsoft Advertising and Meta APIs, writing the files the templates read | C | In scope as `openppc-online fetch`, with a read-only call allowlist and your own credentials | 8 |
| Credentials entered in the local app, kept in memory or the system keychain (`keys` extra) | C | In scope, with the secret-leak tests in section 4 | 8 |
| Chrome and Edge Tag Inspector extension (`extension/`) | C | In scope. Narrow its permissions first: the fork asks for `<all_urls>` at install | 9 |
| WordPress Site Health plugin (`wordpress/openppc-site-check/`) | C | In scope. Run it in PHP CI first: the fork never ran it | 9 |
| Fork copy that rewrites today's promises: "No login to your account needed", "unless you run `openppc fetch`", and fetch and site wording inside the hero and the "Why" paragraph | X | **Do not port.** The companion is described in its own section and pages | — |
| `qa_artifacts/`, `project-issues.md`, review and strategy docs | — | Reference only | — |

Already in 0.1.10, so there is nothing to port: per-term aggregation across ad groups, German and Indian number
formats, UTF-16 with a BOM, Performance Max search terms, the Stop button, the templates page's "Run on my export"
button, refusals of German headers and of mixed number formats, and exit codes 0, 1, 2 and 3 for the common paths.

## 3b. Where the fork falls short, and what we do instead

Porting a feature means porting its idea, not its execution. Each row below is a weakness found in the fork's code,
tests or process, with evidence, and the better way this plan builds the same thing.

| # | Area | What the fork did | Why that falls short | What we do instead | Phase |
|---|---|---|---|---|---|
| F1 | Core freshness | Built every feature on 0.1.4's reader, tracer, `checkfacts` and waste template | 0.1.10's versions are newer and faster. For example, the fork's `totals()` is the slower pure-Python sum that 0.1.10 replaced | Never port a fork version of a shared helper; re-implement the feature on today's code | all |
| F2 | Bundle safety | `build_web.py` uses a denylist | Network wiring leaked into the browser bundle: `engine.js` grew to 367 KB, with 6 `urllib` references | Build from an allowlist of modules, under a size budget | 0b |
| F3 | Network boundary | Put fetch, the crawler and the local server inside the `openppc` package, gated by extras | Extras gate dependencies, not code; the promises had to be rewritten with "unless you run…" | A separate companion with its own command (ADR-7) | 6 |
| F4 | Promise copy | Rewrote the hero and "Why" around fetch and site ("No login to your account needed") | It dilutes the positioning wedge and breaks pinned SEO copy | Promises pinned by tests; the companion gets its own section and pages | 0b, 7 |
| F5 | Editor budgets | `float(str(value).replace(",", ""))` (`ingest/account.py:83`) | A European `50,00` becomes 5,000: a silent wrong number | Reuse the reader's decimal-mark tally, with a property test across locales | 3 |
| F6 | Budget-limited check | Reports "No campaign limited by budget" when the file can't say (`account_structure.py:425-427`) | A false "passed" | A third state: "can't tell from this file", naming the file that can | 3 |
| F7 | Negative costs | Downgraded the refusal to a warning (`google_ads_csv.py:398-400`) | A refund row can quietly shrink waste totals | Keep the refusal (ADR-4); read `-$50.00` only in text, for changes between periods | 1 |
| F8 | Mixed currencies | Left as "Not changed"; the currency comes from the first row | USD and EUR rows are summed as one currency, exit 0 | Refuse a file with more than one currency, naming both | 1 |
| F9 | Microsoft campaign types | `_automated` treats any type other than "search" as automated | "Search & content" waste lands in the Performance Max section | An explicit campaign-type map per platform, with a fixture for each type | 3 |
| F10 | Two HTML renderers | `formats.py` converts markdown to HTML in Python; `web/js/markdown.js` does it again in JavaScript | The CLI's .html and the app's .html can disagree | One Python renderer, called by the app through the worker (ADR-5), with a test that the numbers match | 4a |
| F11 | Module split | Split an older `app.js` with no Stop button and no streaming | Merging it would bring back fixed bugs | Split today's file, behind characterization tests (section 7) | 6 |
| F12 | Local app distribution | `openppc app` serves `web/` from a git clone | It doesn't work after `pip install`; PyPI users get an error | Ship the local web build inside the companion's wheel | 6 |
| F13 | Webhook | `--post-to` accepts `http://` and any address (`cli.py:203-209, 234`) | It sends a whole report unencrypted, possibly to an internal address | https only (http only to localhost), the crawler's address guard applied to it, and the report names the destination | 7 |
| F14 | Extension permissions | `<all_urls>`, `webRequest` and `scripting` at install | Store review friction, and more access than a one-page check needs | `activeTab`, plus per-site optional permissions asked on click | 9 |
| F15 | WordPress plugin | Shipped without ever running (no PHP in the fork's QA) | Unknown behaviour on real WordPress sites | PHP CI on 7.4 and 8.3, the WordPress test suite, PHPCS and Plugin Check before submission | 9 |
| F16 | API client tests | 4 (Google), 4 (Microsoft), 7 (Meta) | Pagination, quota and error paths are untested; writes aren't provably absent | Recorded contract tests, a read-only call allowlist, and a live smoke workflow | 8 |
| F17 | API versions | A comment: "bump it with each OpenPPC release" | Nothing enforces it, and a sunset breaks fetch for everyone at once | A sunset calendar in code; CI fails 60 days early | 8 |
| F18 | MCP limits | Rate limits held in one process's memory; the size cap checks the declared `Content-Length` (`mcp_limits.py:179-242`) | Limits reset on restart and don't add up across instances; chunked bodies need their own check | Cap streamed bytes as well, run one instance, and put a rate limit at the edge in front of it | 4c |
| F19 | Crawler QA | 29 of 31 matrix cases behaved; the QA scratch scripts were committed, then excluded from lint | Two known misses, and QA not repeatable in CI | The QA site becomes CI fixtures on a local server; fix the two misses | 7 |
| F20 | Stop on huge files | U24: "testing Stop still needs a 100k-row fixture" | The feature most likely to fail on a real export is untested | Generate a 100k-row fixture in `build_fixtures.py`, and add a Stop test to the characterization suite | 0b |
| F21 | SPDX churn | Added a header to every file | It rebuilds the bundle and touches every line of history, for no user value | Skip it; `LICENSE` and `THIRD_PARTY_LICENSES.md` are enough | — |
| F22 | Windows portability | Added `.gitattributes`, but the QA ran mostly on one setup | Today's suite fails 4 tests on Windows: 3 read files without `encoding="utf-8"`, and the bundle embeds CRLF | Fix both in Phase 0a, and add the three-OS CI in 0b | 0a, 0b |
| F23 | Hosted connector domain | `project-issues.md` B10–B11 name `mcp.openppc.in` | Today's README markets `mcp.openppc.si` | Use `.si` everywhere, and add a docs link check | 4c |

## 4. Non-negotiables, enforced by tests

Each of these is a test that fails the build. Items 1–7 are in place by the end of Phase 0b, and items 8–12 by the
end of Phase 6; the hotfix uses the reduced
form described in Phase 0a.

1. **No network in the core.** An AST import scan keeps `socket`, `ssl`, `http.client`, `urllib.request` and asyncio
   streams out of `openppc/`. The one exception is the MCP `--http` transport, which is allowlisted by module and
   recorded in ADR-2.
2. **The CLI runs offline.** Every template, and `check`, runs on the samples with `socket.socket` patched to raise.
3. **The web bundle comes from an allowlist.** `tools/build_web.py` lists its modules by name. Today it globs
   `openppc/**/*.py`, and the fork shows why that's unsafe: its *denylist* still ships `mcp_limits.py` and the CLI's
   `fetch` and `site` wiring to the browser (6 `urllib` references in its `engine.js`). `engine.js` is 324 KB today.
   Its growth budget is +15%, spent per phase (section 6), and every increase is a reviewed change. The build is
   byte-identical on every OS. Today it isn't: with `core.autocrlf=true` and no `.gitattributes`, a Windows build
   embeds the samples with CRLF line endings and changes `engine.js` with no code change. `.gitattributes` checks
   text out with LF and keeps CSVs byte for byte, and CI builds on three operating systems.
4. **Promises and SEO stay word for word.** A test pins the phrases in section 2 in `README.md`,
   `site/pages/index.html`, `site/layout.html`, `site/pages/docs/install.html` and `web/index.html`. It also pins the
   title, meta description, canonical and H1 of every existing page. The CSP tests stay.
5. **Existing behaviour is frozen by golden files.** These are captured for the samples and for the fork fixtures
   that 0.1.10 already reads:
   - every template's markdown
   - the cards and the client JSON
   - `check` verdicts
   - MCP tool outputs
   Any diff is a reviewed, intentional change.
6. **Accuracy and speed have numeric gates.** The baselines are 0.1.10's checker recall and precision on the labeled
   claims (the fork's method, run on current code) and 0.1.10's time on the big-export benchmark. No release falls
   below either.
7. **Every new figure is a registered fact.** Every new rule is a row in `rulebook/rules.csv` with a trace test.

These are added in Phase 6, for the companion:

8. **The boundary holds.** `openppc` never imports the companion. The `openppc` command has no network
   subcommands. The openppc.si build contains none of the local-mode modules, and its CSP is unchanged. The hosted
   MCP connector exposes no fetch or crawl tool, since that would mean SSRF and credentials on a shared server.
9. **Each command contacts only its declared hosts.** Tests patch the socket layer and record every connection:
   - `fetch`: the platform's API and token hosts
   - `site`: the named site, one check per external link, CrUX only with a key, and the `--post-to` address only
     when given
   - `app`: 127.0.0.1, plus whatever the command it runs is allowed
10. **API access is read-only by construction.** Each platform has an allowlist of HTTP methods and URL patterns:
    - Google: the token endpoint and `googleAds:searchStream`
    - Microsoft: report submit, poll and download
    - Meta: `GET` only

    Any other call fails the test. Google's `adwords` scope and Microsoft's `msads.manage` scope permit writes; the
    docs say so, and this test is the proof that the code never writes.
11. **Secrets never leak.** A sentinel credential is run through every command and every local-app endpoint. It
    must never appear in output, logs, reports, downloaded files, error messages or the page. Credentials are kept
    only in memory or the system keychain.
12. **The crawler stays off private networks.** It never fetches private or link-local addresses unless
    `--allow-private` is given, and never cloud metadata addresses. The same holds through redirects, DNS rebinding,
    IPv4-mapped and 6to4 addresses, and in the rendering browser. The fork's tests are ported for each case.

## 5. Architecture decisions (written in Phase 0b)

- **ADR-1: port, don't merge.** The histories share no recent commits, and the fork's core is older. Each feature is
  re-implemented on 0.1.10. Each fork test file is adapted, kept or dropped on its own, never bulk-copied.
- **ADR-2: the network boundary.** The `openppc` distribution stays offline. Anything that fetches from the network
  ships in the companion (ADR-7), which depends on `openppc`, never the reverse. The stable engine API it may use is
  `facts.FactBook`, `engine.trace.trace`, `ingest.load_report`, `templates.run_template` and the `Template` protocol.
  `py.typed` ships at the same time as this API is declared, not before.
- **ADR-3: exit codes.** 0.1.10 already returns 0 (clean), 1 (bad input), 2 (untraced numbers) and 3 (the audit
  failed its own check). Two things change, in two releases:
  - an unexpected exception exits 3 with a one-line message, and `--debug` prints the traceback. Today a crash is
    already non-zero, so this is additive and ships in 0.1.12;
  - argparse usage errors exit 1 instead of 2, so 2 always means "untraced numbers". This breaks scripts that treat
    a usage error as 2, so under the 0.x policy it waits for the minor version 0.2.0, with a "Breaking" changelog
    entry.
- **ADR-4: negative inputs stay refused.** 0.1.10 refuses a negative cost, click or impression count
  (`google_ads_csv.py:244-248`). The fork turns a negative cost into a warning; we keep the refusal. `-$50.00` still
  matters, for changes between periods.
- **ADR-5: one HTML renderer.** `--format html` and the app's .html download both render the *traced* markdown with
  one deterministic converter. That converter is the Python one, and the app calls it through the worker. The fork
  keeps a second, JavaScript copy, which can drift (F10). Tests check that:
  - the numbers in the HTML text equal the numbers in the markdown
  - the output has no `<script>` and no external URL, so it opens offline under any CSP

  The branded PDF stays a separate, browser-only layout, which already re-checks its own pages.
- **ADR-6: platform scope.** Google Ads is the headline. Microsoft Advertising (Phase 3) and Meta Ads Manager (Phase
  5) are export readers labelled experimental. They are named in docs, the FAQ and the changelog only, and every
  report says which platform it read.
- **ADR-7: the companion.** The network features ship as `openppc-online` (working name):
  - **Code:** a second distribution in this repository (`companion/`, with its own `pyproject.toml`) pinned to a
    compatible `openppc` (`>=0.4,<0.5`), released from the same CI.
  - **Command:** its own, `openppc-online` with `fetch`, `site` and `app`, never subcommands of `openppc`. Typing
    `openppc fetch` prints where the command now lives and exits 1. That is a string in the core, not code.
  - **App:** `openppc-online app` serves a web build packaged in its wheel. It is the hosted app plus the local
    views (Site, and the Download panel), and its CSP adds only `connect-src 'self'`.
  - **Extension and plugin:** they live in `extension/` and `wordpress/`, ship through the Chrome Web Store, Edge
    Add-ons and WordPress.org, and share one tag-signature file with the crawler.
  - **Docker:** a companion image with the `render` target (Chromium), separate from the core images.

  The alternative, putting the code in `openppc` behind optional extras as the fork did, is rejected. Extras gate
  dependencies, not code, so `pip install openppc` would ship network code and the promises would need asterisks.
- **ADR-8: credentials.** Use the variable names the platforms' own client libraries read. In the local app,
  credentials live in memory or the system keychain, never in a file, and the page can never read them back.
  Developer tokens and OAuth clients are the user's own; OpenPPC never ships or proxies one.

## 6. Phases

Estimates assume one senior engineer full-time, plus the owner for decisions, copy and design-partner outreach.
"Bundle" is the share of the `engine.js` growth budget each phase may spend.

### Phase 0a: Hotfix the silent wrong number (0.1.11, week 1)

What users get: a French or Swiss export reads correctly, an impossible threshold is refused, and Windows doesn't
crash on `₹`.

1. Add the narrow no-break space (U+202F), the no-break space (U+00A0) and the apostrophe to 0.1.10's
   thousands-separator tally. Add a fixture test: the French export's total cost is €4,347.25, not €0.00.
2. Port `threshold()`, so `--min-cost` refuses `nan`, `inf`, negatives and text (in the CLI, the app and MCP).
3. Reconfigure stdout and stderr to UTF-8 on Windows. Add a test that prints `₹` and `€`.
4. **A green suite on Windows first (F22):** 3 tests read files without `encoding="utf-8"`, and `tools/build_web.py`
   embeds the working copy's CRLF line endings, so the freshness test fails on any Windows checkout. Fix both: read as
   UTF-8, and add `.gitattributes` (`* text=auto eol=lf`, `*.csv -text`). Normalizing in the build instead would be
   wrong: the sample CSVs carry CRLF rows on purpose, and their SHA-256 is printed in reports.
5. The reduced golden check: run every sample and every fork fixture before and after, and diff the reports. Only the
   French fixture and the `--min-cost` messages may change.
6. Release, then check the deployed app on desktop and mobile in a real logged-out browser.

**Bundle:** about 1%. **Launch:** a changelog note and a reply in any thread that reported it. No campaign.

### Phase 0b: Decide and freeze (2 weeks; no release)

1. Write ADR-1 to ADR-6 in `docs/adr/`.
2. Add `CHANGELOG.md`, with the 0.x semver policy: a minor version may break, and only with a documented "Breaking"
   entry.
3. Add `docs/compatibility.md`, a matrix of:
   - exit codes, CLI flags and MCP tool signatures
   - hash routes and JSON keys
   - negative-input handling
   - the report wording that site copy quotes
4. Add the golden-file harness and the fitness functions (section 4, items 1–5).
5. Port `tools/build_fixtures.py` and the accuracy and performance tests, and record the 0.1.10 baselines (item 6).
6. **App characterization tests** (moved here from Phase 2, because Phase 1 already changes the app): Playwright
   tests in `tests/e2e/` cover:
   - the sample audit and check
   - an upload for each template
   - copying and downloading negatives
   - the branded PDF gate
   - Stop, including on a generated 100,000-row export (F20), and every hash route
7. CI:
   - add Windows and macOS rows
   - add ruff (lint only). Start with correctness rules (`E9`, `F`), because the fork's full rule set flags 158
     findings on 0.1.10, which would be a cosmetic rewrite in a freeze phase. Widen one rule family per release.
     mypy on the template surface comes with ADR-2's typed API.
   - add `.gitattributes`
   - update `CONTRIBUTING.md` with how to run each of these locally
8. Port `GOVERNANCE.md`, with pledges matching today's README exactly, and `THIRD_PARTY_LICENSES.md`. Scope pledges
   3 ("no hidden phone-home") and 4 ("read-only, never connects to an ad account") to the `openppc` package and
   command, the app at openppc.si, and the MCP server. Add the companion's own pledge: off unless you install and
   run it, read-only, your own credentials, only declared hosts. Written this way from the start, the companion needs
   no pledge amendment later. Add axe-core (MPL-2.0) and Playwright to the third-party list.
9. **[Owner] Start recruiting 5–10 design partners now** (freelancers or agencies), so real Editor, Microsoft and
   Meta exports arrive before Phase 3 needs them.
10. **[Owner]** Decide `origin/chatgpt-app`, which has a ChatGPT app phase 0 (`chatgpt-plugin/`, a results view in
    `openppc/ui/results.html`) and `--allow-host`. The recommendation is to finish it in Phase 4c.

**Done when** every new test is green on 0.1.11 unchanged, and CI is green on three operating systems.

### Phase 1: "Works on your real export" (0.1.12, 1.5 weeks)

What users get: files that 0.1.11 misreads or crashes on now read correctly, or are refused with a reason, and the
report says how it read the file.

1. **cp1252 instead of Latin-1** as the last-resort encoding (Latin-1 turns `€` and curly quotes into control
   characters), and UTF-16 without a BOM.
2. **Reading notes in the report header:** "read with decimal commas", and "not in Unicode, read as Western European:
   check accented names". These are text, not figures, so the checker is unaffected; the golden diff confirms it.
3. **Mixed currencies refused (B4).** This is new work, because the fork never fixed it: today the currency comes from
   the first row (`google_ads_csv.py:249`).
4. **Escaped `\|` in table cells (B2).** A search term containing `|` makes the report fail its own check.
5. **`-$50.00` (B3).** The tracer reads a leading minus.
6. **Clearer refusals (C2–C8),** and `check` reads audits saved in UTF-16 or cp1252 (C4).
7. **ADR-3, additive part:** `--debug`, and exit 3 with a one-line message on a crash. Update the compatibility
   matrix. (Usage errors move to exit 1 in 0.2.0.)
8. **`check --data a.csv b.csv`,** keeping `--data a.csv --data b.csv` working.
9. **"Report this file" link.** When a file can't be read, the app shows a link that opens a prefilled GitHub issue,
   after the user sees exactly what will be sent:
   - only the column names, never Google's title and date lines (they can carry the account name) and never a row
   - nothing at all is sent by the app: the user's own click opens github.com, so the CSP doesn't change and
     "nothing is uploaded" stays true
   - the URL stays under GitHub's length limit; a longer header is cut, and the preview says so

   Add the wrong-finding issue template.
10. **Docs:** add a number-formats and encodings section to the export page, and "Which formats does it read?" to the
   FAQ.

Each fix is its own PR, with a failing test first. **Bundle:** about 2%. **Launch:** "OpenPPC now reads your export
the way Google wrote it", showing the French and rupee cases.

### Phase 2: Accessible app (0.1.13, 1 week)

What users get: an app that works with a keyboard, a screen reader and a phone, and that shows which step it is on.

1. **Step progress** ("Reading your files", "Running the audit", "Checking every number"), through a `progress`
   callback on `run_template_book`, in 0.1.10's worker. Stop keeps working, and the Phase 0b characterization tests
   stay green.
2. **Load the bundle once (B9).** Today the page *and* the worker both load `engine.js`; the worker should hand the
   samples over.
3. **Accessibility fixes,** in small PRs, keeping only those confirmed to still apply in `web/app.js`:
   - toasts in one polite live region (U1–U3)
   - focus rings, contrast and target sizes (U4, U5, U7, U8)
   - `<main>`, a skip link and an `<h1>` (U6)
   - scrollable tables (U9), and a hint on why Run is disabled (U10)
   - the radio keyboard pattern (U11), page titles (U12) and "Checked at" (U13)
   - "Can't read this file" (U18), a copy fallback (U19), heading order (U20), and `#compose` hidden (U23)
4. **Website:** the mobile menu (W1), the GitHub `aria-label` (W2), footer headings (W3), focusable code blocks (W4)
   and Open Graph tags on `/app/` (W5). The titles, descriptions and canonicals stay pinned.
5. **Verification:** axe on every app view and site page at 1440 px and 390 px. A real logged-out browser checks the
   deployed site on desktop and mobile.

**Bundle:** about 0%. **Launch:** an accessibility note in the changelog.

### Phase 3: "Every template runs on files Google gives you" (0.2.0, 3.5 weeks)

What users get: `account-structure` and `account-read` stop needing hand-made JSON, which today makes them unusable
for most people. They also work through MCP and the connector.

1. **Google Ads Editor import** for `account-structure`. It reads UTF-16 tab-separated files and uses names in place
   of ids. Fix the fork's two bugs while porting:
   - A European budget such as `50,00` is read as 5,000: the fork strips every comma
     (`ingest/account.py:83`, `float(str(value).replace(",", ""))`). Use the reader's decimal-mark tally instead,
     with a property test: a budget written in any supported locale reads as the same amount.
   - The budget check reports "No campaign limited by budget" (`account_structure.py:425-427` in the fork) when an
     Editor file can't say. It must report "can't tell from this file".
2. **Policy check (`policy-disapproved`).** It runs only when the input carries an approval status. Otherwise it says
   which file it needs. `all-budget-spend-caps` goes live on the same terms. Add rulebook rows and trace tests.
   The fork adds approval statuses to the Acme sample (`examples/account_structure_acme.json`), so that sample's
   report changes: a reviewed golden diff, called out in the changelog.
3. **Two exports, one per period, for `account-read`.** Refuse mismatched reports, currencies or overlapping dates.
   MCP gets optional comparison arguments, which is an additive change.
4. **Microsoft Advertising** search-term and keyword CSVs. Fix "Search & content" campaigns being counted as
   automated: 0.1.10's `_automated` (`search_term_waste.py:58`) treats any type other than "search" as automated,
   so map each platform's campaign types explicitly. Name it in the docs and FAQ only, labelled experimental.
5. **ADR-3, breaking part:** argparse usage errors exit 1 instead of 2, with a "Breaking" changelog entry.
6. **App:** drop in an Editor export, or two exports of the same report, and the right template is picked. Add a
   sample for each.
7. **Gate:** nothing is announced until 5 real Editor exports and 3 Microsoft exports from design partners pass.
   Anonymised, header-only fixtures go into the corpus.

**Bundle:** about 7%. **Launch:** "One Editor file audits your account's structure. Two exports show what changed."
New how-to-export pages. Retire the README line "Google Ads Editor export next".

### Phase 4: "Hand it over, gate it, use it anywhere" (0.3.0, 4 weeks, three slices that release separately)

**4a. Client deliverables (1 week; bundle about 2%).**
- `--format html` for `audit` and `check`, built per ADR-5.
- App downloads of any audit as .md, .html or .json.
- An optional call to action in the branded PDF: one line plus an https, mailto or tel link. There is none by
  default.

**4b. Builder tools (1.5 weeks; bundle about 2%).**
- `--format json`, with `format_version`, and JSON Schemas shipped in the wheel. Add `check --format sarif`.
- Declare the ADR-2 API, and ship `py.typed` with it.
- The GitHub Action, pinned by commit, which installs the same commit.
- A Dockerfile with CLI and MCP targets. Its smoke test runs with `--network none`. Dependabot watches the base
  image.
- Docs: a new "Command line and CI" page, plus that one home-page card below the existing sections.
- **Pitch:** "Fail the build when an AI audit invents a number."

**4c. Hosted connector (1.5 weeks).**
1. Finish and merge `chatgpt-app`, with its host allowlist, size caps and timeouts.
2. Port the MCP limits, improved over the fork (F18):
   - cap the bytes actually streamed, not only the declared `Content-Length`
   - run one instance, with a rate limit at the edge in front of it, since in-process limits reset on restart
3. Add a privacy page. Unlike the browser app, the connector does receive the export's contents, so the page says
   that plainly: files are processed in memory, nothing is stored, and logs hold counts only. The app's "nothing is
   uploaded" copy is never reused for the connector.
4. **[Owner]** Pick the host and a monthly cost cap. Deploy from a tagged image through CI, with a kill switch.
5. Launch `mcp.openppc.si` (already marketed as "coming soon") and the ChatGPT app.
6. Publish the Phase 0b accuracy benchmark as the first slice of the public eval on the roadmap.

**Launch:** three moments, one per slice. The connector gets its own article.

### Phase 5: Meta Ads Manager exports (0.3.x, 1 week)

The current roadmap lists Meta under "More exports", so this widens scope the way it is already marketed.
`account-read` reads a campaign or ad set export (Reports > Export > .csv):

- link clicks count as clicks
- the currency comes from the "Amount spent (…)" header
- the period comes from Reporting starts and ends
- results count as conversions only when every row has the same Result indicator; a file that mixes leads and
  purchases is refused

The report header names Meta, and reads that assume search intent are switched off. It is experimental, in the docs
only, and gated on 3 real exports from design partners. **Bundle:** about 1%.

### Companion track (Phases 6–9)

It starts after Phase 4b, which declares the engine API (ADR-2) and the JSON and SARIF formats the companion
reuses. Fetch (Phase 8) also needs Phase 3: its `account_structure.json` carries the approval statuses that Phase
3's policy check reads, and its Microsoft files need Phase 3's Microsoft reader. Meta's download writes JSON totals,
which 0.1.10 already reads, so it doesn't wait for Phase 5. Every
companion release must pass a security review of its diff (the `security-review` flow) before it ships.

### Phase 6: Companion foundation (core 0.4.0 and `openppc-online` 0.1.0, 2 weeks; no launch)

What users get: nothing visible yet. This makes Phases 7–9 safe to build.

1. **Packaging (ADR-7):** add `companion/` with its own `pyproject.toml`, and have CI build, test and publish both
   distributions from tags. The core's 0.4.0 changes only the string `openppc fetch|site|app` prints.
2. **Fitness functions 8–12** (section 4), green on an empty companion before any feature lands.
3. **Split `web/app.js` into ES modules,** since this phase triggers the deferred split (section 7). Do it as a pure
   refactor behind the Phase 0b characterization tests, using the fork's `web/js/*` layout as the map.
4. **Two web builds from one source:**
   - The hosted build for openppc.si contains no local-mode modules. A test asserts that, and that its CSP is
     byte-for-byte unchanged.
   - The local build adds `local.js` and `connect.js`, and turns local mode on only when the page carries the
     per-run token that `openppc-online app` writes into it.
5. **`openppc-online app`:** port `localapp.py`, serving the packaged local build:
   - it answers only on 127.0.0.1, and only to its own Host name
   - it needs the per-run token in a header on every API call, compared in constant time
   - uploads go into one folder per run, deleted when it stops
6. **Threat model and security review** of the local server: DNS rebinding, requests from other open tabs, token
   leaks, path traversal in uploads, and job exhaustion.

### Phase 7: Landing page and tracking check, `openppc-online site` (`openppc-online` 0.2.0, 4 weeks)

What users get: an audit of what an ad click lands on. Do the tags load and fire, before and after consent? Which
conversion events do they send, and is Consent Mode set? It also covers broken links and redirects, indexing,
speed, and the search basics.

1. **Port the crawler** (`siteaudit/`):
   - polite by default: two requests at a time, robots.txt and its Crawl-delay obeyed, caps on URL patterns
   - the private and metadata address refusal (fitness function 12)
   - the checks, the scoring and the "inconclusive" exit 4
   - a report that passes the same number check as the audits
   - rule packs and `--config`, `--baseline` and `--fail-on`
   - `--format json|html|sarif` on Phase 4b's formats, with the `site-*` schemas
2. **The `render` extra** (Playwright and Chromium): tags and events before and after the consent banner, the
   dataLayer, axe accessibility results, lab Web Vitals, `--render-url` and screenshots. Add the companion's Docker
   `render` image.
3. **`--crux-key`** reads `OPENPPC_CRUX_KEY`. **`--post-to`** takes https only, or http to localhost. It goes
   through the crawler's address guard, and the report names where it was sent (F13).
4. **Fork QA follow-through:**
   - port the B5–B7 fixes with their tests
   - re-run the fork's 31-case crawler matrix (29 behaved as expected) and fix the other 2
   - turn the QA site into fixtures served by a local HTTP server in CI, so the crawler tests never touch the
     internet
5. **The Site view** in the local app, with downloads as .md, .html, .json and .sarif.
6. **Rulebook:** add the `site-*` rows, each with a trace test, in their own category on the rules page.
7. **Docs and site:**
   - a new "Landing page and tracking check" page, rewritten on today's site rather than copied from the fork
   - a usage note: crawl sites you're allowed to, as the `OpenPPC-SiteAudit` user agent
   - the home page's "Optional companion" section (section 2, **[Owner]** approves the copy)
8. **Gate:** run it on the owner's sites and on 10 design-partner client landing pages, with permission. The partners
   review every finding, and false positives stay under a rate the owner sets.

**Launch:** an article, "Check what your ad clicks land on: tags, consent and conversions". Not in the hero.

### Phase 8: Downloads with your own API credentials, `openppc-online fetch` (`openppc-online` 0.3.0, 3 weeks)

What users get: agencies that already have API access skip the manual export. The download writes exactly the
files the templates read: `search_terms.csv`, `keywords.csv`, `account.json`, and `account_structure.json` with
approval status, which feeds Phase 3's policy check.

1. **Port the three clients:** Google Ads (`searchStream`), Microsoft Advertising (Reporting v13: submit, poll,
   download) and Meta (Graph `GET`), under fitness function 10.
2. **Credentials (ADR-8):** environment variables; in the local app, memory or the keychain (`keys` extra). Fitness
   function 11 runs on every endpoint.
3. **Errors in words:** a revoked token, a test-only developer token, a missing manager ID, the daily quota, and an
   OAuth app in Testing whose refresh tokens expire after 7 days.
4. **Tests:** the fork has only 4–7 per client. Add contract tests on recorded, scrubbed responses covering
   pagination, quota, errors and the Performance Max gap. Add a manual-dispatch live smoke workflow on the owner's
   test accounts; secrets exist only in that workflow.
5. **The Download panel** in the local app.
6. **API version calendar:** Google sunsets a version about a year after release (the fork pins v25), Meta after
   about two (v25.0), and Microsoft is on v13. A table in code records each sunset date, and CI fails 60 days before
   one.
7. **Gate:** 3 design-partner agencies with Google Ads API Basic access run it. For the same dates, each download
   must give the same audit as their manual export.

**Launch:** docs and the changelog, aimed at agencies with API access. Not in the hero.

### Phase 9: Tag Inspector extension and WordPress plugin (`openppc-online` 0.4.0, 2 weeks plus store review)

What users get: a one-page tag and consent check in the browser, and five Site Health checks inside WordPress. Both
point to `openppc-online site` for the full audit.

1. **One tag list:** the extension, the plugin and the crawler share one `signatures.json`. The build copies it, and
   a test asserts every copy is identical.
2. **Extension:**
   - Ask for `activeTab` and per-site optional host permissions when the user clicks, instead of the fork's
     `<all_urls>` at install.
   - Keep `connect-src 'self'`, and add a test that the code has no `fetch`, XHR, beacon or WebSocket.
   - Grow the Node tests beyond the fork's 2.
   - List it on the Chrome Web Store and Edge Add-ons with a "collects nothing" privacy disclosure.
3. **WordPress plugin:**
   - The fork never ran it. Add PHP CI on 7.4 and 8.3 with the WordPress test suite, PHPCS with the WordPress
     standards, and the Plugin Check tool.
   - Submit it to WordPress.org; MIT is GPL-compatible.
4. **Store reviews take 1–3 weeks** and are outside our control. Submit on day one of the phase and release on
   approval; nothing else waits for them.

**Launch:** the store listings, plus one docs page each.

## 7. How we work

- **Branches:** work lands through PRs on the integration branch (today `stagging`). Releases are tagged from `main`.
  **[Owner]** Confirm this flow.
- **One PR per fix or feature,** with a failing test first, and no PR over about 400 lines of logic. Pure refactors
  never carry behaviour changes.
- **Port checklist for each feature:**
  - read the fork's code and tests
  - write the 0.1.x test
  - re-implement
  - fix the fork's known bug
  - add the rulebook row
  - rebuild `engine.js` and check the bundle budget
  - update the docs and the compatibility matrix
- **Deferred module split:** split `web/app.js` (1,397 lines) into ES modules with `@ts-check` at the first of:
  - it passes about 1,800 lines
  - a second engineer works on the web app
  - Phase 6, whose local views would otherwise land in the monolith

  Use the fork's `web/js/*` layout as the map, and treat it as a pure refactor behind the Phase 0b characterization
  tests. The local-only modules (`connect.js`, `local.js`, `site-view.js`) go only into the local build.
- **Definition of done for every release:**
  - golden files unchanged, or the diff reviewed
  - the compatibility matrix green
  - the fitness functions passing on three operating systems
  - accuracy and speed at or above baseline
  - `engine.js` fresh and within its phase budget
  - `CHANGELOG.md`, the README and the docs updated
  - published from a tag
  - the deployed site checked in a real logged-out browser on desktop and mobile
- **Rollback:**
  - PyPI: yank the version and publish a patch; never overwrite a version.
  - Site: redeploy the previous `dist/`.
  - Connector: the previous image stays deployable, and the kill switch answers "temporarily off".
  - Action: users pin commits, and a moving `v1` tag moves only after verification.
  - Companion: yank on PyPI like the core. The extension and plugin roll back by publishing the previous version
    again in their stores, since stores have no yank.
- **For every companion release, the definition of done also has:**
  - fitness functions 8–12 green
  - the security review passed
  - the API version calendar green
  - the hosted openppc.si build still free of local modules, with its CSP unchanged
- **With a second engineer:** one takes the Python lane (Phase 3 engine work, then 4b), the other the web lane
  (Phase 2, the module split, the app parts of Phases 3 and 4a). Phase 4c can start once Phase 1 ships. After 4b,
  the second engineer takes the companion track (Phases 6–9) while the first finishes 4c and 5, then joins on Phase
  8.

## 8. Success measures (no app telemetry)

| Measure | Source | Target by 0.3.0 |
|---|---|---|
| Real exports read correctly | design partners, "report this file" issues | 100% of partner files; each issue answered within 3 working days |
| Silent wrong numbers | issues and partner reports | zero open |
| Checker accuracy | the Phase 0b benchmark | at or above the 0.1.10 baseline, and published |
| Reach | PyPI and uvx downloads, Docker pulls, stars | owner sets the numbers after the 0.1.11 baseline |
| CI adoption | public repos using the Action | the first 10 |
| Connector use | request counts only | owner sets the number |
| Site interest | consent-mode analytics on `/app/` and the export docs (site only, never the app) | trending up |
| Companion reach (by its 0.4.0) | `openppc-online` downloads, store installs and ratings | owner sets the numbers after Phase 7 |
| Landing-page check quality | design-partner review of findings | false positives under the owner's rate |
| Fetch correctness | downloads compared with manual exports for the same dates | identical audits for every partner account |
| Secret leaks and promise drift | fitness functions 8–12, issues | zero |

## 9. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A port changes numbers users already see | Medium | High | Golden files, the accuracy gate |
| A locale change silently changes totals | Medium | High | Property tests (the streaming read equals the whole-file read), refuse ambiguous files, Phase 0a's before/after diff |
| Network code creeps into the core or the bundle | Medium | High | Import ban, the offline CLI test, the bundle allowlist and its budget (the fork's denylist already leaked) |
| Editor, Microsoft or Meta importers fail on real files | High | Medium | Design partners recruited in Phase 0b, the experimental label, "report this file" |
| Marketing drift: other platforms creep into the hero, or SEO regresses | Medium | High | Pinned phrases, titles and canonicals; ADR-6 |
| The exit-code change breaks someone's CI | Low | Low | Only usage errors move, and only in the minor version 0.2.0; changelog, compatibility matrix |
| Hosted connector abuse, cost or privacy exposure | Medium | High | MCP limits, the token, the kill switch, the privacy page, counts-only logs |
| `chatgpt-app` and the MCP limits conflict | High if unordered | Medium | Settle the branch before 4c |
| `app.js` grows hard to change before the split | Medium | Medium | The split trigger in section 7 |
| One engineer becomes a bottleneck | Medium | Medium | The two lanes in section 7 |
| Users read the companion as "OpenPPC connects to my account now" | Medium | High | Its own name and command (ADR-7), promises scoped in `GOVERNANCE.md`, pinned copy, never in the hero |
| A credential leaks from the companion or the local server | Low | High | ADR-8, fitness function 11, threat model and security review, keychain or memory only |
| The crawler is used against private networks, or too hard against a site | Low | High | Fitness function 12, polite defaults, robots.txt, the usage note |
| A platform sunsets its API version and fetch breaks | High over a year | Medium | The version calendar fails CI 60 days early; the live smoke workflow |
| A store rejects or delays the extension or plugin | Medium | Low | Narrow permissions, a privacy disclosure, submission on day one; nothing waits on it |
| The companion track starves the core | Medium | Medium | It starts only after 4b, in the second engineer's lane; core bugs come first |

## 10. Parked, with the conditions to reopen

- **Template plugins:** reopen when an outside contributor asks, after ADR-2's API is declared. The docs must say
  plugins aren't covered by the no-network promise.
- **Fetch and crawl tools in the MCP server:** reopen for the local MCP server only, after Phase 8 has been stable for
  a release, behind fitness functions 9–12. The hosted connector never gets them.
- **Scheduled or hosted crawls and downloads** (a server that runs them for you): out of scope. They would mean
  storing credentials and running on our servers, which is a paid-service question under `GOVERNANCE.md` pledge 2.

## 11. Open questions for the owner

1. Finish `chatgpt-app` in Phase 4c (recommended), or drop it?
2. Who are the 5–10 design partners, recruited in Phase 0b?
3. Confirm the branch flow: `stagging` for integration, `main` for releases.
4. The README says "Premium templates are planned as a paid add-on: … a branded client-ready PDF", but the app
   already ships the branded PDF free. The fork fixed this line. It is marketing copy, so it stays unless you approve
   the fix (recommended).
5. `TRADEMARK.md`: adopt it now or later?
6. Move "Rules · Soon" out of the main navigation? It changes the visible menu, so it stays by default.
7. Where does the hosted connector run, and what monthly cost cap applies (Phase 4c)?
8. The companion's name and command. The working name is `openppc-online`; it should say plainly that it goes
   online. Avoid "Connect", since "OpenPPC Connect connects to your account" would undercut the core promise.
9. Approve the home page's "Optional companion" section copy (Phase 7).
10. The accounts the companion needs: a Google Ads API developer token with Basic access and test accounts for the
    live smoke workflow, a Microsoft Advertising developer token, a Meta system user, a Chrome Web Store developer
    account, Edge Add-ons, and WordPress.org.

**Answers (Oct 12, 2026):**

| # | Answer |
|---|---|
| 1 | Keep `chatgpt-app` for Phase 4c; don't touch the branch until then |
| 2 | No outreach now; design partners are skipped |
| 3 | Changes go to `stagging`; Shiv merges to `main` when they're good, and releases from `main` |
| 4 | Keep the README's premium line as it is |
| 5 | `TRADEMARK.md` later |
| 6 | Keep "Rules · Soon" in the navigation |
| 7 | Open (Phase 4c) |
| 8 | `openppc-online` |
| 9 | Open (Phase 7) |
| 10 | Open (Phase 6) |

**Oct 13, 2026:**
- 7: still open.
- 9: draft the home page section and the docs page for review, as local commits.
- 10: no accounts yet.
- Phase 8: build it on fixtures made from each API's documentation, to be replaced by recordings later.
- Phase 9's WordPress plugin: install PHP here, then build and test it.

Also decided: commits stay local (nothing pushed, released or deployed without the owner); `GOVERNANCE.md` and
`THIRD_PARTY_LICENSES.md` are drafted now and reviewed in the pull request; this plan stays local and untracked.

## Appendix A: evidence (Windows, Python 3.9 for 0.1.10, the fork's own 3.12 venv; Oct 11, 2026)

| Input | 0.1.10 | Fork |
|---|---|---|
| `search_terms_fr.csv` | exit 0: "Account totals: **€0.00 cost**", "No search term… reached €20.00" | €767.60 of waste out of €4,347.25; "read with decimal commas" |
| `search_terms_en_in.csv` | exit 1: `'charmap' codec can't encode '₹'` (Windows console) | reads, with a ₹1,500.00 threshold |
| `search_terms_cp1252.csv` | exit 0, no note | exit 0, with a "not in Unicode" note |
| `--sample --min-cost nan` / `-5` | runs and prints "waste threshold $nan" / "$-5.00" | refused |
| `editor_export.csv` | exit 1, refused (not supported) | reads |
| `search_terms_de`, `_utf16`, `_pmax`, `_duplicates`, `_fractional`, `_renamed`, `_zero_cost`, `_no_waste`, `_june`, `_july` | exit 0, correct | the same |
| `search_terms_german_headers`, `_mixed_formats` | exit 1, refused with the right reason | the same |
| `web/engine.js` | 323,832 bytes on `stagging`; no network modules (built by `rglob("*.py")`, `tools/build_web.py:57`) | 367,558 bytes; `mcp_limits` and the CLI's fetch and site wiring included |
| CLI exit codes | 0 / 1 / 2 / 3 already (`cli.py:75-105`); argparse errors are 2 (`audit nope` exits 2) | 0 / 1 / 2 / 3 (and 4 for `site`), plus `--debug` |

Companion facts, from the fork (Oct 12, 2026):

| Area | What the fork has |
|---|---|
| Local server | 127.0.0.1 only, a Host check, a per-run token compared in constant time (`localapp.py:11-12, 236-239, 398`); the web build comes from a clone |
| API clients | standard-library `urllib` only. Google Ads API `v25` (`google_ads_api.py:34`, "bump it with each release"), Microsoft Reporting v13, Meta Graph `v25.0` |
| Crawler guard | refuses private, link-local and metadata addresses, through redirects and DNS rebinding (`siteaudit/net.py:7, 36-61`) |
| `--post-to` | accepts `http://` as well as `https://` (`cli.py:234`) |
| Extension | MV3; `webRequest`, `storage`, `activeTab`, `scripting`, and `<all_urls>` host permission; `connect-src 'self'` |
| WordPress plugin | five Site Health checks; never run, because no PHP was installed during the fork's QA (`project-issues.md:450`) |
| Tests | `test_siteaudit` 51, `test_localapp` 15, Google 4, Microsoft 4, Meta 7, extension 2, WordPress 2 |
| Governance | pledge 3: a network change must be "documented, off by default, and turned on only by you"; pledge 4: "never connects to an ad account" (`GOVERNANCE.md:15-16`) |
| Licenses | axe-core 4.10.3 is MPL-2.0, vendored unmodified (`THIRD_PARTY_LICENSES.md:22`) |

## Appendix B: critique log

- **v1 to v2 (scope and safety):**
  - Corrected the bug list: issue 3.2 was already fixed, and B4 is new work.
  - Cut the locale work down to what 0.1.10 doesn't already do.
  - Added fitness functions, golden files, ADRs, the compatibility matrix and the changelog.
  - Kept the negative-input refusal.
  - Moved plugins, SPDX and `TRADEMARK.md` out of the plan.
  - Added design partners, the "report this file" link, success measures and rollback.
- **v2 to v3 (re-checked against the code, as a senior engineer):**
  - Added offerings v2 missed: `--min-cost` validation, the report's reading notes, `--debug`,
    `check --format html`, step progress, the typed template contract with mypy and `py.typed`, Dependabot for
    Docker, the command-line docs page, and rule packs (parked with the crawler).
  - Fixed ADR-3: 0.1.10 already uses 0/1/2/3, so only argparse errors move, which is much smaller than v2 said.
  - Added the measured bundle facts, showing the fork's denylist leaks network wiring.
- **v3 to v4 (product and sequencing, as a senior PM):**
  - Phase 0a hotfix: the French €0.00 bug is silent and passes the self-check, so it can't wait behind
    infrastructure.
  - Brought Meta back in scope as Phase 5, experimental and docs-only, because the current roadmap already lists it.
    v2's reason for parking it contradicted today's marketing.
  - Deferred the `app.js` module split behind a trigger, since the fork split an older file. Phase 2 became
    user-facing accessibility and progress work.
  - Moved design-partner recruiting to Phase 0b, so real files exist by Phase 3.
  - Added "What must not change" (section 2) and SEO pins, after the #29 SEO baseline.
  - Raised the README's "branded PDF is paid" contradiction with the owner instead of editing marketing copy.
- **v4 to v5 (architecture):**
  - ADR-5's HTML must have no scripts and no external URLs.
  - JSON Schemas ship in the wheel.
  - `py.typed` ships only with a declared API (ADR-2).
  - ADR-6 requires each report to name its platform, and switches off search-intent reads for Meta.
  - The bundle budget is split per phase.
  - Added two-engineer lanes, and a risk for marketing drift.
- **v5 to v6 (independent re-verification, then a consistency pass):**
  - Re-ran appendix A from scratch. Every claim held except the bundle size, now 323,832 bytes.
  - Confirmed the fork's bugs at the line: the comma-stripping budget parse, the negative-cost warning
    (`google_ads_csv.py:398-400` in the fork), currency taken from the first row in both lines, and `_automated`.
  - Fixed a contradiction: v5 shipped the breaking exit-code change in a patch release (0.1.12) against its own
    "only a minor version may break" policy. The additive part stays in 0.1.12; usage errors move in 0.2.0.
  - Fixed the arithmetic: the phases add up to 14 weeks, not 13.5.
  - Moved the app characterization tests from Phase 2 to Phase 0b, because Phase 1's "report this file" link
    already changes the app.
  - Tightened "report this file": column names only, never the title lines that can carry the account name.
  - Added offerings: `check --data a b`, the contributor docs, and the sample's intended golden diff in Phase 3.
  - Made the connector's privacy copy distinct from the app's "nothing is uploaded", and added the hosting decision.
  - Added a reproducible-bundle gate. A Windows rebuild during this review changed `engine.js` (CRLF in the
    embedded samples) with no code change. The stray rebuild was reverted.
- **v6 review: stop.** A further pass found nothing that changes scope, order, estimates or decisions.
- **v6 to v7 (owner request: bring the network half into scope):**
  - Draft: the five features as Phases 6–9, in an optional companion with its own distribution and command (ADR-7)
    and credential rules (ADR-8). Added fitness functions 8–12, and scoped the `GOVERNANCE.md` pledges from the start
    so no amendment is needed.
  - Architect critique:
    - Rejected the fork's layout (network code inside `openppc`, gated by extras), because extras gate dependencies,
      not code.
    - Rejected subcommands of `openppc`, because "the `openppc` command makes no network calls" would then depend
      on what else is installed.
    - Kept openppc.si's build and CSP unchanged by producing two web builds from one source.
    - Kept fetch and crawl out of the hosted MCP connector (SSRF, credentials).
  - PM critique:
    - Put the crawler first and pitched it as the landing-page and tracking check: no credentials, the widest PPC
      audience, and the lowest risk.
    - Aimed fetch at agencies with API access, since a developer token with Basic access is real friction.
    - Ship the web build in the companion's wheel, because the fork's `openppc app` needs a clone.
    - Added gates on real accounts: findings reviewed by partners, and fetch compared with manual exports.
  - Security critique:
    - Narrow the extension's `<all_urls>` to per-site optional permissions.
    - Restrict `--post-to` to https.
    - Add a threat model and a security review for every companion release.
    - Add the read-only call allowlist, since Google's and Microsoft's scopes permit writes.
    - Add the sentinel-secret test.
  - Delivery critique:
    - The WordPress plugin was never run, so it gets PHP CI first.
    - Store reviews are outside our control, so submit on day one and let nothing wait on them.
    - Added the API version calendar, since Google sunsets yearly.
    - Fetch depends on Phase 3, not Phase 5.
    - Corrected the two-engineer estimate to about 17 weeks.
- **v7 review: stop.** A final pass changed only labels (companion version numbers in the phase headings). What's
  left is in the owner questions 8–10 and the real-account gates.
- **v7 to v8 (owner request: improve what the fork executed poorly):**
  - Added section 3b, 23 weaknesses with evidence. New in this round:
    - two HTML renderers (F10)
    - the slower `totals()` (F1)
    - in-memory MCP limits and the `Content-Length`-only size cap (F18)
    - the webhook's missing address guard (F13)
    - the untested Stop on huge files (F20)
    - the wrong connector domain (F23)
    - and, measured on this machine, today's suite failing 4 tests on Windows (F22)
  - Folded each item into the phase that does the work: Phase 0a now makes the suite green on Windows before its
    golden diff, 0b adds the 100k-row Stop test, ADR-5 names the Python renderer, and 4c and 7 carry the MCP and
    webhook fixes.
- **v8 review: stop.** One more pass found no change to scope, order or estimates. Execution starts with Phase 0a
  (appendix C).
- **v8 to v9 (corrections found by executing):**
  - Line endings are fixed with `.gitattributes`, not in the build. The sample CSVs hold CRLF rows on purpose, so
    normalizing them would change their bytes and the SHA-256 printed in reports.
  - The app has six hash routes, not five: `#check` was missing from section 2.
  - The fork's expected failure "a term wasting money across ad groups is flagged once" is already fixed in 0.1.10.
    It is ported as a passing test.
  - The fork's full ruff set flags 158 findings here, so lint starts with correctness rules (Phase 0b, item 7).

## Appendix C: execution log

Run on Windows with the fork's Python 3.12 venv, because PyPI was unreachable (TLS verification failed) and the
system Python is 3.9. Commits are local on `stagging`; nothing has been pushed, released or deployed.

**Phase 0a (0.1.11): done in the working tree.**

- Numbers: `parse_number` and the decimal-mark tally strip spaces of any kind, apostrophes, a typographic minus, and
  a currency mark or code on either side (`openppc/ingest/google_ads_csv.py`). `Rs. 1,234` now reads as 1234, where
  0.1.10 dropped the cell.
- Threshold: `threshold()` in `openppc/templates/_common.py` is shared by both templates that use one. It covers the
  CLI, the app, MCP and `check`. `--min-cost nan`, `inf` and `-5` exit 1 with a message.
- Console: `openppc` switches stdout and stderr to UTF-8 when they use another encoding. A test runs the CLI with
  `PYTHONIOENCODING=cp1252` and reads `₹72,922.00`.
- Windows: the tests read UTF-8 explicitly, and `.gitattributes` was added. The rebuilt `engine.js` differs from
  the committed one only in the changed Python files; the samples and the precomputed sample results are identical.
- Golden diff, before and after, over all 4 samples (with and without an industry), `check` on the sample, and 16
  fork fixtures × 2 templates: **1 of 40 outputs changed**, the French fixture, which now finds €767.60 of waste in
  €4,347.25, the same as the German and English files. It passes its own check.
- Suite: 177 passed and 4 failed before; 185 passed after the hotfix.
- Left: the release and the deployed-app check in a real logged-out browser (Phase 0a, item 6).

**Phase 0b: engineering items done; owner items open.**

- Done:
  - ADR-1 to ADR-6 (`docs/adr/`), `CHANGELOG.md` with the 0.x policy, and `docs/compatibility.md`
  - fitness functions 1–4 (`tests/test_fitness.py`). The network scan was checked against a scratch package with
    planted imports, and caught all three.
  - item 5, the golden harness: `tools/build_golden.py` and `tests/golden/`, 40 files. It freezes reports, cards
    and client JSON, `check`, MCP answers, and every page's title, description and H1.
  - the bundle allowlist in `tools/build_web.py`, with an identical `engine.js`
  - the fork's fixture generator and corpus (`tools/build_fixtures.py`, 16 files, byte-identical to the fork's)
    and `tests/test_fixtures.py`, adapted to 0.1.10
  - CI on Windows and macOS, and ruff with correctness rules. 5 findings were fixed (unused imports and f-strings
    without placeholders); the golden files confirm no output changed.
  - `CONTRIBUTING.md` explains each tool
- Suite now: 225 passed, 4 skipped (the MCP SDK is not installed here). `ruff check` passes.
- Not done in that pass: the baselines, the browser tests, the two governance files and the owner questions. All
  but the owner-only items are done in the second pass below.

**Second pass (Oct 12, 2026): the project's own venv, browser tests, baselines, drafts.**

- Environment: the project's `.venv` (Python 3.12.3) now installs from PyPI through the Windows certificate store
  (`truststore`, wheels checked against PyPI's SHA-256), and Playwright's Chromium through Node's `--use-system-ca`.
  TLS verification stayed on throughout. The 4 MCP tests run: nothing is skipped.
- Baselines (item 5, fitness function 6): `tests/test_accuracy.py`, ported from the fork, measures recall 0.964 and
  precision 1.000 on 680 labelled claims; the floors are 0.95 and 0.99. `tests/test_performance.py` audits a
  20,000-row export in about 1.4 s and checks it in 2–5 s on this laptop; the budget is 20 s each.
- Browser tests (item 6): `tests/e2e/`, 23 tests in Chromium against `web/` served locally, about 100 s. They cover
  every route (and an unknown one), the sample check precomputed and then live with the same 3 wrong numbers, 1 wrong
  label and 1 contradiction, the sample audit's .md, .csv and clipboard exports, each template on its example, the
  branded PDF's gate, Stop on a 100,000-row export, axe on six pages and a phone, and no sideways scroll at 390 px.
  They are marked `e2e`, left out of a plain `pytest`, and run in their own CI job.
- Accessibility: axe found one serious rule, `color-contrast`: `--faint2` was 3.12:1 on white and `--faint` 4.44:1
  on the page background. Both tokens were darkened to pass 4.5:1 (`web/style.css`), so the allowed list is empty.
  `site/static/site.css` uses the same `--faint` and was not changed or tested.
- Governance (item 8): `GOVERNANCE.md` and `THIRD_PARTY_LICENSES.md`, marked as drafts. Pledges 3 and 4 are scoped to
  the package, the app and the MCP server, and the companion has pledges 6–9. A test keeps the license list in step
  with what the app loads, and two pledge sentences joined the word-for-word promises.
- Checks: no tracked text file changes under `.gitattributes` (the only CRLF files are CSVs marked `-text`), and the
  client name known locally appears nowhere in the repository.
- Still open: the release and the deployed-app check, which need a push; the client-name denylist scan, which runs
  in CI on the pull request; owner questions 7, 9 and 10.

**Phase 1 (0.1.12): committed as `5c68efd`.**

- Encodings: Windows-1252 is tried before Latin-1, and UTF-16 without a byte order mark is recognised. `check` reads
  audits in both.
- A `|` inside a name no longer splits its table cell, so such rows pass their own number check.
- Rows in two currencies are refused instead of added up. Clearer refusals for a folder, a header with no rows, a
  missing `--out` folder and invalid JSON (with line and column).
- CLI: `--data a.csv b.csv`, `--debug` anywhere, and a crash exits 3 in one line.
- "Report this file": `column_names()` returns the header row only; the app previews exactly what goes into a
  prefilled GitHub issue (`.github/ISSUE_TEMPLATE/file_not_read.yml`, plus `wrong_finding.yml`), with the file name
  replaced. The prefill can only be checked once the forms are on GitHub's default branch.
- B3 (negative numbers in the tracer) was not needed: the tracer compares absolute values, and ADR-4 refuses
  negative costs.

**Phase 2 (0.1.13): committed as `b8e8244`.**

- Progress: `run_template_book` and `webapi` report each step through `on_progress`; the worker forwards them and
  the page shows them under Run. Stop still works (e2e).
- B9: the page posts the engine bundle to the worker, so `engine.js` is fetched once. The old code fails the new
  e2e test with two downloads.
- App accessibility: a main heading and title per view, skip link and `<main>`, one live region for messages, a
  reason under a disabled Run, roving tabindex with arrow keys on the template list, focus on the drop zone,
  scrollable tables named as regions, contrast and target sizes, a copy fallback without the clipboard API, PDF
  preview heading order. axe at every impact (not only serious and critical) is clean on all six views, both
  results and the branded PDF, at 1440 and 390 px.
- Website: phone menu (`details` in `site/layout.html`), named GitHub button, footer `h2`s, focusable code blocks,
  `--faint` darkened to #666e73 (4.5:1 on the page background). New `tests/e2e/test_site_pages.py` scans every site
  page with axe at both widths; it evaluates the axe source rather than bypassing the site's CSP.
- The site test's "one `<h1>` per page" now allows the app one per view, since only one view shows at a time.
- Checks: ruff clean; 249 plain tests and 32 e2e tests pass; the staged tree was tested in isolation before commit.
- Next: Phase 3. Owner: push `stagging`, CI, merge, release 0.1.11 to 0.1.13, then the deployed check on desktop
  and phone in a logged-out browser.

**Phase 3 (0.2.0): execution plan after three critique rounds.**

Round 1 found that the fork's Editor reader needs reader helpers ours doesn't have (rewrite it on our streaming
reader), that check mode fails on a two-period report unless the pair's facts are added, that `inspect_file` and
`facts_for_paths` must know Editor files, that a new module must join the bundle allowlist or only the browser
breaks, and that the fork's "no live Search, so only the policy check" shortcut changes reports (dropped). Round 2:
design partners were skipped, so the gate in item 7 can't be met; Editor and Microsoft ship labelled experimental
and the launch waits for the owner. The Microsoft fixtures are built from Microsoft's documented report layout,
not a real file, and say so. An explicit campaign-type map also fixes Google's older "Search Network with Display
Select", which 0.1.13 counts as automated; every other type keeps today's grouping. An Editor sample generated
from the Acme snapshot gives a round-trip test. Round 3: in the app a pair is the last two good report files, the
account-read option shows "Matches your files", a mismatched pair says why under Run, and no new sample enters the
bundle. Commits, each tested in isolation:

1. Reader: `HEADER_LINES` 50, Microsoft Advertising columns, dates and footer, `Report.platform` named in the
   header for non-Google files, the campaign-type map, and an Editor export named in the refusal.
2. Editor and the account snapshot: `ingest/editor.py` (UTF-16 TSV, names as ids, budgets with the file's decimal
   mark), snapshot fields `budget`, `budget_limited`, `approval`, `policy`; the policy and budget-cap checks with
   "can't tell from this file"; rulebook rows; approvals in the Acme snapshot; `examples/editor_acme.csv`;
   `inspect_file` and `facts_for_paths` read Editor files.
3. Two periods: `account-read` takes two exports; the CLI takes two files; MCP gets `prior_path` and
   `prior_text`; `facts_for_paths` adds a valid pair's comparison; a periods-of-different-length note;
   `examples/search_terms_acme_june.csv`.
4. ADR-3: argparse usage errors exit 1 (Breaking).
5. App: an Editor file picks account-structure, two exports pick account-read, with e2e tests.
6. Docs (formats, compatibility matrix), CHANGELOG 0.2.0, golden diff reviewed, `engine.js` rebuilt.

**Phase 3 (0.2.0): committed on `stagging` as six commits, `3e4a46e` to `b3d1fda`.**

- `3e4a46e` reader, `84d5747` Editor and the two checks, `fe1af63` two periods, `a14b44f` exit codes, `2402fc3`
  app, `b3d1fda` docs. Each staged tree was tested in isolation before its commit.
- Found while executing, and fixed in the same commits: with no live Search, the Search checks passed over nothing
  (now "No live Search campaigns"); check mode re-ran a snapshot report without its summary, so the summary counts
  didn't trace; a same-named prior export in the MCP web connector overwrote the current one (now in a folder of
  its own); `account_acme.json` was written with CRLF on Windows; a pair's check-mode facts must leave out the rule
  thresholds.
- App: `webapi.inspect_pair` and `audit(..., prior)`. The pair is the last two good report files; a valid pair picks
  account-read ("Matches your files"); an invalid one keeps the option pickable and Run says why. The branded PDF
  names both files and fingerprints each.
- Golden diff since 0.1.13: two new account-structure checks and their sections, the policy exception in "How this
  was computed", the Editor refusal, "first 50 lines", and three new golden files (Editor, Microsoft, the pair).
- Checks: ruff clean; 300 plain tests and 35 e2e tests pass; `engine.js` is 352 KB (budget about 372 KB).
- Not verified: the Microsoft layout and the Editor column names (Budget type, Approval Status, the header row)
  against real files; the Editor menu path in the install guide. Both ship as experimental.
- Owner: the README's "Google Ads Editor export next" line, the version bump to 0.2.0, push, release, and the
  launch.

**Phase 4a and 4b (0.3.0): execution plan after three critique rounds.** The owner chose 4a and 4b now, local
commits only; 4c waits for question 7.

Round 1 (engineer): the app's .json download in 4a needs the JSON format that 4b introduces, so both JSON formats
and their schemas move to 4a and 4b keeps SARIF and the builder tools. The fork's Dockerfile copies only
`openppc/`, but our wheel force-includes the five samples from `examples/`, so its build would fail: copy those
five files, and add an allowlist `.dockerignore` so no client export enters the build context. The HTML must leave
the version out, so its golden files don't change with every bump; JSON keeps it under `openppc`. The renderer only
needs what reports emit (headings, tables with `\|`, numbered and dash lists, bold, underscore italics, code,
rules); no report has links or raw HTML, and every character of data is escaped. Round 2 (product): three download
buttons crowd the report header on a phone, so "Download .md" stays and a line under the header offers .html and
.json. The precomputed sample has no engine token, so its .html and .json wait for the checker, as the branded PDF
already does; that code is shared. The call to action is one line on the cover, its link only https, mailto or tel,
remembered with the brand kit, and set aside by the PDF's number check like the agency and client names, so a phone
number in it is never flagged. Round 3 (architect and delivery): ADR-2's API is declared as the five names with
type hints, a `Template` protocol that `TEMPLATES` is typed against, mypy on those modules only (`follow_imports =
silent`), and `py.typed`. The Action installs its own commit, takes inputs through the environment only, and CI runs
it twice: on the sample AI audit (must fail) and on an OpenPPC report (must pass). Docker is checked by a CI job
that builds both targets and runs the samples with `--network none`; locally only if Docker's engine runs.

Commits, each tested in isolation:

1. `openppc/formats.py`: `to_html` (ADR-5), audit and check JSON with `format_version` 1, both schemas in the
   wheel; `audit --format md|html|json`, `check --format md|html|json`. Tests: the numbers in each golden report's
   HTML equal its markdown's, no script, link, image or `url(`, escaping, schema validation, exit codes unchanged.
2. App: .html and .json downloads of any audit through the worker, the shared sample token, e2e.
3. Branded PDF call to action, e2e (link rules, number check).
4. `check --format sarif`.
5. ADR-2 API, `Template` protocol, type hints, `py.typed`, mypy in dev and CI.
6. `action.yml` and its CI job.
7. Dockerfile, `.dockerignore`, Dependabot for Docker, a CI job with `--network none`.
8. Docs: "Command line and CI" page, one home-page card, README, compatibility, CHANGELOG 0.3.0, `llms.txt`.

**Phase 4a and 4b (0.3.0): committed on `stagging` as nine commits, `c594dde` to `789e1e5`.**

- `c594dde` HTML and JSON output, `ba3e6f1` app downloads, `6bc049a` PDF call to action, `0119616` the bundle
  leaves out `cli.py`, `mcp_server.py` and `__main__.py` (it was near its size budget), `34db049` SARIF, `a3259fa`
  ADR-2 API, `75423fd` GitHub Action, `1b7e3c9` Docker, `789e1e5` docs. Each staged tree was tested in isolation
  before its commit.
- Found while executing: mypy can't check `trace.py`'s older body yet (16 errors), so only its signature is typed and
  ADR-2 says so; SARIF needs a relative path, or a file URI for a path outside the working folder; the docs index
  had two command line cards, merged into one; the SEO golden file lists the new page.
- Checks: ruff and mypy clean; 382 plain tests and 36 e2e tests pass; SARIF validated once against the 2.1.0
  schema; the new page and home card looked at on desktop and a phone; `engine.js` about 346 KB.
- Not verified locally: the Docker builds (the engine was off; `tests/test_docker.py` checks the Dockerfile
  statically, and the CI job is the first real build); the Action and Docker jobs on GitHub's runners; Python 3.10
  at runtime (CI covers it); the wheel's contents (no build backend installed here).
- Owner: the version bump to 0.3.0, push, release, a moving `v1` tag for the Action if wanted (the docs pin by
  commit), the home card's copy, and publishing the site.
- Next: 4c waits for question 7. Phase 5 (Meta) can't pass its gate without design partners, so it would ship
  experimental like Phase 3's readers. Phase 6 needs no owner answer for its first steps.

**Phase 5 (Meta, 0.3.1): execution plan after three critique rounds.** The owner chose Phase 6 and Phase 5; Phase 5
goes first, as the version order (0.3.x before core 0.4.0) and its size suggest. Design partners are skipped, so it
ships experimental, built from the published layout and the fork's reader (which has no tests of its own).

Round 1 (engineer): the fork maps Meta's columns only when the header has "Reporting starts", so a Google export
with a column named Results is never misread; keep that. Meta leaves a cell blank for none, so the blank-figure
refusal is off for Meta only. Its period comes from the rows' Reporting starts and ends (ISO dates), its currency
from "Amount spent (EUR)". The fork misses three cases: Results with no Result indicator column can't be known to
be one result type, so it isn't counted as conversions; two files that each count one type but different types
(June leads, July purchases) must be refused as a pair; and an indicator can carry a custom conversion's id, a
number that would fail the report's own check, so no indicator is printed in a report. Round 2 (product): a Meta
file given to the waste or keyword audit says it is a Meta export and to compare two with account-read; the app
labels it "Meta Ads Manager report" (the app pairs files whose kind ends in "report"); a single Meta file shows
account-read as needing a pair. Reads that assume search: the reach-dilution flag names broad match, so Meta gets
its own wording; the industry averages are Google search averages, so a Meta report leaves them out and says so.
The "How the files were read" line says link clicks count as clicks and Results as conversions. Round 3
(delivery): two commits, reader and report then docs; fixtures from `tools/build_fixtures.py` (two periods in EUR
with a blank cell, and a file that mixes result types, whose refusal becomes a golden file); a golden pair report;
an e2e test that two Meta files pick account-read; `engine.js` rebuilt. Docs follow Phase 3's Microsoft pattern:
the install guide, compatibility, the changelog; not the home page.

Commits, each tested in isolation:

1. Meta reader, account-read on two Meta exports, the refusals, `inspect_file`'s kind, fixtures, goldens, tests,
   e2e, `engine.js`.
2. Docs: install guide, compatibility, CHANGELOG 0.3.1.

**Phase 5 (0.3.1): committed on `stagging` as `f4cbba2` (reader and report) and `d68e898` (docs).**

- Findings while building: a Meta export without its Reporting starts column would have got the Google-only "no
  header row" message, so it now says it looks like a Meta export missing those columns.
- Checks: ruff and mypy clean; 395 tests (11 new in `tests/test_meta.py`, two new golden files, no existing golden
  changed); 37 browser tests, including two Meta files picking account-read; each commit's suite run from a clean
  checkout of the index. `engine.js` is 352 KB, inside its budget.
- Not verified: real Meta exports (none available; the fixtures follow the published layout), and the Ads Manager
  menu names in the install guide (Reports, Export table data).
- Owner: the version bump to 0.3.1 and its release.

**Phase 6 (companion foundation): execution plan after four critique rounds.**

Draft (section 6): packaging, fitness functions 8–12, the `app.js` split, two web builds, `openppc-online app`
ported with uploads, then a threat model and security review.

Round 1 (engineer):
- The `app.js` split moves to the start of Phase 7. Phase 6 adds no view: `local.js` runs as its own script. The
  hosted app is cache-busted by content (`version_app` rewrites three names); ES modules would need every import
  versioned, or a returning visitor runs new modules against old ones. That is risk on the production app for no
  user gain until the Site view lands.
- Jobs, uploads, credentials and the downloads route come with their callers (Phases 7 and 8). An endpoint with no
  caller is attack surface with no use. Phase 6's API is `GET /api/info`.
- The core's pyproject stays 0.1.10 until the owner bumps it, and the companion pins `openppc>=0.4,<0.5`. CI
  installs the companion with `--no-deps`; its release job checks that the pin admits the core version.
- The wheel needs the web app. `tools/stage_companion_web.py` copies `web/` into `companion/openppc_online/web/`
  (gitignored, included through Hatch's `artifacts`); in a clone the server falls back to the repo's `web/`. CI
  builds the wheel and checks its file list.
- `release.yml` runs on every published release and would fail on a companion tag; both release workflows are
  guarded by tag prefix (`v*` and `openppc-online-v*`).

Round 2 (security):
- Static files come from a fixed map of the web folder's files, built at start, not `SimpleHTTPRequestHandler`'s
  path translation: no traversal and no directory listings.
- Only GET and HEAD; nothing reads a request body. A handler timeout keeps a slow client from holding a thread.
- The token page is `Cache-Control: no-store`. Every response has a CSP header with `frame-ancestors 'none'`
  (a meta tag can't set it), `Referrer-Policy: no-referrer` and `X-Content-Type-Options: nosniff`. No CORS headers.
- The token is never in a URL, a log line or any other response; a test runs it through every route as a sentinel.
- `THREAT_MODEL.md` in `companion/`: DNS rebinding, other tabs and sites, other local users, token leaks, path
  traversal, framing, exhaustion. The formal `security-review` run stays with the owner, before the first release.

Round 3 (product and delivery):
- What changes for users: `openppc fetch`, `site` and `app` say plainly that OpenPPC never goes online and where
  the command lives (`app` now, `fetch` and `site` planned). `openppc-online app` opens the same app from
  127.0.0.1, with a line saying it is running on this computer. openppc.si doesn't change.
- Fitness functions: 8 in full; 9 for `app` (only 127.0.0.1); 10 as "the companion has no HTTP client yet", which
  Phase 8 replaces with per-platform allowlists; 11 with the token as the sentinel; 12 lands with the crawler.
- Docs: `companion/README.md` and `companion/CHANGELOG.md`, the core CHANGELOG's 0.4.0, compatibility's command
  list. No README or site change (Phase 7's section needs the owner's approval of its copy).

Round 4: one check added, that the local page fails loudly if `web/index.html`'s policy changes, as the fork does.
A further pass changed nothing material, so this is the plan.

Commits, each tested in isolation:

1. Core 0.4.0: `openppc fetch|site|app` answer with exit 1; fitness function 8 on the core side (no import of the
   companion, exactly four commands, the hosted build has no local modules and its CSP is pinned whole, MCP has no
   fetch or crawl tool).
2. Companion 0.1.0: the package, `openppc-online app`, `local.js`, fitness functions 9–11, the threat model, an e2e
   test, the CI job and the release workflow.
3. Docs: companion README and CHANGELOG, core CHANGELOG 0.4.0, compatibility.

**Phase 6 (core 0.4.0, `openppc-online` 0.1.0): committed on `stagging` as `c611a72` (core boundary), `9d4ebe8`
(the companion) and `30ad245` (docs).**

- Findings while building:
  - The plan's "CSP header on every response" broke the engine: a worker takes its policy from its own script's
    headers, so `engine-worker.js` inherited the page's and couldn't import Pyodide from its blob ("The checker
    could not start"). The header now goes on the page only, which matches openppc.si (its policy is only the
    meta tag); a test asserts the files carry none, and the browser test waits for the engine and runs a real
    audit, not the precomputed sample.
  - On Windows, one large write to a loopback socket can stall; the server writes in 64 KB chunks.
  - The wheel build needs the README, so the companion's README and threat model moved into commit 2.
- Checks: ruff and mypy clean; 402 core tests; 43 companion tests and its browser test; each commit's suites run
  from a clean checkout of the index. The wheel, built locally and installed into a fresh venv with the core
  wheel, serves its packaged copy of the app (six files) and prints its version. The app served from 127.0.0.1
  reached Ready in Chromium and audited a sample file.
- Not verified: the new CI job and both release workflows (they run only on GitHub; PyYAML isn't installed here,
  so the workflow files weren't even parsed locally); the companion on Python 3.10, macOS and Linux; the wheel's
  dependency resolution, since the core is still 0.1.10 and the pin wants 0.4.
- Owner:
  - Bump the core to 0.4.0 before releasing either package (the companion's release job refuses otherwise).
  - On PyPI, add a trusted publisher for `openppc-online` (workflow `release-online.yml`, environment
    `pypi-online`), and create that environment on GitHub, limited to tags `openppc-online-v*`.
  - Run the formal security review of the companion before its first release.
  - Merge, push and release, as before.

**What's left after Phase 6 (Oct 13, 2026), and what can run without the owner.**

- 4c needs question 7 (host and cost cap) and the `chatgpt-app` branch, which stays untouched until then.
- Phase 8 needs question 10 (developer tokens, test accounts) for its recorded responses and live smoke.
- Phase 9 needs question 10 (store accounts) to list anything.
- Phase 7 can run, except the home page section (question 9), the openppc.si docs page (the owner approves
  companion copy on the site) and the design-partner gate (skipped). So Phase 7 is next, without those three.

**Phase 7 (`openppc-online site`): execution plan after four critique rounds.**

Draft: port `siteaudit/` whole, the render pass, the Site view and the docs page in one go, as section 6 lists.

Round 1 (engineer):
- Four slices, each releasable on its own: **7a** the crawl, checks and report with no browser (0.2.0); **7b**
  `--render` (Playwright, axe, the guard proxy, consent and events, lab vitals, the Docker `render` image);
  **7c** the `app.js` split and the Site view, which brings the local app's first job API; **7d** docs. 7a goes
  first because 7b and 7c both stand on it.
- 7a is about 2,700 lines from the fork, so it lands as five commits of reviewable size: the network guard; the
  page reader and crawler; the checks, tags, scoring and report; rule packs, baselines and schemas; the command.
- The report uses only the stable engine API. The fork's `_text_numbers` imports the tracer's private `NUM`
  pattern; ours registers the numbers `trace(text, [])` finds instead. `--format html` uses the core's one HTML
  renderer (ADR-5), so `formats.to_html` joins ADR-2's stable list, which is additive before 0.4.0 ships. A new
  companion fitness test fails on any `openppc` import outside that list.
- The rulebook: the core's rulebook test imports every `code_ref`, so `site-*` rows there would make the core's
  tests import the companion. The rows go in `companion/rulebook/rules.csv`, with the same columns, checked by
  a companion test the same way, plus a test that every rule in `checks.RULES` has a row and every row a rule.
- The render data types (`Observation`, `Vitals`, `Rendered`) and constants the checks and report read come in
  7a; the browser itself, and `GuardProxy`, in 7b.
- `test_the_companion_has_no_http_client_yet` becomes the real fitness function 10 for `site`: `http.client`,
  `ssl` and `socket` only in `siteaudit/net.py`, `urllib.request` only in `siteaudit/crux.py`.

Round 2 (security):
- `--post-to` (F13): https, or http only to a loopback address; the request goes through the guard (so a
  private address needs `--allow-private`, and metadata addresses never open); one POST, no redirects
  followed. The report and the console name the host only, never the full URL: webhook URLs carry their secret
  in the path (Slack's do).
- The CrUX key is a sentinel in a test: never in the markdown, JSON, SARIF, HTML, console or an error.
- Fitness function 9 for `site`: every host name the guard resolves is recorded; a crawl touches the site's
  host and the external links' hosts only; CrUX's host only with a key; the webhook's only with `--post-to`.
- Fitness function 12: the fork's address table (private, link-local, metadata, CGNAT, mapped, 6to4,
  Teredo), a name with one private address among public ones, a redirect to the metadata address, and a
  compressed bomb, ported test by test. The proxy's case comes with 7b.
- Text from the site reaches the report only inside code spans or escaped by the HTML renderer; secret-looking
  query values are masked in every format (the fork's `redact`).

Round 3 (product and delivery):
- What users get in 7a: `openppc-online site https://example.com` prints a scored audit of SEO, links, indexing,
  structured data, HTTPS, AI crawlers and the tags in the HTML, every number traced, with `--fail-on`,
  `--baseline`, `--config`, `--format md|json|html|sarif`, `--crux-key` and `--post-to`. Exit codes: 0, 1 bad
  input, 2 a finding at `--fail-on`, 3 the report failed its own check, 4 inconclusive.
- Docs stay in `companion/` (README, CHANGELOG, THREAT_MODEL); nothing on openppc.si or the core README.
- F19: the fork's QA site becomes a test fixture, and its 31-case matrix becomes parametrized command tests
  (the 2 render cases wait for 7b). The two cases that failed in the fork's last run were B5 and B7, fixed later
  in the fork: a blocked site exits 4, and a site with soft 404s passes against its own baseline. Both are tests.

Round 4: user-agent and politeness defaults stay the fork's (`OpenPPC-SiteAudit`, two at a time, 0.5 s apart,
robots.txt and Crawl-delay obeyed); the user agent names `openppc-online` and its version. A further pass changed
nothing material, so this is the plan.

7a commits, each tested in isolation:

1. Core: `formats.to_html` declared stable in ADR-2. Companion: the import allowlist test.
2. `siteaudit/net.py` (the guard and fetch) with fitness functions 10 and 12.
3. `page.py` and `crawl.py`: robots.txt, sitemaps, caps, politeness, with the crawler tests.
4. `tags.py` and `signatures.json`, `checks.py`, `triage.py`, `crux.py`, the render data types, `report.py`,
   `packs.py`, the schemas, the example rule packs and the companion rulebook, with their tests.
5. `openppc-online site`: the command, `--post-to`, fitness functions 9 and 11, the QA matrix, the CI and
   wheel checks, and README, CHANGELOG 0.2.0 and the threat model's crawler section.

**Phase 7a: committed on `stagging` as five commits, `da3b05f` to `1cff012`.** Core 402 tests, companion 196,
ruff and mypy clean; each commit tested from a copy of exactly what it staged. Added on the way: a test that the
site's own text (a quoted title, hostile URLs) never becomes markup in the md or HTML report.

- Unverified: CI itself, Linux and macOS, Python 3.10, and the wheel's contents (no build backend locally; the CI
  wheel check now asks for `signatures.json` and both schemas).
- Owner: the companion's version bump to 0.2.0 (CHANGELOG says Unreleased 0.2.0, the package still 0.1.0); the
  security review of the crawler, with THREAT_MODEL's new section; noticed, not changed: the core's own schema
  tests `importorskip("jsonschema")`, and the core's dev extra lacks it, so CI skips them.

**Phase 7b (`--render`): execution plan after four critique rounds.**

Draft: port the fork's `render.py`, `GuardProxy`, `follow()`, axe-core, the flags and the e2e test in one commit,
plus the Docker `render` image.

Round 1 (engineer):
- Three commits. (1) `GuardProxy` in `net.py` and `follow()` in `crawl.py`: no browser, tested in the regular
  suite. (2) The browser pass: `render.py`, the vendored `axe.min.js`, the `render` extra, the e2e tests.
  (3) The command: the flags, `site.run`, the rulebook's 12 `planned` rows back to `live`, the "needs a browser,
  which this version doesn't run" text back to "needs `--render`", QA cases SITE-29 and 30, docs and CI.
- Fitness function 10 grows: `socketserver` (the proxy) only in `siteaudit/net.py`, and `playwright` (a browser
  is a network client) only in `siteaudit/render.py`.
- Playwright is optional: `render.py` imports it at the top in `try`/`except ImportError`, as the fork does, and
  `--render` without it fails before the crawl with the install line.
- Every new input is read before the crawl: `--render-url` must be a page of the site (`checks.same_site`), the
  `--screenshots` folder is created, and the browser is started once (`preflight`).

Round 2 (security):
- Fitness function 12, the proxy's case: `GuardProxy` answers 403 to a `CONNECT` or plain request for a private
  or metadata address, tested without a browser; the fork's reset-tunnel test comes too.
- The browser reaches the network only through the proxy, loopback included; QUIC and non-proxied WebRTC UDP
  off; service workers blocked; downloads refused. The e2e test with a default guard sees 127.0.0.1 refused.
- The proxy listens on 127.0.0.1, only during the browser pass, with no password: a program on this computer
  could use it then, but reaches nothing it couldn't reach directly. Accepted, in THREAT_MODEL.
- `axe.min.js` is vendored unmodified with its MPL-2.0 header; a test pins its SHA-256, and
  `companion/THIRD_PARTY_LICENSES.md` names it (shipped in the sdist; the file's own header travels in the
  wheel).
- Text from rendered pages (axe targets, dataLayer event names) reaches the report through `code()`; the e2e
  test plants a hostile dataLayer event.
- Fitness function 9 for `--render`: the e2e test records every host the proxy connects to: the site's and the
  hosts its pages load, nothing else.
- Screenshots are saved only with `--screenshots`, and may show what the page shows; the README says so.

Round 3 (product and delivery):
- The fork's flags: `--render`, `--render-pages`, `--vitals-pages`, `--render-url`, `--consent-selector`,
  `--screenshots`. Install: `pip install "openppc-online[render]"`, then `playwright install chromium`.
- CHANGELOG: an Unreleased (0.3.0) section, since each slice is releasable alone.
- CI: the `web-app` job already installs Chromium and runs `pytest -m e2e companion/tests`, so the render tests
  run there; the wheel check adds `axe.min.js`.
- Docker moves out of 7b: the companion has no image, isn't on PyPI, and a new distribution channel is the
  owner's call. Owner question, with the docs in 7d.

Round 4: Ctrl-C during the browser pass keeps the crawl; `follow()` runs only when the crawl wasn't cut short,
and `--max-time` counts both passes. The QA cases run with `--vitals-pages 0` to stay short. A further pass
changed nothing material, so this is the plan.

**Phase 7b: committed on `stagging` as three commits, `3de0607` to `a2cc931`.** Core 402 tests, companion 209,
companion browser tests 4 (in Chromium, about 2.5 minutes), ruff and mypy clean; each commit tested from a copy of
exactly what it staged, the browser tests included.

- `axe.min.js` checked byte for byte against npm's `axe-core@4.10.3` (SHA-256 `880970c0…a68bb`, pinned in a test).
- Fitness function 9 in Chromium: the only names resolved are the site's and the two tag hosts its page loads.
- Deviation: SITE-29 keeps the fork's `--vitals-pages 2` (that case exists to test it); SITE-30 runs with 0.
- Unverified: CI, Linux and macOS, and the wheel's contents (the CI check now asks for `axe.min.js`).
- Owner: the version labels. The CHANGELOG says Unreleased 0.2.0 (7a) and 0.3.0 (7b), each slice releasable alone,
  while this plan's headers say Phase 7 is 0.2.0 and Phase 8 (`fetch`) 0.3.0; release 7a and 7b together as
  0.2.0, or renumber Phase 8. Also the companion Docker `render` image (moved out of 7b), and the security review,
  which now covers the proxy and the browser.

**Phase 7c (the Site view): execution plan after four critique rounds.**

Draft: as the fork does it. Split `web/app.js` into ES modules, add `site-view.js` and `local.js` to `web/`, put a
"Site" tab in the hosted rail that tells openppc.si visitors to install the companion, and port `localapp.py`'s
job API: uploads written to a temp folder, the form turned into argv and parsed by the command's own parser.

Round 1 (engineer):
- No split, and no change to the hosted app. `app.js` is a classic script, so its top-level declarations (`h`,
  `reportNode`, `download`, `toast`, `route`) are visible to any classic script loaded after it. A new
  `companion/openppc_online/local/site.js`, injected only by `openppc-online app` (like `local.js`), builds the
  view from those. The split would rewrite 1,569 lines openppc.si serves for a view only the local copy shows,
  and a "Site" tab on openppc.si is companion copy on the site (question 9).
- The cost of reusing `app.js` this way: renaming one of those helpers would break the local view without
  anyone noticing. A companion test therefore checks that every `app.js` name `site.js` uses is a top-level
  declaration in `web/app.js`, and the browser test runs the view.
- Navigation: `route()` rewrites any hash it doesn't know to `#home`, so the view has no hash of its own. A
  "Site" button goes into the rail after Audit; opening it hides every view. Any other rail click closes the
  Site view and calls `route()` itself, because clicking a link to the hash already showing fires no
  `hashchange`. There is no deep link to the view, which is accepted.
- The server calls `site.run` with keywords instead of going through argv and the parser: typed, with no flag
  strings, and `run` already checks every input before the crawl.
- Uploads: temp files would put their paths in the report (pack names, the baseline's name) and in errors. So
  `packs.load` and `triage.read_baseline` take (name, text) pairs instead, the command reads its files itself,
  and the app writes nothing to disk.
- Stop: the job's progress callback raises `KeyboardInterrupt("stopped with the Stop button")`, as Ctrl-C would.
  The crawl and `site.run` record the exception's own text, with "stopped with Ctrl-C" when it has none. Like
  Ctrl-C, Stop still produces a report of what was crawled.
- Generic `/api/jobs` with `"kind": "site"`, so `fetch` (Phase 8) joins without a new route.

Round 2 (security):
- The new method is POST, for `/api/jobs` and `/api/jobs/<id>/stop` only. Any other POST address gets 404;
  PUT, DELETE, PATCH and OPTIONS still get 501; no answer ever carries an `Access-Control-*` header.
- Checks run in this order: the Host name; then `Origin`, which, when present, must be this server's own; then
  the token; then `Content-Type: application/json`; then a `Content-Length` of at most 20 MB. Only then is the
  body read. A request turned away earlier has its connection closed unread, so no body from a page without the
  token is ever read.
- Cross-site POST: the custom token header and the JSON content type each force a CORS preflight, and this server
  never allows one. The `Origin` check is a second lock behind that.
- Fields are type-checked, with the command's limits (`max_pages` ≥ 1, `max_time` > 0, booleans as booleans);
  a mistake gets 400 and a sentence.
- One job runs at a time; a second gets 409 with the running job's id. The last 4 finished jobs are kept in
  memory and never written to disk.
- Fitness function 11 covers the API: the CrUX key travels in the request body only, and a sentinel key never
  shows in a job's view, progress, error or report.
- `--screenshots` and `--post-to` stay command-line only: one writes to disk, the other sends the result to a
  third host.
- An uploaded file's name is cut to its base name, without control characters, at most 100 characters. It
  reaches the report only in code spans, as the command's file names already do.
- `app.py` gains no network import: it calls `site.run`, and the fitness function 10 map is unchanged.

Round 3 (product and delivery):
- The form follows the fork's fields:
  - the URL, max pages and minutes ("No limit" by default, as on the command line)
  - fast, check links to other sites, allow private addresses
  - load pages in Chromium (`--render`), with render URLs and a consent selector
  - a CrUX key
  - rule packs and a baseline
- The view says plainly that it connects from this computer to the site and the hosts it links to.
- The render box is disabled, with the install line, when `/api/info` says Playwright is missing.
- Results show:
  - the finding count, the high-severity count and any reason the scan was inconclusive
  - downloads as .md, .html, .json and .sarif
  - the report, rendered by the app's own sanitized `reportNode`
  - "Audit another site"
- Tests:
  - the job API over HTTP against the local fixture sites: every check above, Stop, 409, eviction and the
    sentinel key
  - a Chromium test that fills the form, sees the report, downloads the .md and stops a run
- Three commits:
  1. pack and baseline text in, Stop's wording out, with no behaviour change for the command
  2. the job API with its tests, and THREAT_MODEL's app section rewritten for POST
  3. `site.js` with its tests, plus README and CHANGELOG

Round 4: when a job is already running, which happens after a page reload, the view attaches to it from the 409
answer instead of failing. The page polls every 800 ms, and a job's view carries only the latest progress line
until the job ends. A further pass changed nothing material, so this is the plan.

**Phase 7c: committed on `stagging` as three commits, `389d17e` to `803c14a`.** Core 402 tests, companion 244,
companion browser tests 6 (the Site view's included), ruff and mypy clean; each commit tested from a copy of
exactly what it staged.

- Found on the way and fixed in the third commit: the app server wrote in 64 KB pieces, and on this Windows
  machine about one page load in five stalled for half a minute and came up without `app.js`. It happened with
  the server from before 7c too. A probe of 16 loads at each size failed 3 at 64 KB and none at 16 KB or 8 KB, so
  the server now writes 8 KB.
- Checked by eye: screenshots of the form, the result and a 375 px phone. They showed a stray "null" above the
  result, now fixed and covered by the browser test.
- Not offered in the app, as planned: `--post-to`, `--screenshots`, `--max-per-pattern`, `--render-pages` and
  `--vitals-pages`; the app uses the command's defaults for the last three.
- Unverified: CI, Linux and macOS, and the wheel's contents (the CI check now asks for `site.js` and `site.css`).
- Owner: the security review now covers the job API too.

**Phase 7d: the companion part is committed as `8d52884`,** the README's usage note (who the crawler says it is,
and that robots.txt rules for `OpenPPC` apply). The openppc.si docs page and the home page section wait for
question 9.

**What is left, and what it waits on:**

- **4c:** question 7 and the `chatgpt-app` branch.
- **Phase 8 (`fetch`):** its contract tests are meant to run on recorded, scrubbed API responses, and its smoke
  workflow on the owner's test accounts. Both need question 10. Writing the clients against fixtures built from
  the API documentation is possible, but it is a weaker test than the plan asks for, and is the owner's call.
- **Phase 9:** the store listings need question 10. The extension can be built and tested here (Node is
  installed). The WordPress plugin cannot be tested on this machine (no PHP); only CI would test it, and nothing
  is pushed.

The owner chose the extension only (Oct 13): the WordPress plugin and the store listings wait.

**Phase 9, the Tag Inspector extension: execution plan after four critique rounds.**

Draft: port the fork's `extension/` (a `webRequest` listener in a background worker that records every request
and tag POST bodies per tab into session storage; a popup that summarizes them; `match.js` on the shared
`signatures.json`), with `activeTab` and per-site optional host permissions instead of `<all_urls>`.

Round 1 (engineer):
- The draft's two halves don't fit together. `webRequest` reports a request only when the extension has host
  permission for its URL, and the tags live on third-party hosts (google-analytics.com, facebook.net,
  bat.bing.com). With `activeTab` or a per-site grant, the listener sees the site's own requests and none of its
  tags. The fork needed `<all_urls>` for exactly that reason.
- Instead, read the page on click. On the toolbar click, `activeTab` plus `scripting` runs a function in the page:
  - `performance.getEntriesByType('resource')` lists every address the page has loaded since it opened, third
    parties and beacons included.
  - The dataLayer gives the events pushed to it and Consent Mode's `default` and `update` commands, as the crawler's
    render pass reads them.
  - The DOM gives the SEO basics.
- That removes `webRequest`, `storage`, every host permission and the background worker. Nothing is recorded
  between clicks, and it works on a page that was open before the extension was installed, so the fork's "reload
  the page first" step goes.
- The cost, said in the popup and the README:
  - The browser's resource list keeps the first 250 entries unless the page asks for more.
  - Requests made from inside other sites' frames aren't listed.
  - Events batched in a POST body are missed; the dataLayer usually names the same events.
- Lives in `companion/extension/`; the companion's wheel doesn't ship it. `signatures.json` is a committed copy,
  and a test fails when it differs from the crawler's.
- One file of tag cases (`companion/tests/tag_cases.json`), checked against `tags.py` by pytest and against
  `match.js` by `node --test`, so the two can't drift apart. pytest runs the Node tests when Node is installed,
  so `pytest companion` covers everything; the CI runner has Node.

Round 2 (security):
- The manifest asks for `activeTab` and `scripting` only: no host permissions at install or later, no
  `webRequest`, no storage, no background. The extension pages' policy has `connect-src 'self'`, and the only
  fetch is of the bundled `signatures.json`.
- A test fails if any script uses XHR, `sendBeacon`, WebSocket or EventSource, names an outside address,
  `fetch`es anything but `chrome.runtime.getURL`, or writes `innerHTML`.
- The page is untrusted. The resource list and the DOM are read in the extension's isolated world, where page
  scripts can't patch the functions used. The dataLayer has to be read in the page's own world, so the page can
  answer there with anything it likes. So the popup checks and caps everything it gets: strings only, 100
  characters each, at most 3,000 addresses and 200 events, and it uses `textContent` only.
- Fitness function 9: the extension contacts no host. The browser test routes every request, fails any it
  didn't expect, and checks that only the fixture page's own requests were made.

Round 3 (product and delivery):
- The popup shows:
  - the tags found, each with "script loaded" and "sent data"
  - the events each tag sent, from the addresses, plus the dataLayer events
  - the consent banner, and Consent Mode on or off, with its default and update states
  - the cookieless pings sent before consent
  - unknown third parties
  - the page basics
  - a line pointing to `openppc-online site --render` for the full audit
- Tests:
  - Node: the shared tag cases, plus the fork's summary tests
  - Chromium: the extension loaded unpacked, a fixture shop page served through Playwright's request routing (no
    DNS, no network), and the popup's own code run against it. The test copy of the extension gets one host
    permission for the fixture's address, because a test can't click the toolbar to grant `activeTab`. That
    change lives in the test's copy only.
- Docs: `companion/extension/README.md` (install unpacked, package, the permissions, the listing text with a
  "collects nothing" disclosure), a section in the companion README, the CHANGELOG, and THREAT_MODEL's third
  section.
- Icons and the store submission wait for the listing, which needs question 10.

Round 4: two commits.
1. The shared tag cases and the matcher (`match.js`, the copied `signatures.json`, the Node tests and the pytest
   wrapper).
2. The extension (manifest, popup, the page reader), the Chromium test, CI, and the docs.

The manifest's version starts at 0.1.0, and the owner bumps it. A further pass changed nothing material, so this
is the plan.

**Phase 9 (the extension), committed locally on `stagging` (Oct 13), not pushed:**

1. `59abc0c`: the matcher. `extension/match.js` plus a `signatures.json` copy; 39 shared cases in
   `tests/tag_cases.json`, checked by `test_tag_cases.py` against `tags.py` and by Node against `match.js`.
2. `f61c7f6`: the extension:
   - the manifest, `inspect.js` (the reading and its clean-up), `view.js` (text nodes only), `popup.js` (5 seconds
     of patience), the popup HTML and CSS, and a README with install steps, limits, permissions and a listing
     draft
   - static tests, Node tests of the clean-up, and a Chromium test (offline, any unexpected request fails it)
   - THREAT_MODEL's third section, the companion README section, CHANGELOG Unreleased (0.4.0), and the CI comments

Found while building:
- Playwright's routing also answers the extension's own `chrome-extension://` files, so the test routes `http(s)`
  only.
- `gtag()` pushes `arguments` objects, so the page reader takes entries by index, not as arrays.

Still open for Phase 9:
- icons, screenshots and the store submission (question 10)
- the WordPress plugin (no PHP here)
- CI on Linux, which hasn't run (nothing is pushed)
- a manual check in a real Chrome profile with the toolbar click, which no test can make

**Oct 13, second pass: everything still buildable, after the owner's answers.** The owner said: "complete all you
can do"; questions skipped stay on hold. Question 7 and the accounts (question 10) are on hold; 4c and the
recorded API responses wait for them. PHP 8.3.33 is now installed here (winget, user scope).

Order:
1. The WordPress plugin, since PHP is ready now.
2. Phase 8's `fetch`, the largest piece.
3. The openppc.si drafts, last, so they describe only what was built.

**A. Phase 9's WordPress plugin, after four rounds.**

Draft: port the fork's `wordpress/openppc-site-check/` (five Site Health checks, one PHP file) and its stub test,
and add CI on PHP 7.4 and 8.3.

Round 1 (engineer):
- The fork's text tells users to run `openppc site`; the command is `openppc-online site`.
- The fork registers all five as direct tests, so opening Site Health waits up to 10 seconds per page fetched.
  - The four that read a page become async tests: `has_rest`, a REST route each under `openppc-site-check/v1`,
    and `async_direct_test` for WP-CLI. That needs WordPress 5.6; the plugin already asks for 5.8.
  - The indexing check reads an option, so it stays direct.
- The plugin runs `signatures.json`'s `source` patterns with PHP's PCRE; the crawler runs them with Python's `re`.
  `tag_cases.json` gains `in_source` cases that both must pass.
- Tests:
  - The stub test stays a plain PHP script, so the tests need no Composer packages. pytest runs it when PHP is
    installed, as it runs Node for the extension.
  - CI runs it on 7.4 and 8.3, plus PHPCS with the WordPress standards.
- Before it counts as done, a real WordPress check on this machine (a scratch copy, nothing committed):
  - WordPress with the SQLite integration, served by `php -S`, its download checked against wordpress.org's
    checksum
  - the plugin activated, Site Health opened in Chromium as an administrator
  - Plugin Check run on it with WP-CLI

Round 2 (security):
- Escape every string WordPress prints: labels too, not only descriptions.
- Each REST route's permission is `view_site_health_checks`, the capability Site Health itself needs; WordPress's
  REST nonce covers the request.
- It fetches only `home_url('/')` and `/robots.txt`, at most 2 MB each, each once per request.
  - TLS verification follows core's `https_local_ssl_verify` filter, as Site Health's own loopback test does.
    Recorded as accepted in THREAT_MODEL: the request goes to the site itself.
- A pattern that fails (PCRE's backtracking limit) counts as no match.
- It stores nothing, adds no settings, and leaves nothing behind to uninstall.
- PHPCS with WordPress-Extra covers escaping, nonces and sanitising. Its Composer packages are pinned in
  `companion/wordpress/composer.json` and its lock file, which stay out of the plugin's zip.

Round 3 (product and delivery):
- `readme.txt` for WordPress.org: MIT is GPL-compatible. "Tested up to" names the version actually run here.
- The folder that ships is `companion/wordpress/openppc-site-check/`; the tests live in `companion/tests/php/`.
- A test keeps the plugin's `signatures.json` copy identical.
- Docs: a THREAT_MODEL section, a companion README section, the CHANGELOG.

Round 4: two commits.
1. The plugin, its tests and the shared cases.
2. CI, PHPCS and the docs.

The real WordPress check comes between them, and anything it finds goes into commit 1.

**A, done: committed locally on `stagging` (Oct 13), not pushed.**
- `3d3abcc` The plugin, its PHP test, `test_wordpress.py`, and the shared cases. `tags.py` reads the patterns
  ASCII-only (Python's `\d` matched Arabic-Indic digits; PHP's PCRE doesn't), with an `in_text` list of cases both
  must pass.
- `c40c841` CI and docs:
  - a `wordpress` job on PHP 7.4, 8.3 and 8.5, with PHPCS on 8.3
  - PHP 8.3 in the companion job, so pytest runs the PHP tests on Windows too
  - setup-php 2.40.0 pinned by commit; Dependabot for Composer
  - THREAT_MODEL, README and CHANGELOG sections
- The real WordPress check (scratch WordPress 7.1.3 with SQLite, in `.cache/wp`):
  - Site Health as admin showed all five checks, at desktop width and at 390 px (no sideways scroll)
  - "Tags but no consent banner" with GA4 and Meta Pixel; "has a consent banner: Cookiebot" once Cookiebot was added
  - REST answers 401 to a visitor
  - Plugin Check 2.1.0: no errors, after one annotated line for core's `https_local_ssl_verify` filter
- PHPCS (WordPress-Extra plus PHPCompatibilityWP 7.4+) found only alignment; fixed, now clean.
- Changed from the plan:
  - `php -S` hung here after its first request (cause not found), so the scratch server runs `php-cgi` per
    request behind a threaded Python server. In CGI mode `php-cgi` ignores `-c`; `PHPRC` sets the ini.
  - No `composer.lock`. Composer can't reach Packagist here: the firewall's TLS interception isn't in PHP's CA
    file, verification stays on, and exporting the Windows roots was blocked. So `composer.json` pins every package
    exactly (all eight, transitive ones included), and PHPCS ran here from git checkouts of those exact tags.

**B. Phase 8, `openppc-online fetch` on documentation-based fixtures, after four rounds.**

Draft: port the fork's three clients (`google_ads_api.py`, `microsoft_ads_api.py`, `meta_ads_api.py`) into
`openppc_online/fetch/`, add `openppc-online fetch google|microsoft|meta`, and test each on fixtures written from
its API documentation.

Round 1 (engineer):
- One HTTP module, `fetch/http.py`, is the only one that connects. It holds fitness function 10: each platform's
  allowlist of method plus host and path, checked before connecting. Anything else raises: Google's token
  endpoint and `searchStream`; Microsoft's token, report submit and poll, and the download host the poll names;
  Meta `GET` only. `test_boundary` names it.
- It follows no redirects (urllib follows them by default). Meta's `paging.next` and Microsoft's download URL come
  from the API, so they pass the allowlist like any other address.
- Output: the files the core's templates read. A test runs the core's audits on each download, so the formats
  can't drift. Microsoft's files need the core's Microsoft reader, which Phase 3 added.
- The fixtures:
  - follow each API's documented shapes: Google's searchStream batches, Microsoft's ReportRequestStatus and its
    CSV, Meta's insights and paging
  - cover pagination, quota, the errors named in the plan, and Performance Max (search terms Google doesn't
    report)
  - get swapped for recorded, scrubbed responses when the accounts exist (question 10)
- The API version calendar: a table in code of each pinned version and its sunset date, with a test that fails 60
  days before one. The dates come from each platform's published schedule, checked on the web while building;
  any that can't be confirmed is marked as an estimate.

Round 2 (security):
- Fitness function 11:
  - every credential is set to a sentinel value, and the test fails if it appears in a file, stdout, stderr, an
    error, the report or an app API response
  - error bodies are never echoed: they are mapped to words, and unknown ones give the HTTP status alone
- Credentials:
  - the command line reads environment variables only
  - in the app, credentials come in the job's POST body and live in memory for that run
  - the keychain extra waits
- Files are written only inside `--out`, under fixed names; an existing file is replaced only with `--force`.
- Read-only by construction: the allowlists hold no mutate endpoint, and a test fails if one is added.

Round 3 (product and delivery):
- Errors in words: a revoked token, a test-only developer token, a missing manager ID, the daily quota, and an
  OAuth app in Testing whose refresh token expired after 7 days.
- The Download panel in the app is a second job kind on `/api/jobs`, with its own form.
- Docs: the companion README, THREAT_MODEL's `fetch` section, the CHANGELOG.
- The gate (3 design partners) is skipped, as the owner decided. The live smoke workflow waits for the accounts.

Round 4: commits, each tested from the staged snapshot.
1. The HTTP module, its allowlists and the calendar.
2. Google.
3. Microsoft.
4. Meta.
5. The `fetch` command and its feed-the-audits test.
6. The app's Download panel.
7. The docs.

The order may merge commits where they are small.

**B, done: seven commits locally on `stagging` (Oct 13), not pushed.**
- `c59586e` `fetch/http.py` (the allowlists, no redirects, 200 MB answers, error codes only), `files.py` (fixed
  names inside `--out`, written whole, `--force`) and `versions.py`.
- `e7a858b` Google: four files. Performance Max's search terms come from `campaign_search_term_view`, without a
  keyword segment (which would drop them); `search_term_view` leaves them out.
- `3c647c9` Microsoft, through the REST Reporting API (`/Reporting/v13/GenerateReport/Submit` and `/Poll`): three
  files; polls back off from 2 to 30 seconds and give up after 10 minutes; the download address is let through
  once, https on a host name, without credentials; one zip member, its size checked first.
- `b05a70d` Meta: GET only, the token in a Bearer header; a next page only on the same list; without
  `--conversion` the error lists the action types with their counts.
- `231e166` The command, whose files `openppc audit` runs on in the test, for all three platforms; `openppc fetch`
  now names it.
- `9739c05` The app's Download view: a second job kind, its credentials in the request only and cleared when it
  ends, Stop during Microsoft's polling, a 409 that names the running kind, and "Audit them here". In Chromium, the
  browser checker read all four Google files as the exports they stand for. The form empties its credentials after
  a successful download. The phone rail fits seven items at 360 px.
- `9844b34` The docs: README fetch section (every environment variable), THREAT_MODEL `fetch` section (every cited
  test exists), companion CHANGELOG Unreleased (0.5.0).
- Checked on the web while building (Oct 13): Google v25's `campaign_search_term_view`; Microsoft's REST paths,
  body and ApiFaultDetail errors (a Q&A answer naming other paths was wrong). Meta's Bearer header rests on SDKs
  and an accepted Stack Overflow answer, not a Meta page; THREAT_MODEL says so.
- Not verified: any real account (question 10), CI, Linux and macOS.
- Seen once: SITE-03 failed in one full run and passed in four reruns (untouched site-audit code; timing). And one
  `test_app.py` failure while two suites ran at once, not seen again.
- Owner:
  - The version label. The CHANGELOG says 0.5.0, after 0.4.0's extension and plugin, where this plan's header says
    Phase 8 is 0.3.0.
  - With all four Google files loaded, the hosted app greys out "Account read" ("Your last two exports can't be
    compared"), since it reads the last two files. Removing the others works; a hosted-app change if it matters.

**C. The openppc.si drafts (question 9), after three rounds.**

Draft:
- the home page's "Optional companion" section
- a docs page for the website check

Round 1:
- Nothing in the companion is released yet. The section carries a "Soon" label, as "Rules · Soon" does, and the
  docs page says "not released yet" where it says how to install. The copy stays true if `stagging` is merged
  before the release.
- The section keeps the core promise apart: "a separate install that goes online when you run it".
- Every claim it makes is backed by a test already in the companion.

Round 2:
- One docs page, `/docs/online/`, covering:
  - the website check, with the Site view
  - the Tag Inspector and the WordPress plugin, each linked to its folder
  - `fetch`
- The home section gets three short cards and a link to that page.
- The site's own tests (sitemap, nav, links) must pass.

Round 3: one commit, its message saying it waits for the owner's approval of the copy.

**C, done: `c53b97f` locally on `stagging` (Oct 13), not pushed; the copy waits for the owner's approval.**
- Home: an "Optional companion · Soon" section between Privacy and the FAQ, with three cards (site check,
  downloads, extension and plugin), each linking to its part of `/docs/online/`.
- `/docs/online/`: the four pledges, the app's Site and Download views, `site`, `fetch`, the Tag Inspector, the
  WordPress plugin, and install ("not released yet", with `pip install openppc-online` once it is). The docs
  index and llms.txt list it; the golden `site-seo.txt` gains its title, description and h1.
- The site's tests and the axe scan (desktop and phone) pass; seen in a browser at desktop width.
- Not in the header nav, to keep it as it is. The page links only to the repository's root, not to
  `companion/`, which isn't on `main` until the merge.

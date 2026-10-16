# Site audit parity with PageSpeed Insights and Lighthouse (v5, final)

Status: final. Four critique rounds, stopped when every reviewer found nothing that would change scope, order,
estimates or decisions (appendix B). Local and untracked, like `SCOPE_WIDENING_PLAN.md`.
Owner decisions are marked **[Owner]**.

Progress (local commits on `stagging`, nothing pushed):
- **R1: built.** `net.fetch` and CrUX through the guard, Lighthouse's throttling, tag hits answered during speed
  loads, `--crux`/`--crux-key`, `--psi`/`--psi-key`, `--single`, the speed score as Performance, real visitors as
  PSI shows them, "All Lighthouse audits" with the parity matrix, the app's ticks, rulebook, docs (up to `428bb88`).
  PSI now starts once robots.txt is read (`0cdcf15`). Open: the release's security review of the diff.
- **R2: built, except what waits on the owner.** Ad click IDs through server redirects (`d93aeb1`), plain words and
  the glossary (`364287f`), the client summary with the quick check's two buttons, Re-check, agency name and print
  layout (`eece875`). Not built: the page screenshot on the summary (the app offers no screenshots yet), the "costs
  the ads" lines (Q3: owner said leave them out for now), the U5 check (Q2).
- **Gate before R3: owner chose "review and proceed".** A review of R1+R2 found 13 issues; all fixed in `e9a1875` (PSI stop and Ctrl-C, Python 3.10 timeout, CrUX error numbers, malformed answers, key characters,
  the app's quick check, Re-check size, re-run settings, gauge, `psi` field, ad-click robots.txt); the iframe and
  worker gap in answering tag hits is documented, not closed.
- **R3 chunk A: built (`41f6a28`).** Trace capture and Lighthouse 13.5 metrics (FCP, LCP, TBT, TTI, CLS, TTFB, Speed
  Index), Lighthouse's quiet wait, Lighthouse CI's representative run, range and stability, `--runs`, near-line
  rule for one load, new headless with the sink for Chromium's calls home (the search preconnect off, the AI Mode
  check sent to `google.invalid`). Calibration on web.dev mobile, this machine: Lighthouse FCP 3355, TBT 2988, SI
  3778, TTI 16988; OpenPPC FCP 3206, TBT 2151, SI 3418, TTI 16551.
- **R3 chunk B: built (`6336377`).** The OpenPPC lab score, labelled "(uncalibrated)" and outside Performance; the
  benchmark index with Lighthouse's slow-CPU line; the U6 explainer; JSON `score`, `score_label`,
  `rendered.benchmark_index`.
- **R3 chunk C: built, gate green on mobile at 3 loads a side.** Lighthouse attaches to OpenPPC's own browser
  (`lab/lighthouse.py` and `lighthouse.mjs`: puppeteer-core connects over the DevTools port on 127.0.0.1, which the
  guard refuses to every page, to a page in a context behind GuardProxy). The harness (`tests/calibration`), 17
  fixtures, the gate, the proxy gate, a weekly and manual `calibration` workflow (mobile and desktop, 9 loads a
  side). Mobile, this machine, 3 loads a side: 1 miss (TTFB, which runs 5-20 ms over Lighthouse's on small values),
  every score within 1 point of Lighthouse devtools; proxy gate passed (LCP 3252 vs 3266 ms). Found and fixed on
  the way: Windows dropped the end of large files a throttled browser was still reading through the proxy (now
  `SO_SNDBUF` 0 on the browser's side). Not yet, against section 8: HTTPS with HTTP/2, a web font, the HTTP/1.1-only
  host and the tag pages; desktop and 9-load runs. `CALIBRATED` stays False until the workflow is green on both
  devices.
- **R3 chunk D: spike passed on both devices, so R4 takes the trace engine.** `@paulirish/trace_engine` 0.0.65
  (Lighthouse 13.5's pin) bundles with esbuild into one 543 KB IIFE (`companion/calibration/trace-engine.mjs`,
  `npm run build`) and runs in a blank page of OpenPPC's Chromium on an unthrottled load's trace (screenshots
  dropped; 3.4 MB mobile, 6.5 MB desktop at most), simulating as Lighthouse does, in under 2 s a trace.
  `tests/calibration/insights.py` compares it with Lighthouse `simulate`, savings rounded as Lighthouse's audit.js
  rounds them (50 ms): 7 of 17 fixtures match exactly on failing insights and savings within 10%, mobile and desktop
  (the other 10: nothing failing on either side, or the noise below). Savings agree to the rounding step
  (render-blocking 900/850 ms, image delivery 1650/1650 ms and 353/351 KB, big image 9250/9150 ms). Noise: a
  "forced reflow" with no source (about 25 ms, a page with no scripts of its own too) fails on one side in about one
  fixture in eight, seen on Lighthouse's side as well; a one-off LCP-breakdown fail on Lighthouse's side. Found: our
  loads' document requests run slower and noisier through GuardProxy than Lighthouse's (redirect median 54 vs 30 ms,
  outliers to 150 ms; tag-hit answering ruled out), likely the proxy's threads waiting on the Python process while it
  handles the page's DevTools events; Lighthouse's rounding hides it in the savings, and it is the TTFB offset seen in
  C. R4 needs: `capture(raw=...)` (added) for the unthrottled load, the bundle vendored with its licence, and a
  decision on the unattributed forced reflow (show as Lighthouse does, or drop entries with no source).
- **R4 chunk A: built.** `lab/insights.py` and the vendored `vendor/trace-engine.js` (547 KB, built by
  `companion/calibration/build.mjs` with the three licences on top, SHA-256 pinned, rebuilt and compared in the
  calibration workflow): after a page's speed loads, one more at full speed per device, and the engine's insights
  with savings rounded as Lighthouse rounds them, failing ones in the report under each measured page (title,
  savings, failed checks, plain words, up to 5 files or companies), all in JSON (`insights`, `insights_error`,
  `trace_engine`). Forced reflow is shown as Lighthouse shows it. Seen while checking: one blocking-css run gave
  300 ms of savings against Lighthouse's 850 (the next gave 900/900), the proxy-timing noise found in D; spa's
  render-blocking saving sits one rounding step under Lighthouse's (350/400). Next: B, the PPC insights.
- **R4 chunk B1: built.** What each tag costs: the engine also returns each URL's bytes and main-thread time
  (`Extras.ThirdParties.summarizeByURL`, what Lighthouse's third-parties insight counts), summed per
  `signatures.json` vendor (`tags.owner_of`: its tag file or hit, else its hosts) and consent platform, hits the
  load answered left out; a table under the insights, `tag_costs` in JSON. JavaScript errors: the tags and consent
  pass notes `pageerror`s and console errors, not "Failed to load resource" (the guard's refusals would flood it),
  10 a page of 200 characters; `site-js-errors` (tracking, medium), source Lighthouse's errors-in-console. The
  proxy's listen backlog went from socketserver's 5 to 128, a guess at the e2e flakes (a page.goto timeout, and
  once an unexplained "Refused to ..." console line) that a tight loop didn't reproduce. Next: B2.
- **R4 chunk B2: built.** Ad parameters in the browser: after the tags pass, the crawl's `with_ad_params` address
  (only when the crawl asked for it, so robots.txt allowed it) loads in its own context routed whole through
  Playwright: main-frame navigations go on, tag hits and any request carrying `OPENPPC-TEST` to a host the page
  isn't on are answered 204 (the e2e test shows a frame, a blob worker's fetch and a beacon caught); `location.href`
  after SETTLE_MS against what the server kept is `site-ad-params-dropped-js` (medium: a tag that read the address
  first still has the ID). The app's "Ad click IDs survive redirects" fails on either. Consent banner shifts: an
  init script keeps layout shifts and when an accept button first went in (MutationObserver); a shift is the
  banner's when a source is inside it, content moved by its height, or it came within 500 ms of it going in
  (Chrome named `<body>`, not the pushed content, in the test page). At CLS_GOOD or more,
  `site-consent-banner-shift`; the number is in the report's consent line. Next: R5.
- **R5: built.** `--lighthouse FOLDER`: the user's Lighthouse 13 (`lab/lighthouse.folder`, Node checked before the
  crawl) measures the pages `--psi` would (start page and `--render-url` pages, 5 at most, robots.txt-allowed only)
  in OpenPPC's browser through the guard, phone then desktop, simulated throttling, PSI's four categories
  (`render.lighthouse_speed`); results are `Speed` with source "Lighthouse", so the Speed section, scores, audits
  and checks read them as PSI's (the intro says whose Lighthouse ran where); `--render` skips pages it measured;
  refused with `--psi`. Its loads fire tags (THREAT_MODEL, accepted). Budgets: `budgets` in config files (`max`
  timings `fcp lcp tbt cls si ttfb` and `<type>-kb` sizes from `resource-summary`, `min` `speed-score`; `pages`,
  `device`), checked against Lighthouse's result when there is one, else the lab's shown load (timings only); a
  page over a line is a finding of the budget's severity named by its id, so `--fail-on`, `--baseline` and
  suppressions treat it as any pack rule's; a budget nothing measured is an info finding. Example pack
  `landing-speed.json`; rulebook rows `site-lighthouse-local`, `site-budget`. All phases built; open: the
  security and bugbot reviews (owner's call), Q2 and Q4, and `CALIBRATED` stays False until the gate passes.
- **R3 chunk E: the corpus gap closed.** The fixtures are served over HTTPS (a certificate made per run with
  `cryptography`, now in the dev extra) through a Node front end (`tests/calibration/front.mjs`): HTTP/2 for every
  host but `old.test`, which is HTTP/1.1 only (`http1-host`, 18 images); `--plain` keeps the old HTTP/1.1. Chromium
  153 ignores `--ignore-certificate-errors-spki-list` in every form tried, so the calibration's browsers take
  `--ignore-certificate-errors` through a wrapper in `tests/calibration/bypass.py` (test_boundary keeps it out of
  the package). `font-swap`: a generated TrueType font a full em wide, 1.5 s late, rewrapping the text on both
  widths, with a 3 s image holding the load event so neither trace ends before the swap. It found a real
  difference: OpenPPC forgave the input flag for 500 ms from about:blank's viewport event, not the page's, so a
  phone's swap shift could read 0; fixed in `metrics.measure`. Three loads a side: CLS 0.518 / score 79 on mobile and
  0.145 / 94 on desktop, both sides, every run. `tags` (GA4 beacon, fetches, late scroll hit) and `tags-chained`
  (Adobe pixel whose 302 lands a GA4 hit) are published three ways, not gated: hits answered, hits sent,
  Lighthouse; smoke run on mobile: TBT 137 / 170 / 183, TTI 2081 / 2602 / 3327.
- **Reviews done.** Security review and Bugbot over the companion package in four slices (network and app, lab,
  downloads and local views, checks and report): no security findings; one bug (failed PSI/Lighthouse calls hid the
  Web Vitals "needs --render" line), fixed in 6df6e64. The `test_app_jobs` reset flake fixed by a lingering close
  (ffcd8d4). Open: Q2, Q4, and the calibration workflow's run (needs a push).
- **U5 dry run (simulated, not the real gate).** 20 public landing pages, "Check on this computer only", read as
  three non-technical clients (a shop owner who runs her own ads, a B2B marketing manager, a clinic owner). 18
  summaries; 2 pages were judged too broken to summarise by design (Warby Parker: bot protection; Booking: the start
  page didn't load). Found and fixed in c343ae8: the speed answer said Not checked beside a lab score; no overall
  line; accessibility and lab fixes in developer words; "who: tag manager" read as the product; a CLI flag in a fix;
  CLS unrounded; no why-it-differs line. As captured, all four questions at 3 of 3 on 6 of 18 summaries; every miss
  was one of those wordings, now replaced (checked live on casper.com). Open: the overall line said Needs work on all
  18, so it doesn't tell big brands apart; "hidden from search engines" fired on Canva (noindex sent to OpenPPC's user
  agent) and once on Wix (not on a re-crawl), which may overstate what Google sees. Q2 proper still needs the owner's
  review set and real readers.
- **Full local calibration (9 loads a side, 19 pages, both devices).** The gate passed on both with 0 misses, and
  every gated page's lab score equalled Lighthouse devtools'. The proxy gate passed on a phone (LCP 3253 vs 3248 ms)
  and failed on a desktop twice: LCP 426 vs 410 and 422 vs 409 ms against a 3% allowance of about 12 ms, TTFB
  44 vs 33 and 43 vs 29 ms (within 20). The guard costs a steady 12 to 15 ms on the first answer, which a 400 ms
  desktop LCP can't absorb at 3%. Owner chose an LCP allowance of 3% or 20 ms, whichever is larger: both desktop
  runs pass under it.

## 1. Summary

`openppc-online site` (companion 0.5.0, unreleased) crawls a whole site and checks SEO, links, indexing,
structured data, security, tracking and consent, with every number traced. On speed and page quality it is behind
Lighthouse 13 and PageSpeed Insights (PSI): three lab metrics on one page, no 0–100 score, no desktop, no
insights, field data only with a CrUX key, and a text-only report. Its lab numbers are also wrong against the
profile they claim (section 3).

**What parity means here** (section 2): a PPC freelancer pastes a landing page URL and gets PSI's speed score (or
one that says plainly why it differs), the same real-visitor verdict, mobile and desktop, every Lighthouse audit,
and a summary a client can read. Plus what PSI can't do: the whole site, staging sites, tags and consent, ad
parameters through redirects, and numbers that are all traced.

**How** (ADR-9): one reader for Lighthouse's result format (the LHR), fed by PSI's API (`--psi`) or by a
Lighthouse the user installed (`--lighthouse`). That gives exact parity, all four Lighthouse categories, early and
cheaply. The native lab pass that already exists stays for what those can't do (site-wide, private and staging
pages, tag cost), fixed and calibrated, and always labelled as OpenPPC's own measurement. It shows no 0–100 score
until it is calibrated (R3).

The companion is unreleased, so scoring and schema changes cost nothing in compatibility now. That ends with the
first release.

**Time:** about 18 weeks for one senior engineer, in five releases (section 6 itemises them). The first useful
release lands after about 3.5 weeks, for the command line and the app's existing Site form. The app's quick check
and client summary follow in R2.

## 2. Parity, defined so it can be tested

**User parity** (the owner signs off on these):

| # | Outcome | Test (on the review set, section 9) |
|---|---|---|
| U1 | Paste one URL, get a result | `--single --psi`, on an install without the render extra: under 60 s for 80% of the set. Native `--single`: first mobile result under 60 s and full result under 4 min, for 80%, with progress shown |
| U2 | Same speed score as PSI | `--psi`: PSI's own number, identical by construction. Native, from R3: labelled, explained (U6), and within the calibration gate (section 8) of Lighthouse on the same machine |
| U3 | Same real-visitor verdict as PSI | with `--psi`, PSI's own `overall_category`; with `--crux`, computed by PSI's rule and tested against recorded PSI responses |
| U4 | Mobile and desktop | both, side by side, by default in `--single` |
| U5 | A client understands the summary | 3 non-technical people (the owner's clients, named before R2 starts) each answer from the summary alone: is it good, what's the main problem, who fixes it. On a "this computer only" summary, also: why it differs from PageSpeed. Passes at 3 of 3 |
| U6 | "Why does this differ from PageSpeed?" | a fixed explainer next to every native number (device, network, lab vs real visitors, one load vs many), tested through U5's fourth question |

**Feature parity:** every audit in Lighthouse 13 appears in an OpenPPC report when `--psi` or `--lighthouse` runs,
with its result, details (in JSON) and a link to Google's docs.

- The parity matrix (`companion/parity/lighthouse-13.csv`) is generated from recorded LHR fixtures
  (`categories.*.auditRefs` and `lighthouseVersion`), so R1 needs no Node. It lists each audit, its source (LHR,
  native, both) and its report group.
- A test fails when a new fixture has an audit the matrix doesn't map. PSI's Lighthouse version floats with
  Google's schedule. So at run time an unmapped audit is shown under "Not yet mapped" with its title and result, and
  the version is recorded. A major version other than 13 is labelled in the report.

**Native parity** is a deliberate subset (R3, R4). Re-implementing Lighthouse means re-porting every major release:
Lighthouse 13 replaced 16 audits with insights.

## 3. What's wrong today

Evidence from `render.py`, `net.py` and `crux.py`. The Lighthouse values come from its `constants.js` and were
confirmed in review. A test re-checks each against the pinned version.

| Today | Lighthouse | Effect | Fixed in |
|---|---|---|---|
| 150 ms latency, 1638.4 kbps down, 750 up, applied with `Network.emulateNetworkConditions` | those are Lantern's *simulated* inputs. Applied (devtools) throttling is 562.5 ms (×3.75), 1474.56 kbps (×0.9), 675 kbps | lab numbers optimistic against the profile they claim | R1 |
| 412×823 at DPR 2.625, no mobile user agent | Moto G Power: 412×823 at DPR 1.75, Lighthouse's mobile UA | layout and images differ; UA-sniffing sites serve desktop HTML | R1 |
| Playwright's default headless shell | new headless (`channel="chromium"`) | paints differently | R3 (moved from R1: the full browser calls accounts.google.com, android.clients.google.com, clients2.google.com, update.googleapis.com and www.google.com on its own, through the guard, whatever the flags; found in R1's e2e test. R3 measures the shell against new headless in calibration, and new headless needs those hosts refused before they are resolved, which `--lighthouse` in R5 needs too) |
| `goto(wait_until="load")` with a 60 s timeout; a page that times out loses its vitals | a 45 s load cap, then measure anyway and flag the run | with corrected throttling, heavy pages would time out | R1 |
| "simulated phone" in the README and report | Lighthouse's "simulated" means Lantern | implies parity we don't have. Becomes "throttled phone (rough estimate)" until R3 | R1 |
| `crux.py` calls `urllib.request.urlopen` directly | n/a | bypasses `net.Guard` and its size caps (THREAT_MODEL row on CrUX) | R1 |
| `Vitals.median`: a median per metric, details from run 1 | one representative run (Lighthouse CI's median-run rule) | a score from it matches no real load | R3 |
| TBT from `longtask` entries starting after FCP, until load + 5 s | each task's blocking part (start + 50 ms to end) clipped to FCP–TTI | late third-party work inflates TBT, the 30% metric | R3 |
| a fixed 5 s settle | 5 s with no long tasks and at most 2 requests in flight, capped | late SPA LCPs missed; no TTI | R3 |
| CLS from the top frame's observer | trace layout shifts, subframes by `weighted_score_delta` | iframe shifts missed | R3 |

The guard's proxy also shapes timing:
- DNS happens in Python, so the browser sees 0 ms DNS.
- Addresses are tried one at a time.
- Plain `http://` gets `Connection: close`.
- QUIC is off.
- Chromium allows 32 sockets per proxy.

HTTPS tunnels through `CONNECT`, so HTTP/2 survives, but the proxy sees only host and port. Connection-level results
say "measured through OpenPPC's guard".

## 4. What must not change

- **The companion's promises:** off unless run, read-only, your own credentials, only declared hosts. Each new host
  is declared only with its flag:
  - fitness function 9 (SCOPE_WIDENING_PLAN section 4, item 9)
  - the README's Hosts lines
  - THREAT_MODEL.md

  All three are updated in the same change.
- **The guard:** every connection the companion makes goes through `net.Guard` (`net.fetch`), with its caps.
  CrUX and PSI included. Every browser goes through `GuardProxy`. Even under `--allow-private`, the guard refuses
  the run's own ports: the debugging port, the proxy and the app.
- **Traced numbers:** every number in a report is a registered fact, checked by `trace` before anyone sees it.
  Numbers from an LHR are facts too, labelled with their source. Lighthouse's `displayValue` strings are never copied
  untraced.
- **Screenshots and secrets:** screenshots are saved or shown only when asked for (`--screenshots`, or the app's
  tick). Secret-looking URL values are masked in every format. Both now cover LHR content (ADR-9).
- **The core:** `openppc` is untouched. `formats.to_html` keeps its rule (no script, link, image or `url()`), so
  the CLI's `--format html` stays text. Visuals live in the local app (R2).
- **Positioning:** the companion is the "landing page and tracking check" (SCOPE_WIDENING_PLAN section 1). Speed
  parity serves that. It is not pitched as a general speed or SEO tool, and none of it goes in the hero.

## 5. ADR-9: where the numbers come from

| Source | Flag | What it gives | Limits |
|---|---|---|---|
| PSI API | `--psi` (key: `--psi-key` or `OPENPPC_PSI_KEY`, optional) | PSI's exact numbers, all four categories, real-visitor data for the page and the site | public URLs only; sends the address to Google; shared quota without a key; Google's Lighthouse version |
| Your installed Lighthouse 13.x | `--lighthouse` | Lighthouse's exact logic (simulated throttling, as PSI uses), all four categories, private and staging pages too, through our guard | needs Node and `npm i -g lighthouse@13`; timings include our proxy |
| OpenPPC lab (exists) | `--render` | site-wide sample, tag cost, consent shifts; no Node; nothing sent to Google | a subset of audits; labelled "OpenPPC lab", never "PageSpeed"; no 0–100 score before R3 |

**Rules:**

- **One reader (`lab/lhr.py`)** turns an LHR from PSI or local Lighthouse (the same JSON) into facts and report
  sections.
  - It drops screenshots (final, full-page, filmstrip) unless they were asked for.
  - It runs `triage.redact` over every string.
  - It puts DOM snippets and URLs in code spans.
  - It renders audit details (tables of URLs, bytes and times) in JSON only. The Markdown shows each audit's title,
    result and the few numbers registered as facts.
- **One lab source per page and device, chosen up front:** PSI, else local Lighthouse, else native. Every score
  names its source, and per-page tables have a source column. Real-visitor data and test loads are always named
  apart: "Real visitors (last 28 days)" and "Test load".
- **Lighthouse's category scores never go in `scores`.** Its Accessibility, Best Practices and SEO scores appear only
  in the "All Lighthouse audits" section, labelled as Lighthouse's, so they never sit beside OpenPPC's own grades
  under the same name.
- **Rulebook (fitness function 7):** native rules keep one row each. LHR results get one row per Lighthouse category,
  plus the speed score and the real-visitor verdict. This is a recorded exception. The parity matrix is the
  per-audit register, and its test does the job a row's trace test would.
- **Rejected:**
  - native-only parity: a permanent re-port, and Lantern savings can't be honest without the simulator;
  - PSI as the only lab: no staging, no site-wide, no tag cost.

**`--psi`:**

- **The key:** `--psi` is a plain switch. The key comes from `--psi-key KEY` or `OPENPPC_PSI_KEY` and travels as the
  `X-Goog-Api-Key` header, never in a URL; fitness function 11's sentinel runs through it.
  - CrUX takes the same shape: `--crux` turns it on, with the key from `--crux-key KEY` or `OPENPPC_CRUX_KEY`.
    Today's `--crux-key [KEY]` (`nargs="?"`) swallows a URL that follows it.
  - In the app, both keys travel in the job request and live only in that job, as today.
  - The README's flag table changes in the same commit.
- **The route:** calls go through `net.fetch`, so they get the guard and its caps. R1 gives `fetch` per-call headers,
  a request body (CrUX's `queryRecord` is a POST), and its own timeouts and size cap: PSI often sends nothing for
  20–60 s, so it gets about 120 s and 20 MB, then the response is validated. A test checks the key header never
  appears in a log or an error. `pagespeedonline.googleapis.com` is declared only with the flag.
- **Which pages:** the start URL and each `--render-url`, at most 5, mobile and desktop, at most 2 calls at a time.
  With `--single`, when PSI succeeds, the native speed runs are skipped (its score wins anyway); the tag and consent
  load still runs if the render extra is installed.
- **Refused targets:**
  - A URL with secret-looking query values (`triage.redact`'s list) is refused with a message, not silently changed,
    since PSI would then measure a different page.
  - A target "not public" is refused, pointing at `--lighthouse` or `--render`. Not public means the guard refuses
    its address, or its host doesn't resolve to a public address.
  - `--psi` with `--allow-private` is refused.
- **Quota failure:** a plain message and, when the render extra is installed, native metrics, labelled as such.
- **The project's own key:** the nightly drift job's key belongs to the project and lives only as a CI secret.
  ADR-8 ("OpenPPC never ships or proxies one") is about users' keys; this key never ships.

**`--lighthouse`:**

- **The browser:** Playwright launches Chromium with the guard's proxy (a browser-wide flag, so Lighthouse's tab
  inherits it) and a debugging port.
  - The port is bound to 127.0.0.1, and `--remote-allow-origins` is never passed.
  - How the port is read back is R3's spike, because Playwright refuses `--user-data-dir` in `launch()`. Either
    `launch_persistent_context` with a temporary profile, reading `DevToolsActivePort`, or a free port picked in
    Python and confirmed with `/json/version`.
- **Starting Lighthouse:** it runs as `node <npm root -g>/lighthouse/cli/index.js` with an argument list. It is never
  started through the `lighthouse.cmd` shim, whose argument parsing on Windows lets a crafted URL inject commands.
  - `--no-enable-error-reporting` turns off its Sentry reporting.
  - The major version and Node's minimum are checked first.
  - The user's global, unpinned install is an accepted risk, recorded in THREAT_MODEL.md.
- **Throttling:** Lighthouse applies its own emulation and throttling to its own tab. Ours is per page and never
  browser-wide, so they don't stack. The method is recorded.
- **Tag hits** are not blocked in Lighthouse's tab, and the report says so. Lighthouse runs once per device, as PSI
  does.
- **New surface:** the debugging port lives only for the run, and THREAT_MODEL.md gets an entry. A test runs
  Lighthouse with outbound traffic sent to a sink, since fitness function 9 sees only Python's sockets.

## 6. Releases

**Each release includes:**
- its rulebook rows and trace tests
- schema changes and docs
- a CHANGELOG entry
- fitness functions 8–12 green
- THREAT_MODEL.md rows
- a security review of its diff

| Release | Work | Fixed time |
|---|---|---|
| R1 | 3 weeks | security review 2 days |
| R2 | 2.5 weeks | U5 sessions, owner gate, security review: 1 week |
| R3 | 6 weeks (calibration tuning time-boxed) | security review 2 days |
| R4 | 2.5 weeks (3.5 if the spike fails) | security review 2 days |
| R5 | 1 week | security review 2 days |
| **Total** | 15–16 weeks | about 2.5 weeks, so about 18 weeks |

### R1: PSI parity and the one-page check (companion 0.6.0)

1. **Honest native numbers now:**
   - `lab/throttle.py` with mobile and desktop profiles copied from Lighthouse, tested against its values
   - DPR 1.75 and a mobile UA
   - ~~new headless~~ moved to R3 (section 3)
   - the 45 s load cap
   - the "rough estimate" wording
   - `crux.py` on `net.fetch`
2. **Tag hits blocked during speed loads** (**[Owner]** answers open question 1 before R1 starts; until then it's a
   module constant, on):
   - CDP `Fetch.enable` on the speed-measurement session, with `requestPatterns` limited to the hit URLs in
     `signatures.json`, answered `204` locally. Scripts still load.
   - Not `page.route`, which turns off the HTTP cache and sends every request through Python.
   - The patterns are generated from `signatures.json`. A test checks that no ordinary image, stylesheet or script URL
     matches them.
   - Any error in the handler falls back to `Fetch.continueRequest`, so a load can't hang on it.
   - The one tag and consent load stays real, and the report says which loads were which.
   - This keeps test visits out of clients' analytics from the first release. Its timing bias is measured in R3
     (section 8).
3. **`lab/lhr.py` and `--psi`** (ADR-9).
4. **`--single`:** a `single` mode in `crawl()` that fetches the start URL (and `--render-url` pages) and skips
   sitemaps, the missing-page probe, `llms.txt`, external links and `follow()` of rendered links.
   - Rules that need a whole site (duplicate titles, `site-sitemap-bad-url`, sitemap and robots findings beyond the
     page) don't run; a test lists which rules apply to one page.
   - Mobile and desktop by default, the first mobile speed load first.
   - It runs without the render extra when `--psi` is given. The HTML tag checks always run, and a line offers the
     browser load for consent and events.
5. **Speed score from an LHR:** the Lighthouse formula (weights 10/10/25/30/25, log-normal curves, mobile and desktop
   control points; Apache-2.0, credited in THIRD_PARTY_LICENSES.md), tested against Lighthouse's scoring test
   vectors. It is read from the LHR in R1, and used natively from R3.
   - **With an LHR:**
     - The Performance area's score is the start page's mobile speed score, rounded to an integer, with PSI's band
       (0–49, 50–89, 90–100) next to the grade.
     - Performance findings come from the LHR and cost no points ("counted in the speed score"), as
       `counted_elsewhere` does for axe twins.
   - **Without an LHR, until R3:** Performance keeps today's points from native findings, labelled "rough estimate".
     There is no 0–100 speed score, gauge or band.
   - **Code:** `scores()` takes the speed result as an argument instead of `rendered` alone. `NEEDS_BROWSER` stops
     saying "needs `--render`" for rules an LHR covered.
   - **JSON:**
     - a top-level `speed` block: source, method, device, Lighthouse version, per-metric value, score and weight;
     - `scores.performance` gains `method` (`$defs/score` allows extra properties).
     - Additive, so `format_version` stays 1.
6. **Real-visitor data, PSI style:**
   - **What's shown:** good, needs-improvement and poor shares for LCP, INP, CLS, FCP and TTFB. The page first, then
     the site as fallback, said explicitly. "Not enough real visitors yet" when empty.
   - **The verdict:** PSI's `overall_category` with `--psi`. With `--crux` (which gains desktop, histograms, FCP
     and TTFB):
     - passed when LCP, INP and CLS are all good at p75 (good includes the line);
     - LCP and CLS alone when INP has no data;
     - no assessment when LCP or CLS has none.
7. **"All Lighthouse audits" section:**
   - First: what affects the ad click (speed, the landing page's content).
   - Then: Accessibility, Best Practices and SEO under "Not about the ad click".
   - Then: "Not yet mapped".
   - Passed audits are shown as a count. Each audit links to its docs.
8. **The app's existing Site form** gets a "Use Google PageSpeed (sends the address to Google)" tick and a "One page
   only" tick, so app users get R1 before R2's summary.

### R2: the summary a client can read (companion 0.7.0)

- **In the local app's Site view** (its CSP allows `data:` images):
  - **The top row:** pass, warn or fail answers to four questions: the page loads fast on phones, the tags fire,
    consent works, ad parameters survive redirects. "Loads fast on phones" comes only from PSI, local Lighthouse or
    real visitors. Without them it says "check with PageSpeed" (until R3's calibrated native score).
  - **The scores:** score gauges in PSI's bands as inline SVG, each with its source badge; the real-visitor banner;
    mobile and desktop tabs.
  - **The page screenshot,** only when ticked.
  - **The top three fixes,** each with who does it (developer, hosting, tag manager), its effort, and what it costs
    the ads if ignored. Each "costs" line has a rulebook source in Google's own wording.
  - **The traced-numbers line.**
  - **One next step:** "fix these, then re-check", "check with PageSpeed to compare", or "load in Chromium to check
    consent". **Re-check** keeps this result as the baseline.
- **Plain words:** a line per metric on what it means and why it matters for ad clicks (wording checked against
  Google's docs). The top 10 Lighthouse audits get a plain line each. The report and the summary end with a
  glossary.
- **An agency name field,** printed on the summary. A print stylesheet makes it a one-page PDF.
- **The quick check's choice:** "Check with Google PageSpeed (sends the address to Google; Google's test loads fire
  the page's tags)" and "Check on this computer only".
  - The choice is made each run and never kept, so it stays opt-in.
  - Without the render extra, the second button reads "Tags and page checks only (no speed)".
- **Local-app threat model rows:**
  - the PSI key, handled like the CrUX key (ADR-8: memory only)
  - screenshots, kept in memory with the last few results
  - the agency name, length-capped, control characters removed, written as a text node
  - the PSI choice, never persisted
- **Ad parameters through server redirects:** the crawler (no browser, so no tag fires) requests the page with
  `gclid`, `gbraid`, `wbraid`, `msclkid`, `fbclid` and `utm_*` set to `OPENPPC-TEST`. It checks the final URL keeps
  them. Labelled "server redirects only" until R4. The docs say server-side logs and CRMs may record the test value.
- **The U5 comprehension check.**
- **[Owner] gate:** review R1 and R2 on the review set before R3.

### R3: native lab parity (companion 0.8.0)

1. **The `lab/` package** (render.py only orchestrates):
   - `capture.py`: one CDP trace per load (main-thread tasks, layout shifts, screenshots) and the network log, into a
     serialisable `LabRun`. Not "trace", which already means the number checker.
   - `metrics.py`:
     - FCP, LCP, CLS (subframes included), TBT and TTFB from the trace.
     - TTI is computed only to bound TBT and pick the representative run, and is never shown.
     - A run with no TTI (no quiet window before the cap) is flagged.
     - Tested against Lighthouse's TBT and TTI unit vectors.
2. **Runs:**
   - 3 per device by default, `--runs 5` for more, devices one after the other (CPU contention corrupts TBT).
   - The representative run (Lighthouse CI's rule) is displayed, with min and max per metric.
   - "Unstable" when variation is high: coefficient of variation above 25% for TBT, 10% for FCP and LCP.
   - Site-wide rendered pages get 1 run each, labelled as one load. Their metric findings fire only above the poor
     line, or more than 20% above the good line. Otherwise they say "near the line; re-check with `--single`".
3. **Speed Index and the native score:**
   - Speed Index from trace screenshots with speedline's method, credited.
   - The native score, labelled "OpenPPC lab" with the U6 explainer, from the start page when there's no PSI or
     Lighthouse result. From here, "Without an LHR" in R1 item 5 uses it.
   - Each report records the host's benchmark index, with a warning outside Lighthouse's range.
4. **Attach mechanism for Lighthouse** (ADR-9's port spike), used by the calibration reference now and exposed as
   `--lighthouse` in R5.
5. **Trace-engine spike, 5 days, decides R4:**
   - Bundle the DevTools trace engine (`@paulirish/trace_engine`, BSD-3) as an IIFE, as axe is, and run it in a
     blank page in the same Chromium on a `LabRun`'s trace, with screenshots stripped (traces run to 20–100 MB).
   - Lantern simulates from an unthrottled load, so savings need one extra unthrottled load per device, inside U1's
     4-minute line.
   - It passes when its insight IDs match Lighthouse 13's and its savings are within 10% of Lighthouse `simulate`, on
     5 fixtures.
6. **The calibration harness and gates** (section 8).
   - Tuning is time-boxed to the last 1.5 weeks.
   - If the gate isn't green by then, R3 ships with native scores labelled "uncalibrated" and the published gap, and
     the summary's "loads fast on phones" stays PSI-only.

### R4: insights, and the ones only OpenPPC can give (companion 0.9.0)

- **If the spike passed:** the trace engine's insights with savings, for each page with speed runs, version-pinned and
  bumped like axe.
- **If not:** LCP phases, render-blocking files, image delivery, cache lifetimes, third parties, document latency and
  CLS culprits, natively. They show bytes and request times only, labelled "not simulated", never milliseconds saved.
- **PPC insights, always native:**
  - **What each tag costs:** bytes and main-thread time per vendor in `signatures.json`.
  - **Consent banner shifts:** layout shifts caused by the consent platform's elements.
  - **Ad parameters in the browser:** the final `location.href` after load, with tag hits blocked. This catches
    parameters that SPA routers, `history.replaceState`, consent tools and JavaScript redirects drop.
  - **JavaScript errors on the page** (CDP console and exceptions), since a script error can stop a tag.

### R5: local Lighthouse and budgets (companion 0.10.0)

- **`--lighthouse`** (ADR-9), on R3's attach mechanism and R1's reader.
- **Budgets in rule packs:** metric lines (LCP, TBT, CLS, the speed score) and resource sizes, failing with
  `--fail-on`; `--baseline` covers them. `site-config.schema.json` gains `budgets`.

### Parked, with the condition to reopen

- **Native Best Practices and SEO extras** (link text, crawlable anchors, robots.txt validity, hreflang): `--psi` and
  `--lighthouse` cover them. Reopen native, site-wide versions if users ask.
- **A native Lighthouse-weighted accessibility score:** the LHR has it, and native axe stays as is.
- **User flows and lab INP:** reopen with a scripted-interaction design.
- **Trends and other views:** CrUX History trends, filmstrip, treemap, stack packs and source-map audits.
- **Lists of landing pages across sites** (`--urls`): reopen after R2 if review-set users ask.
- **The branded PDF's full layout for the summary:** reopen after the U5 check.

## 7. Reports

- **Formats:** Markdown and SARIF carry the findings, scores and traced numbers. JSON also carries LHR audit details,
  redacted, without screenshots unless asked for. `--format html` stays text (section 4).
- **A "Speed" section per page and device:**
  - the source and method, with a source column in per-page tables
  - the score with its band (LHR sources from R1; native from R3)
  - five metrics with good and poor lines
  - the representative run with min and max, and stability (native)
  - the U6 explainer for native numbers
- **"Real visitors" apart from "Test load",** always.
- **"All Lighthouse audits"** when an LHR is present (R1, item 7).

## 8. Calibration (R3)

- **Reference:** the pinned Lighthouse 13.x with `--throttling-method=devtools`, on the same Chromium binary, host
  and proxy, matching screen and user agent, attached through R3's mechanism. `simulate` is recorded alongside to
  track the gap PSI users will see; it is not gated.
- **Corpus:** 18–23 local fixtures over HTTPS with HTTP/2, on several host names, with scripted delays:
  - plain text, a hero image as LCP, a lazy-loaded LCP image, and a client-rendered SPA;
  - render-blocking CSS and JS, and a font swap;
  - a late banner shift and a shift inside an iframe;
  - 60/200/800 ms tasks before and after TTI;
  - a redirect chain, many third-party hosts, and an HTTP/1.1-only host;
  - 2–3 pages with fake tag scripts and hit endpoints on vendor host names mapped to loopback, including a chained
    pixel.
- **Harness:**
  - The fixtures resolve to loopback, so runs pass `--allow-private`, with `Guard.resolve` overridden in the tests.
  - A test certificate authority is trusted with `--ignore-certificate-errors-spki-list`.
  - The run "without the guard" uses a bypass that lives under `tests/`. A fitness function proves neither the
    bypass nor that flag appears in `openppc_online/`.
- **Runs:** at least 9 per side, alternating. The workflow is split by device and fixture group, to stay under the
  runner's 6-hour limit.
- **Gate on per-metric medians from both sides,** with hit blocking on (as users run it):

| Metric | Allowed difference |
|---|---|
| FCP, LCP | ±10% or ±150 ms, whichever is larger |
| Speed Index | ±15% or ±250 ms, whichever is larger |
| TBT | ±25% or ±50 ms, whichever is larger |
| CLS | ±0.01 |
| TTFB | ±5% or ±20 ms, whichever is larger |

  - The representative run's score must be within ±5, and in the same band unless within 2 points of a band line.
  - TTI is compared (±15%) but not gated.
  - The gate passes with at most one miss in total, across all fixtures and metrics.
  - The tag fixtures stay out of the gate, since the reference fires hits and ours are blocked. On them, blocking on
    vs off is recorded and published.
- **Proxy gate:** the median of 9 alternating runs with and without the guard: LCP within 3% or 20 ms, whichever is
  larger (the guard's cost is mostly fixed, and 3% of a 400 ms desktop LCP is about 12 ms), TTFB within 20 ms. A
  nightly run with and without the proxy on public sites tracks DNS and connection costs; it never gates.
- **Where it runs:**
  - **Per pull request:** offline unit tests on recorded `LabRun`s and LHRs (no internet, no Lighthouse).
  - **The gates:** a scheduled and manual workflow with Chromium and a lockfile-pinned Lighthouse
    (`npm ci --ignore-scripts`).
  - **Nightly:** 10 public sites against PSI, using the project's key from a CI secret, publishing the native-vs-PSI
    gap in the docs. It never gates.

## 9. Success measures (no telemetry)

| Measure | Source | Target |
|---|---|---|
| U1–U6 | a fixed review set of 20 landing pages (the owner's and public ones) | U1, U3–U6 pass before R2 ships; U2 native from R3 |
| Time to result | the review set, each release | U1's lines |
| Native vs PSI gap | the nightly job, published | shown to users, trending down |
| Comprehension | U5 | 3 of 3 |
| "Differs from PageSpeed" issues | GitHub issues with that label | each answered within 3 working days; the median published |
| Calibration gate | the scheduled workflow | green from R3, or "uncalibrated" shown (R3 item 6) |

## 10. Risks

| Risk | Mitigation |
|---|---|
| Native and PSI scores differ and users distrust both | no native score before calibration; one source per score; PSI offered first; labels, the explainer, the gate, the published gap |
| Lighthouse or PSI changes its format or version | the matrix from fixtures; "Not yet mapped" at run time; the version recorded; a non-13 major labelled |
| The keyless PSI quota fails | at most 2 calls at a time; a plain message; native metrics labelled |
| The trace-engine spike fails | R4's native fallback, already estimated |
| Test loads add visits to clients' analytics | hit blocking from R1; PSI's and Lighthouse's loads say they fire tags |
| Hit blocking biases timings | measured on tag fixtures in R3, published |
| LHRs leak screenshots or secrets | `lhr.py` drops screenshots and redacts every string; details in JSON only |
| `--lighthouse` on Windows, or the debugging port, opens a hole | Node started directly; port on 127.0.0.1 for the run, never `--remote-allow-origins`; the guard refuses the run's ports; outbound sink test; threat model |
| Scope drifts into a general SEO tool | the parked list; Lighthouse's SEO and Best Practices under "Not about the ad click"; section 4 |
| R3's estimate slips | the owner gate before it; time-boxed tuning with the "uncalibrated" exit; R1 and R2 already deliver PSI parity |

## 11. Decisions taken, and open questions for the owner

**Taken** (the owner may overrule):
- the speed score from an LHR replaces performance points; no native score before R3;
- PSI is opt-in, offered as an equal button each run;
- Lighthouse's category scores stay out of `scores`;
- `--lighthouse` needs the user's own Node, opt-in;
- LHR audits are one rulebook row per category, an exception to fitness function 7.

**Open:**
1. Block tag hit requests during speed loads by default, from R1 (recommended)? It slightly changes timings
   against Lighthouse and PSI, which fire hits; R3 measures by how much. Needed before R1 starts.
2. Which 20 landing pages form the review set, and which 3 clients take the U5 check? Needed before R2 starts.
3. Approve the summary's wording on what each problem "costs the ads", before R2 ships.
4. A project-owned Google API key for the nightly PSI job (a CI secret).

## Appendix B: critique log

- **v1 to v2** (architecture, product and measurement reviews):
  - **Parity:** redefined it as user outcomes plus a generated audit matrix. Replaced "native by default" with one
    LHR reader fed by PSI or local Lighthouse.
  - **Measurement:** found today's throttling using Lantern's simulated values as applied ones, a wrong DPR, no
    mobile UA, a per-metric median, and TBT to load + 5 s. Corrected "median run as Lighthouse does" (it's
    Lighthouse CI's rule). Removed lab INP. Noted that keyless field data comes only from PSI.
  - **Design:** kept the core's `to_html` unchanged, with visuals in the app. The speed score replaces performance
    points. Added the trace-engine spike, the gates, licensing, `--psi` and `--lighthouse` security, the `lab/`
    package, PPC insights and an owner gate.
  - **Rejected:** that CI has no Chromium (the `web-app` job installs it).
- **v2 to v3** (the same three reviews, round 2):
  - **Order:** split R1 (PSI first, lab rewrite to R3), and moved the Lighthouse attach mechanism to R3 for
    calibration.
  - **`--single`:** made it a real crawl mode, which runs without the render extra under `--psi`.
  - **Targets:** realistic U1 targets (3 runs per device).
  - **Scores:** defined the Performance area's source, and kept Lighthouse's category scores out of `scores`.
  - **`--psi`:** made it a plain switch with `--psi-key`; URLs with secrets are refused.
  - **`--lighthouse`:** started via `node …/cli/index.js`, never the `.cmd` shim.
  - **Calibration:** spelled out TBT and TTI; gate on per-metric medians over 9 or more runs; fixed tolerances;
    added the harness.
  - **Product:** two equal buttons, the pass/warn/fail row, who fixes each problem, an agency name, next steps, the
    U5 test, the glossary, measurable success measures.
- **v3 to v4** (the three reviews, round 3, plus a fresh consistency and security review):
  - **No native score before R3:** R1 would have shown a 0–100 gauge built on metrics the plan itself calls wrong, or
    left Performance empty. Until R3, Performance keeps today's points, labelled "rough estimate", with no gauge;
    "loads fast on phones" comes only from PSI, Lighthouse or real visitors.
  - **Estimates:** the release estimates added up to 13, not 16 weeks, with R1 and R3 light. They are now itemised
    with fixed time (security reviews, U5, the owner gate) at about 18 weeks. R3 is 6 weeks with time-boxed tuning
    and an "uncalibrated" exit. The plain words and glossary moved to R2.
  - **Hit blocking:**
    - It can't happen in the proxy (it sees only host and port inside `CONNECT`), and `page.route` turns off the
      cache. It is now CDP `Fetch` with narrow patterns.
    - It moved to R1, so clients' analytics aren't touched from the first release.
    - Its timing bias is measured on new tag fixtures in R3.
    - Lighthouse's own tab isn't blocked, and says so.
  - **Parity matrix:** generated from recorded LHR fixtures, so no Node in R1. PSI's floating version is handled at
    run time with "Not yet mapped".
  - **LHR privacy and tracing:** screenshots dropped unless asked for, every string redacted, details in JSON only,
    and the rulebook exception recorded.
  - **The guard and the threat model:**
    - PSI and CrUX go through `net.fetch`. This also fixes today's `crux.py`, which bypasses the guard.
    - The guard refuses the run's own ports even under `--allow-private`.
    - `--remote-allow-origins` is never passed.
    - The test-only bypass and certificate flag are kept out of the package by a fitness function.
    - THREAT_MODEL rows were added for the app's new fields.
  - **Smaller fixes:**
    - Defined "not public"; `--crux-key` loses `nargs="?"`.
    - PSI concurrency capped at 2; the nightly key is a CI secret.
    - `--single` skips `follow()`; scores are rounded to integers; `NEEDS_BROWSER` knows about LHRs.
    - The 45 s load cap.
    - Site-wide one-run findings only clear of the line.
    - The first mobile load runs first; U1 is stated as 80% of the review set.
    - Test parameter values are `OPENPPC-TEST`; the second button reads "no speed" without the render extra; U5 asks
      about the PSI difference.
- **v4 review: stop.** All four reviewers answered "no material changes needed". Their polish went into v5:
  - `net.fetch` gains per-call headers, body, timeouts and size cap, for PSI and CrUX.
  - `--crux` and `--crux-key KEY` match `--psi` and `--psi-key KEY`.
  - The hit-blocking handler falls back to `continueRequest`, and its patterns are tested against ordinary files.
  - The tag fixtures stay out of the calibration gate.
  - The app's existing Site form gets PSI and one-page ticks in R1.
  - U5's "why it differs" question applies only to "this computer only" summaries.
  - Owner deadlines: question 1 before R1, question 2 before R2.
  - The first release is "about 3.5 weeks".

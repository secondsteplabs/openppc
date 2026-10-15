# Third-party licenses: openppc-online

openppc-online's own code is MIT, like OpenPPC. It ships two third-party files, copies a few published values, one
scoring formula and Lighthouse's way of measuring a trace, and uses one optional package.

## Shipped in the package

| Package | Version | File | Used for | License |
|---|---|---|---|---|
| axe-core | 4.10.3 | `openppc_online/siteaudit/vendor/axe.min.js`, unmodified, its license header intact | The accessibility checks in `openppc-online site --render` | MPL-2.0 |
| `@paulirish/trace_engine` (Chrome DevTools' trace engine), with third-party-web and legacy-javascript, which it includes | 0.0.65, 0.30.0, 0.0.3 | `openppc_online/siteaudit/vendor/trace-engine.js`, bundled and minified by esbuild, all three licences at its top | Lighthouse's insights in `openppc-online site --render` | BSD-3-Clause (Copyright The Chromium Authors), MIT (Copyright Patrick Hulce), Apache-2.0 (Google) |

The axe-core file is byte for byte the one npm publishes as `axe-core@4.10.3`; `tests/test_render.py` pins its
SHA-256. Its source: [github.com/dequelabs/axe-core](https://github.com/dequelabs/axe-core/tree/v4.10.3).

The trace engine file is built by `npm run vendor` in `companion/calibration/` from `trace-engine.mjs` (OpenPPC's few
lines that call the engine) and the lockfile's packages, the versions Lighthouse 13.5.0 pins; the build gives the same
bytes each time, `tests/test_lab_insights.py` pins its SHA-256, and the calibration workflow rebuilds it and compares.
Their sources: [ChromeDevTools/devtools-frontend](https://github.com/ChromeDevTools/devtools-frontend/tree/main/front_end/models/trace),
[patrickhulce/third-party-web](https://github.com/patrickhulce/third-party-web) and
[GoogleChrome/lighthouse](https://github.com/GoogleChrome/lighthouse/tree/main/packages/legacy-javascript)
(legacy-javascript).

## Values copied

| From | What | Where | License |
|---|---|---|---|
| Lighthouse 13 (`core/config/constants.js`) and Lantern (`simulation/Constants.ts`, in Chrome DevTools) | The mobile and desktop screens, user agents, throttling and load cap | `openppc_online/siteaudit/lab/throttle.py`; `tests/test_lab.py` checks each value | Apache-2.0 (Lighthouse), BSD-3-Clause (Chrome DevTools) |
| Lighthouse 13 (`shared/statistics.js`, `shared/util.js`, `core/audits/metrics/*.js`, `core/scoring.js`) | The performance score: the log-normal curve, each metric's control points per device, the weights and the rounding, ported to Python | `openppc_online/siteaudit/lab/score.py`; `tests/test_lab_score.py` checks it against a Lighthouse 13.5 report | Apache-2.0 |
| Lighthouse 13.5 (`core/computed/metrics/*.js`, `core/lib/lantern/metrics/tbt-utils.js`, `core/lib/tracehouse/trace-processor.js`, `core/gather/driver/wait-for-condition.js`, `core/config/constants.js`, `computeBenchmarkIndex` in `core/lib/page-functions.js` and its slow-CPU line in `core/gather/driver/environment.js`), `@paulirish/trace_engine` 0.0.65 (the layout shift and LCP handlers) and speedline-core 1.4.3 | How a trace becomes First Contentful Paint, Largest Contentful Paint, Total Blocking Time, Time to Interactive, Cumulative Layout Shift, time to first byte and Speed Index, how a load waits until quiet, and the trace categories, ported to Python; Lighthouse CI's representative run and its stability limits; Lighthouse's CPU benchmark (its JavaScript, run as is) and its slow-CPU line | `openppc_online/siteaudit/lab/metrics.py`, `openppc_online/siteaudit/lab/capture.py`; `tests/test_lab_metrics.py` | Apache-2.0 (Lighthouse, Lighthouse CI), BSD-3-Clause (trace engine), MIT (speedline) |
| Lighthouse 13.5 (a report it wrote, from its own test pages) | A test fixture, and the audit ids and categories of the parity matrix | `tests/fixtures/lhr-13.5-mobile.json`; `openppc_online/siteaudit/lab/lighthouse-13.csv` | Apache-2.0 |

## Installed only on request

| Package | Installed by | Used for | License |
|---|---|---|---|
| playwright | `pip install "openppc-online[render]"` | Driving Chromium for `--render` | Apache-2.0 |

`playwright install chromium` then downloads Chromium itself, under its own licenses.

`companion/calibration/` pins Lighthouse 13.5.0 (Apache-2.0) for checking the lab against it on a developer's
computer, and esbuild 0.28.2 (MIT) for building the trace engine file (`npm ci --ignore-scripts` there). Neither is
shipped or installed with the package.

## Loaded by the app

`openppc-online app` serves the OpenPPC web app, which loads its runtime and libraries from a CDN: see OpenPPC's
[THIRD_PARTY_LICENSES.md](https://github.com/secondsteplabs/openppc/blob/main/THIRD_PARTY_LICENSES.md).

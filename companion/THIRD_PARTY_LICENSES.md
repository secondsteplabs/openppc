# Third-party licenses: openppc-online

openppc-online's own code is MIT, like OpenPPC. It ships one third-party file, and uses one optional package.

## Shipped in the package

| Package | Version | File | Used for | License |
|---|---|---|---|---|
| axe-core | 4.10.3 | `openppc_online/siteaudit/vendor/axe.min.js`, unmodified, its license header intact | The accessibility checks in `openppc-online site --render` | MPL-2.0 |

The file is byte for byte the one npm publishes as `axe-core@4.10.3`; `tests/test_render.py` pins its SHA-256.
Its source: [github.com/dequelabs/axe-core](https://github.com/dequelabs/axe-core/tree/v4.10.3).

## Installed only on request

| Package | Installed by | Used for | License |
|---|---|---|---|
| playwright | `pip install "openppc-online[render]"` | Driving Chromium for `--render` | Apache-2.0 |

`playwright install chromium` then downloads Chromium itself, under its own licenses.

## Loaded by the app

`openppc-online app` serves the OpenPPC web app, which loads its runtime and libraries from a CDN: see OpenPPC's
[THIRD_PARTY_LICENSES.md](https://github.com/secondsteplabs/openppc/blob/main/THIRD_PARTY_LICENSES.md).

# Third-party licenses

> **Draft for the maintainer's review.**

OpenPPC's own code is MIT (see [LICENSE](LICENSE)). The Python package has no runtime dependencies and ships no third-party files. This page lists everything else the project loads or is built with, and its license. A test fails if the web app loads something from its CDN that is not listed here at the version it loads.

## Loaded by the browser app

The page downloads these from one CDN (`cdn.jsdelivr.net`), each pinned to a version and, for the files the page itself loads, checked against a fingerprint. None is copied into this repository.

| Package | Version | Used for | License |
|---|---|---|---|
| pyodide | 314.0.7 | Python in the browser tab (includes CPython, PSF-2.0) | MPL-2.0 |
| marked | 18.0.14 | Showing markdown reports | MIT |
| dompurify | 3.4.16 | Cleaning the shown HTML | MPL-2.0 OR Apache-2.0 |
| @fontsource-variable/plus-jakarta-sans | 5.3.0 | Headings and text | OFL-1.1 |
| @fontsource-variable/geist-mono | 5.3.0 | Numbers and code | OFL-1.1 |
| @fontsource-variable/source-serif-4 | 5.3.0 | Serif headings in the branded PDF | OFL-1.1 |

## Optional Python extras

| Extra | Package | Used for | License |
|---|---|---|---|
| `mcp` | MCP Python SDK (`mcp`) | The MCP server, `openppc-mcp` | MIT |
| `e2e` | Playwright (`playwright`) | The browser tests | Apache-2.0 |

The `mcp` extra brings its own dependencies (a web server, an HTTP client, validation). Their licenses are permissive, but they change with each release: for the exact list in an environment, run `pip-licenses` there. `playwright install chromium` downloads Chromium (BSD-3-Clause, with the third-party licenses Chromium lists in `about:credits`).

## Development only (never shipped)

| Package | Used for | License |
|---|---|---|
| hatchling | Building the package | MIT |
| pytest | Tests | MIT |
| ruff | Lint | MIT |
| axe-core 4.10.3 | Accessibility checks in the browser tests, loaded from the CDN | MPL-2.0 |

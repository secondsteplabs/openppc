# ADR-2: The network boundary

Status: accepted, October 2026

## Context

OpenPPC promises that it never connects to an ad account, makes no network calls, uploads nothing and needs no API
keys. Some fork features (API downloads, a website crawler) need the network by their nature.

## Decision

- The `openppc` distribution stays offline. Anything that fetches from the network ships in a separate companion
  distribution (ADR-7, written when that work starts), which depends on `openppc`, never the reverse.
- One exception is allowlisted by module: `openppc/mcp_server.py` imports the MCP SDK, which serves
  `openppc-mcp --http` as a connector for ChatGPT and claude.ai. It listens; it never fetches.
- The stable engine API the companion may use is `facts.FactBook`, `engine.trace.trace`, `ingest.load_report`,
  `templates.run_template` and the template protocol. `py.typed` ships when this API is declared stable, not before.
- Declared in 0.3.0: the five names carry type hints, `templates.Template` is the protocol that every module in
  `TEMPLATES` is checked against, and `py.typed` ships. mypy checks `facts.py`, `ingest/google_ads_csv.py` and
  `templates/__init__.py` in dev and CI; `trace`'s signature is typed, and its older body is not yet checked. A
  change that breaks one of these names is listed under Breaking in the changelog.
- Added in 0.4.0: `formats.to_html(markdown, title)`, the one HTML renderer (ADR-5), so the companion's reports
  render as the core's do. `openppc.__version__` may be read too. The companion's tests fail on any other import
  from `openppc`.

## Consequences

- `tests/test_fitness.py` fails if any module in `openppc/` imports `socket`, `ssl`, `http`, `urllib.request`,
  `asyncio`, an HTTP client library, or the MCP SDK outside the MCP server.
- The same file runs every command and MCP tool with sockets patched to fail.
- The browser bundle lists its modules by name (`tools/build_web.py`), so a new module reaches the app only by a
  reviewed change.
- `tests/test_api.py` imports the stable names from where this ADR puts them and checks that every template provides
  what the protocol lists.

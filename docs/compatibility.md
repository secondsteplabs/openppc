# What scripts, assistants and the site rely on

Everything here stays as it is in a patch release. A minor release may change it only with a **Breaking** entry in
[CHANGELOG.md](../CHANGELOG.md). Additions (a new flag, a new JSON key, a new tool) are not breaking.

## Exit codes (`openppc`)

| Code | Meaning |
| --- | --- |
| 0 | Clean: the audit ran, or the check found nothing wrong |
| 1 | Bad input: a missing file, the wrong export, an unreadable file or setting, or a usage mistake such as an unknown template or flag (a usage mistake exited 2 before 0.2.0) |
| 2 | The check found wrong numbers, wrong labels or contradictions, and nothing else (since 0.2.0, ADR-3) |
| 3 | A bug in OpenPPC: its own report failed its number check, or the command crashed (since 0.1.12; a crash used to exit 1 with a traceback) |

## CLI

- `openppc templates`, `openppc industries`, `openppc --version`
- `openppc audit <template> [data...] [--sample] [--industry KEY] [--min-cost AMOUNT] [--brand NAMES] [--out FILE]`:
  one file, or for `account-read` two exports of one report, one per period (since 0.2.0)
- `openppc check [--audit FILE] [--data FILE...]... [--sample] [--industry KEY] [--out FILE]`: `--data` takes one
  or more files, and can be repeated (since 0.1.12)
- `--debug`, before or after the command, prints the traceback of a crash (since 0.1.12)
- Templates: `search-term-waste`, `keyword-audit`, `account-structure`, `account-read`
- `--min-cost` must be an amount of zero or more; unset, it is the default in the export's currency.
- `--format` on `audit` (`md`, `html`, `json`) and `check` (`md`, `html`, `json`, `sarif`); `md` is the default
  (since 0.3.0). The exit code is the same in every format.
  - `json` matches `openppc/schemas/audit-report.schema.json` or `check-report.schema.json`. `format_version` (now
    1) goes up only for a change that breaks a reader; a new key keeps it.
  - `html` is one page that loads nothing from anywhere, with no date or version in it.
  - `sarif` is SARIF 2.1.0 with the rules `wrong-number`, `wrong-label`, `contradiction` (errors) and `cant-check`
    (a note), each result at its line in the audit.

## GitHub Action (`action.yml`)

- Inputs: `audit`, `data` (one path per line), `industry`, `sarif`, `python-version` (since 0.3.0).
- The step exits with `openppc check`'s code, writes the check to the job summary, and writes `sarif` only when
  the check ran (exit 0 or 2).

## Docker

- `docker build .` makes the command line image (entrypoint `openppc`, no MCP SDK); `--target mcp` makes the MCP
  server image (entrypoint `openppc-mcp`, port 8000). Both run as uid 10001 in `/data` (since 0.3.0).

## Python API (ADR-2)

- `openppc.facts.FactBook`, `openppc.engine.trace.trace`, `openppc.ingest.load_report`,
  `openppc.templates.run_template` and the `openppc.templates.Template` protocol, typed, with `py.typed` (since
  0.3.0).

## MCP tools

All are read-only and return markdown.

- Local (`openppc-mcp`): `list_templates()`, `audit_account(template, data_path, industry="", min_cost=None,
  brand="", prior_path="")`, `check_numbers(audit_text, data_paths, industry="")`
- Web connector (`openppc-mcp --http`): `list_templates()`, `audit_export(template, export_text,
  export_name="export.csv", industry="", min_cost=None, brand="", prior_text="", prior_name="prior.csv")`,
  `check_audit(audit_text, export_text, export_name="export.csv", industry="")`
- `prior_path`, `prior_text` and `prior_name` give `account-read` the other period's export (since 0.2.0)

## Browser app

- Hash routes: `#home`, `#check`, `#audit`, `#templates`, `#rules`, `#branded`
- The worker calls `openppc/webapi.py`; each function returns JSON with `ok`, and `error` when `ok` is false:
  - `meta()`: `version`, `templates` (`name`, `title`, `input`, `summary`, `kind`), `industries` (`key`, `name`)
  - `inspect_file(path)`: `name`, `kind`, `rows`, `start`, `end`, `days`, `currency`, `templates`, and for reports
    `currency_sign` and `min_cost`; on failure `hint`. `kind` is "Google Ads Editor export" for an Editor file,
    `rows` its campaigns (since 0.2.0)
  - `inspect_pair(paths_json)`: for two report files, `paths` with the current period first; on failure `error`
    says why they can't be compared (since 0.2.0)
  - `count_numbers(text, paths_json)`: a number
  - `check(text, paths_json, industry)`: `passed`, `counts` (`total`, `traced`, `mismatch`, `not_in_data`,
    `cant_check`, `contradictions`), `claims`, `contradictions`, `markdown` (`passed` since 0.3.0)
  - `audit(name, path, industry, min_cost, brand, prior)`: `title`, `markdown`, `passed`, `facts`, `cards`,
    `client`, `token`, `fingerprint`, and `prior_fingerprint` when `prior` names the other period's export (since
    0.2.0)
  - `verify(token, text, names_json)`: `total`, `traced`, `problems`
  - `export(token, fmt)`: `text`, the audit as `openppc audit --format html` or `json` writes it (since 0.3.0)
- The branded PDF settings saved in the browser add `ctaText` and `ctaUrl`; the link is used only when it starts
  with `https:`, `mailto:` or `tel:` (since 0.3.0).
- The app's bundle lists its modules in `tools/build_web.py`; `openppc/cli.py`, `openppc/mcp_server.py` and
  `openppc/__main__.py` are not in it (since 0.3.0).

## Input handling

- A negative cost, click count or impression count is refused, never read (ADR-4).
- Numbers in two styles in one file (`1,234.56` and `1.234,56`) are refused.
- Rows in more than one currency, and an export with a header but no rows, are refused (since 0.1.12).
- Column names must be Google's English ones.
- Text is read as UTF-16 (with or without a byte order mark), UTF-8, Windows-1252, then Latin-1.
- Microsoft Advertising reports and Google Ads Editor exports are read since 0.2.0 as **experimental**: built from
  the published layouts, not yet from real files, so how they are read may change in a minor release without a
  Breaking entry. Reports on Microsoft files name the platform with "(experimental)".

## Report wording

Scripts and assistants read these lines, so they stay as they are:

- A report that passes its own check says "Number check: every number in this report traces back to your data."
- Every report says "read-only: computed from this file alone, with no network calls.", or "from these files
  alone" for `account-read` on two exports (since 0.2.0).
- The "Settings:" line, which `openppc check` reads to re-run the same audit.
- "How the file was read:", a line that appears only when a file was read with decimal commas or as Western
  European text. It holds no numbers. On two exports it says "How the files were read:" (since 0.2.0).
- On two exports, the source line names each file with "(current)" or "(prior)", and periods of different lengths
  add a line starting "_Note: the two periods are different lengths" (since 0.2.0).

The reports themselves are frozen in `tests/golden/`; a change to one is reviewed like any other change here.

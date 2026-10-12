# What scripts, assistants and the site rely on

Everything here stays as it is in a patch release. A minor release may change it only with a **Breaking** entry in
[CHANGELOG.md](../CHANGELOG.md). Additions (a new flag, a new JSON key, a new tool) are not breaking.

## Exit codes (`openppc`)

| Code | Meaning |
| --- | --- |
| 0 | Clean: the audit ran, or the check found nothing wrong |
| 1 | Bad input: a missing file, the wrong export, an unreadable file or setting |
| 2 | The check found wrong numbers, wrong labels or contradictions. Today argparse usage errors also exit 2; that changes to 1 in 0.2.0 (ADR-3) |
| 3 | A bug in OpenPPC: its own report failed its number check, or the command crashed (since 0.1.12; a crash used to exit 1 with a traceback) |

## CLI

- `openppc templates`, `openppc industries`, `openppc --version`
- `openppc audit <template> [data] [--sample] [--industry KEY] [--min-cost AMOUNT] [--brand NAMES] [--out FILE]`
- `openppc check [--audit FILE] [--data FILE...]... [--sample] [--industry KEY] [--out FILE]`: `--data` takes one
  or more files, and can be repeated (since 0.1.12)
- `--debug`, before or after the command, prints the traceback of a crash (since 0.1.12)
- Templates: `search-term-waste`, `keyword-audit`, `account-structure`, `account-read`
- `--min-cost` must be an amount of zero or more; unset, it is the default in the export's currency.

## MCP tools

All are read-only and return markdown.

- Local (`openppc-mcp`): `list_templates()`, `audit_account(template, data_path, industry="", min_cost=None,
  brand="")`, `check_numbers(audit_text, data_paths, industry="")`
- Web connector (`openppc-mcp --http`): `list_templates()`, `audit_export(template, export_text,
  export_name="export.csv", industry="", min_cost=None, brand="")`, `check_audit(audit_text, export_text,
  export_name="export.csv", industry="")`

## Browser app

- Hash routes: `#home`, `#check`, `#audit`, `#templates`, `#rules`, `#branded`
- The worker calls `openppc/webapi.py`; each function returns JSON with `ok`, and `error` when `ok` is false:
  - `meta()`: `version`, `templates` (`name`, `title`, `input`, `summary`, `kind`), `industries` (`key`, `name`)
  - `inspect_file(path)`: `name`, `kind`, `rows`, `start`, `end`, `days`, `currency`, `templates`, and for reports
    `currency_sign` and `min_cost`; on failure `hint`
  - `count_numbers(text, paths_json)`: a number
  - `check(text, paths_json, industry)`: `counts` (`total`, `traced`, `mismatch`, `not_in_data`, `cant_check`,
    `contradictions`), `claims`, `contradictions`, `markdown`
  - `audit(name, path, industry, min_cost, brand)`: `title`, `markdown`, `passed`, `facts`, `cards`, `client`,
    `token`, `fingerprint`
  - `verify(token, text, names_json)`: `total`, `traced`, `problems`

## Input handling

- A negative cost, click count or impression count is refused, never read (ADR-4).
- Numbers in two styles in one file (`1,234.56` and `1.234,56`) are refused.
- Rows in more than one currency, and an export with a header but no rows, are refused (since 0.1.12).
- Column names must be Google's English ones.
- Text is read as UTF-16 (with or without a byte order mark), UTF-8, Windows-1252, then Latin-1.

## Report wording

Scripts and assistants read these lines, so they stay as they are:

- A report that passes its own check says "Number check: every number in this report traces back to your data."
- Every report says "read-only: computed from this file alone, with no network calls."
- The "Settings:" line, which `openppc check` reads to re-run the same audit.
- "How the file was read:", a line that appears only when a file was read with decimal commas or as Western
  European text. It holds no numbers.

The reports themselves are frozen in `tests/golden/`; a change to one is reviewed like any other change here.

"""Report formats beyond markdown: one self-contained HTML page, JSON for scripts, and SARIF for a check in CI.

The one HTML renderer (ADR-5): `--format html` and the app's .html download both run the traced markdown
through to_html, so the two can never disagree. The page loads nothing (no script, link, image or url()), so it
opens offline from a file share, and every character of data is escaped: a search term is text, never markup.
It holds no version or date, so the same report always gives the same page.
"""
import html
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from . import __version__

FORMAT_VERSION = 1  # of the --format json output: a change that breaks a reader bumps it; a new key doesn't
CHECK_TITLE = "Number check"

INLINE = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|(?<!\w)_(.+?)_(?!\w)")
HEADING = re.compile(r"(#{1,6})\s+(.*)")
TABLE_RULE = re.compile(r"^\|?\s*:?-{3,}")
CELL = re.compile(r"(?<!\\)\|")
ITEM = {"ol": re.compile(r"\d+\.\s+(.*)"), "ul": re.compile(r"-\s+(.*)")}
STYLE = ("body{font:15px/1.55 system-ui,-apple-system,'Segoe UI',sans-serif;color:#1f2937;max-width:980px;"
         "margin:40px auto;padding:0 20px}h1,h2,h3{line-height:1.25}"
         "code{font:13px ui-monospace,Consolas,monospace;background:#f1f3f5;padding:1px 4px;border-radius:3px}"
         ".table{overflow-x:auto;margin:12px 0}table{border-collapse:collapse;min-width:100%}"
         "th,td{border:1px solid #dfe3e5;padding:6px 9px;text-align:left;vertical-align:top}th{background:#f6f7f8}"
         "hr{border:0;border-top:1px solid #dfe3e5;margin:28px 0}")


def _inline(text):
    out, pos = [], 0
    for m in INLINE.finditer(text):
        code, strong, em = m.groups()
        out.append(html.escape(text[pos:m.start()]))
        if code is not None:
            out.append(f"<code>{html.escape(code)}</code>")
        elif strong is not None:
            out.append(f"<strong>{_inline(strong)}</strong>")
        else:
            out.append(f"<em>{_inline(em)}</em>")
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def _cells(row):
    parts = CELL.split(row.strip())
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return [_inline(p.strip().replace("\\|", "|")) for p in parts]


def _blocks(lines):
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    while i < len(lines):
        s = lines[i].strip()
        heading = HEADING.match(s)
        kind = next((k for k, rx in ITEM.items() if rx.match(s)), None)
        table = s.startswith("|") and i + 1 < len(lines) and TABLE_RULE.match(lines[i + 1].strip())
        if s and not (heading or kind or table or s == "---"):
            para.append(s)
            i += 1
            continue
        flush()
        if heading:
            n = len(heading.group(1))
            out.append(f"<h{n}>{_inline(heading.group(2))}</h{n}>")
        elif s == "---":
            out.append("<hr>")
        elif kind:
            items = []
            while i < len(lines) and (m := ITEM[kind].match(lines[i].strip())):
                items.append(f"<li>{_inline(m.group(1))}</li>")
                i += 1
            out.append(f"<{kind}>{''.join(items)}</{kind}>")
            continue
        elif table:
            head = "".join(f'<th scope="col">{c}</th>' for c in _cells(s))
            rows, i = [], i + 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in _cells(lines[i])) + "</tr>")
                i += 1
            out.append(f'<div class="table"><table><thead><tr>{head}</tr></thead>'
                       f"<tbody>{''.join(rows)}</tbody></table></div>")
            continue
        i += 1
    flush()
    return out


def to_html(markdown: str, title: str) -> str:
    """A report or check, as one HTML page that opens anywhere."""
    body = "\n".join(_blocks(markdown.splitlines()))
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{html.escape(title)}</title>\n<style>{STYLE}</style>\n</head>\n<body>\n{body}\n</body>\n</html>")


def _json(obj):
    return json.dumps({"format_version": FORMAT_VERSION, "openppc": __version__, **obj}, indent=2, default=str,
                      ensure_ascii=False)


def audit_json(template, title, markdown, book, passed):
    """An audit for scripts: the report, whether it passed its own check, every fact and the template's results."""
    return _json({"template": template, "title": title, "passed": passed, "markdown": markdown,
                  "facts": [asdict(f) for f in book.facts], "cards": book.cards})


def check_result(claims, contradictions, markdown):
    """A check's results. passed is what the exit code says: no wrong number, wrong label or contradiction
    (a figure that can't be checked is never held against an audit)."""
    counts = {
        "total": len(claims),
        "traced": sum(c.verdict == "traced" for c in claims),
        "mismatch": sum(c.verdict == "mismatch" for c in claims),
        "not_in_data": sum(c.verdict == "not in data" for c in claims),
        "cant_check": sum(c.verdict == "can't check" for c in claims),
        "contradictions": len(contradictions),
    }
    return {"passed": not (counts["mismatch"] or counts["not_in_data"] or contradictions), "counts": counts,
            "claims": [asdict(c) for c in claims],
            "contradictions": [{"line": n, "problem": p, "context": ctx} for n, p, ctx in contradictions],
            "markdown": markdown}


SARIF_RULES = {  # verdict: (rule id, level, what it means)
    "not in data": ("wrong-number", "error", "A number that doesn't match the data the audit was written from."),
    "mismatch": ("wrong-label", "error", "A real figure from the data, on the wrong metric or row."),
    "contradiction": ("contradiction", "error", "A sentence that contradicts its own numbers."),
    "can't check": ("cant-check", "note", "A target, forecast or the audit's own working, which an export can't "
                                          "confirm. Never held against the audit."),
}


def _uri(path):
    """The audit's path as code scanning wants it: relative to the working folder, else an absolute file URI."""
    try:
        rel = os.path.relpath(path)
    except ValueError:  # another drive on Windows
        rel = ".."
    return Path(path).resolve().as_uri() if rel.startswith("..") else Path(rel).as_posix()


def to_sarif(result, audit_path):
    """A check as SARIF 2.1.0, for GitHub code scanning and other CI tools: one result per wrong number, wrong label,
    contradiction or figure that can't be checked, at its line in the audit."""
    uri = _uri(audit_path)
    found = [(c["verdict"], c["line"], f"{c['written']}: {c['detail']}") for c in result["claims"]
             if c["verdict"] != "traced"]
    found += [("contradiction", c["line"], c["problem"]) for c in result["contradictions"]]
    rules = [{"id": rid, "shortDescription": {"text": text}, "defaultConfiguration": {"level": level}}
             for rid, level, text in SARIF_RULES.values()]
    return json.dumps({
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "OpenPPC", "version": __version__,
                                "informationUri": "https://github.com/secondsteplabs/openppc", "rules": rules}},
            "results": [{"ruleId": SARIF_RULES[verdict][0], "level": SARIF_RULES[verdict][1],
                         "message": {"text": text},
                         "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri},
                                                             "region": {"startLine": line}}}]}
                        for verdict, line, text in sorted(found, key=lambda f: f[1])],
        }],
    }, indent=2, ensure_ascii=False)


def audit_as(fmt, template, markdown, book, passed):
    if fmt == "md":
        return markdown
    if fmt == "html":
        return to_html(markdown, template.TITLE)
    if fmt == "json":
        return audit_json(template.NAME, template.TITLE, markdown, book, passed)
    raise ValueError(f"unknown format '{fmt}'")


def check_as(fmt, result, audit_path=""):
    if fmt == "md":
        return result["markdown"]
    if fmt == "html":
        return to_html(result["markdown"], CHECK_TITLE)
    if fmt == "json":
        return _json(result)
    if fmt == "sarif":
        return to_sarif(result, audit_path)
    raise ValueError(f"unknown format '{fmt}'")

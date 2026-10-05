"""Browser bridge. The web app runs this package inside Pyodide and calls these functions.

Arguments are plain strings (paths inside the in-browser file system, or text) and every
function returns a JSON string, except count_numbers. Nothing here touches the network.
"""
import itertools
import json
import os
from dataclasses import asdict

from . import __version__
from .checkfacts import facts_for_paths
from .engine import benchmarks
from .engine.trace import render_check, trace
from .ingest import load_report
from .ingest.account import is_snapshot, read_json, snapshot
from .templates import TEMPLATES, account_read, load_input, run_template, run_template_book
from .facts import SYMBOLS
from .templates._common import fingerprint, min_cost_for

READ_ERRORS = (ValueError, KeyError, TypeError, UnicodeDecodeError, OSError)
KEEP_AUDITS = 8  # recent audits whose facts the app can still check a branded PDF against
_BOOKS = {}
_TOKENS = itertools.count(1)
WRONG_FILE = ("Export a Search terms or Keywords report from Google Ads: Campaigns > Insights and "
              "reports > Search terms, pick the date range, then Download > .csv.")


def _json(obj):
    return json.dumps(obj, default=str)


def _clean(error, paths):
    """Error text without the in-browser folder names."""
    text = str(error)
    for p in paths:
        text = text.replace(p, os.path.basename(p))
    return text


def meta():
    """Version, templates and industries for the page's pickers."""
    return _json({
        "version": __version__,
        "templates": [{"name": t.NAME, "title": t.TITLE, "input": t.INPUT, "summary": t.SUMMARY,
                       "kind": t.INPUT_KIND} for t in TEMPLATES.values()],
        "industries": [{"key": k, "name": row[0]} for k, row in benchmarks.TABLE.items()],
    })


def inspect_file(path):
    """What the file chip shows, and which templates can read the file."""
    name = os.path.basename(path)
    try:
        if path.lower().endswith(".json"):
            raw = read_json(path)
            if is_snapshot(raw):
                data = snapshot(raw, source=path)
                fits = [t.NAME for t in TEMPLATES.values() if t.INPUT_KIND == "account" and t.accepts(data)]
                return _json({"ok": True, "name": name, "kind": "Account snapshot", "rows": len(data["campaigns"]),
                              "start": None, "end": None, "days": None,
                              "currency": (data["meta"].get("currency") or None), "templates": fits})
            data = account_read.load_metrics(path)
            fits = [t.NAME for t in TEMPLATES.values() if t.INPUT_KIND == "metrics" and t.accepts(data)]
            return _json({"ok": True, "name": name, "kind": "Two-period totals", "rows": None, "start": None,
                          "end": None, "days": None, "currency": None, "templates": fits})
        report = load_report(path)
    except READ_ERRORS as e:
        error = _clean(e, [path])
        if error.startswith(name + ": "):  # the file chip already shows the name, right above the error
            error = error[len(name) + 2:]
        return _json({"ok": False, "name": name, "error": error, "hint": WRONG_FILE})
    if report.has("search_term"):
        kind = "Search terms report"
    elif report.has("keyword"):
        kind = "Keywords report"
    else:
        kind = "Google Ads report"
    fits = [t.NAME for t in TEMPLATES.values() if t.INPUT_KIND == "report" and t.accepts(report)]
    return _json({"ok": True, "name": name, "kind": kind, "rows": len(report.rows),
                  "start": report.start.isoformat() if report.start else None,
                  "end": report.end.isoformat() if report.end else None,
                  "days": report.days, "currency": report.currency, "templates": fits,
                  "currency_sign": SYMBOLS.get((report.currency or "").upper(), ""),
                  "min_cost": min_cost_for(report.currency)[0]})


def count_numbers(text):
    """How many numbers in the text the check will judge."""
    claims, _ = trace(text, [])
    return len(claims)


def check(text, paths_json, industry=""):
    """Check every number in an audit against the files (and optionally an industry's averages)."""
    paths = json.loads(paths_json)
    try:
        facts = facts_for_paths(paths, industry or None)
    except READ_ERRORS as e:
        return _json({"ok": False, "error": _clean(e, paths)})
    claims, contradictions = trace(text, facts)
    counts = {
        "total": len(claims),
        "traced": sum(c.verdict == "traced" for c in claims),
        "mismatch": sum(c.verdict == "mismatch" for c in claims),
        "not_in_data": sum(c.verdict == "not in data" for c in claims),
        "cant_check": sum(c.verdict == "can't check" for c in claims),
        "contradictions": len(contradictions),
    }
    return _json({"ok": True, "counts": counts, "claims": [asdict(c) for c in claims],
                  "contradictions": [{"line": n, "problem": p, "context": ctx} for n, p, ctx in contradictions],
                  "markdown": render_check(claims, contradictions)})


def audit(name, path, industry="", min_cost=None, brand=""):
    """Run a template on a file. The report has already passed its own number check when passed is true."""
    template = TEMPLATES.get(name)
    if template is None:
        return _json({"ok": False, "error": f"unknown template '{name}'"})
    wrong = _json({"ok": False, "error": f"{os.path.basename(path)} is not a {template.INPUT}."})
    try:
        data = load_input(template, path)
    except READ_ERRORS:
        return wrong
    if not template.accepts(data):
        return wrong
    try:
        cost = None if min_cost in (None, "") else float(min_cost)  # unset: the default in the export's currency
        markdown, book, passed = run_template_book(name, path, industry=industry or None, min_cost=cost,
                                                   brand=brand or None)
    except READ_ERRORS as e:
        return _json({"ok": False, "error": _clean(e, [path])})
    token = f"audit-{next(_TOKENS)}"
    _BOOKS[token] = book
    while len(_BOOKS) > KEEP_AUDITS:
        _BOOKS.pop(next(iter(_BOOKS)))
    return _json({"ok": True, "title": template.TITLE, "markdown": markdown, "passed": passed,
                  "facts": len(book.facts), "cards": book.cards, "client": book.client or None, "token": token,
                  "fingerprint": fingerprint(path)})


def verify(token, text, names_json="[]"):
    """Check the text of a finished branded PDF against the audit it was made from.

    The names the user typed (agency, client, report title) are set aside first: they are words
    on the page, not claims about the account, even when they hold digits."""
    book = _BOOKS.get(token)
    if book is None:
        return _json({"ok": False, "error": "This audit is no longer loaded. Run it again, then make the PDF."})
    names = {n.strip() for n in json.loads(names_json or "[]") if isinstance(n, str) and n.strip()}
    for name in sorted(names, key=len, reverse=True):
        text = text.replace(name, "Name")
    claims, contradictions = trace(text, book.facts)
    bad = [c for c in claims if c.verdict != "traced"]
    problems = [{"written": c.written, "verdict": c.verdict, "detail": c.detail, "context": c.context} for c in bad]
    problems += [{"written": "", "verdict": "contradiction", "detail": p, "context": ctx} for _, p, ctx in contradictions]
    return _json({"ok": True, "total": len(claims), "traced": len(claims) - len(bad), "problems": problems})

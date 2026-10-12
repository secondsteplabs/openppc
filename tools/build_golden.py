"""Build tests/golden/: what OpenPPC shows users today, so a change to any of it is seen and reviewed.

It holds every template's report on the sample and on each fixture, the app's cards and the branded client
report's pages, `check` on the sample audit, the sample reports and check as HTML, the MCP tools' answers, and
each site page's title, description and H1. Run it after an intended change, and review the diff before committing:

    python tools/build_golden.py

tests/test_golden.py fails when a file differs from what the code produces now.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "golden"
FIXTURES = ROOT / "tests" / "fixtures"


def _json(data):
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False)


def _seo():
    lines = []
    for page in sorted((ROOT / "site" / "pages").rglob("*.html")):
        text = page.read_text(encoding="utf-8")
        meta = dict(re.findall(r"^(title|description): (.*)$", text.split("-->", 1)[0], re.M))
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S)
        lines += [page.relative_to(ROOT).as_posix(), f"  title: {meta.get('title')}",
                  f"  description: {meta.get('description')}",
                  f"  h1: {re.sub(r'<[^>]+>', '', h1.group(1)).strip() if h1 else None}"]
    return "\n".join(lines)


def golden():
    """{file name: text}."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from openppc import mcp_server, samples
    from openppc.checkfacts import facts_for_check
    from openppc.engine.trace import render_check, trace
    from openppc.formats import CHECK_TITLE, to_html
    from openppc.ingest import load_report
    from openppc.ingest.editor import is_editor_export
    from openppc.templates import TEMPLATES, run_template_book

    out = {}
    for name in sorted(TEMPLATES):
        path = str(samples.path(samples.EXPORTS[name]))
        for label, industry in (("", None), ("-industry", samples.INDUSTRY)):
            markdown, book, passed = run_template_book(name, path, industry=industry)
            out[f"sample-{name}{label}.md"] = f"<!-- passed: {passed} -->\n{markdown}"
            out[f"sample-{name}{label}.json"] = _json({"cards": book.cards, "client": book.client})
            if not label:
                out[f"sample-{name}.html"] = to_html(markdown, TEMPLATES[name].TITLE)
        out[f"mcp-audit_account-{name}.md"] = mcp_server.audit_account(name, path, samples.INDUSTRY)
    pair = [str(samples.path(samples.EXPORTS["search-term-waste"])), str(samples.path("search_terms_acme_june.csv"))]
    markdown, _, passed = run_template_book("account-read", pair)
    out["sample-account-read-pair.md"] = f"<!-- passed: {passed} -->\n{markdown}"
    audit = samples.path(samples.AUDIT).read_text(encoding="utf-8")
    data = [str(samples.path(samples.AUDIT_DATA))]
    for label, industry in (("", None), ("-industry", samples.INDUSTRY)):
        out[f"check-sample{label}.md"] = render_check(*trace(audit, facts_for_check(audit, data, industry)))
    out["check-sample.html"] = to_html(out["check-sample.md"], CHECK_TITLE)
    out["mcp-check_numbers.md"] = mcp_server.check_numbers(audit, data)
    for path in sorted(FIXTURES.glob("*.csv")):
        if is_editor_export(path):
            markdown, _, passed = run_template_book("account-structure", str(path))
            out[f"fixture-{path.stem}-account-structure.md"] = f"<!-- passed: {passed} -->\n{markdown}"
        try:
            report = load_report(path)
        except ValueError as e:
            out[f"fixture-{path.stem}.md"] = "refused: " + str(e).replace(str(path), path.name)
            continue
        for name, template in sorted(TEMPLATES.items()):
            if template.INPUT_KIND == "report" and template.accepts(report):
                markdown, _, passed = run_template_book(name, str(path), report)
                out[f"fixture-{path.stem}-{name}.md"] = f"<!-- passed: {passed} -->\n{markdown}"
    out["site-seo.txt"] = _seo()
    return {name: text.rstrip("\n") + "\n" for name, text in out.items()}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    built = golden()
    for stale in set(p.name for p in OUT.iterdir()) - set(built):
        (OUT / stale).unlink()
    for name, text in built.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {len(built)} files to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""--format html and json: one HTML renderer (ADR-5) whose numbers are the report's, and JSON that matches its schema."""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from openppc import formats
from openppc.cli import main
from openppc.templates import TEMPLATES

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden"
SCHEMAS = ROOT / "openppc" / "schemas"
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
REPORTS = sorted(p for p in GOLDEN.glob("*.md") if not p.read_text(encoding="utf-8").startswith("refused:"))


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _text(page):
    parser = _Text()
    parser.feed(page)
    return " ".join(parser.parts)


def _markdown(path):
    text = path.read_text(encoding="utf-8")
    return text.split("\n", 1)[1] if text.startswith("<!--") else text  # the golden file's own "passed" line


@pytest.mark.parametrize("path", REPORTS, ids=lambda p: p.stem)
def test_the_html_has_exactly_the_reports_numbers(path):
    markdown = _markdown(path)
    page = formats.to_html(markdown, "Report")
    body = page.split("<body>", 1)[1]
    numbered = re.sub(r"^\s*\d+\.\s+", "", markdown, flags=re.M)  # a list's own numbering becomes <ol>
    assert NUMBER.findall(_text(body)) == NUMBER.findall(numbered)


@pytest.mark.parametrize("path", REPORTS, ids=lambda p: p.stem)
def test_the_html_loads_nothing(path):
    page = formats.to_html(_markdown(path), "Report").lower()
    for loads in ("<script", "<link", "<img", "<iframe", "<object", "src=", "href=", "url(", "@import"):
        assert loads not in page


def test_data_in_a_report_is_text_never_markup():
    markdown = ("# Waste\n\n<script>alert(1)</script> and <img src=x onerror=alert(1)>\n\n| Search term | Cost |\n"
                "|---|---|\n| <b>bold</b> \\| pipe | $5.00 |\n")
    page = formats.to_html(markdown, "<title>")
    assert "<script>alert" not in page and "<img" not in page and "<b>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "<title>&lt;title&gt;</title>" in page
    assert "<td>&lt;b&gt;bold&lt;/b&gt; | pipe</td><td>$5.00</td>" in page


def test_the_page_is_the_same_whatever_the_version(monkeypatch):
    markdown = _markdown(GOLDEN / "sample-search-term-waste.md")
    page = formats.to_html(markdown, "Report")
    monkeypatch.setattr(formats, "__version__", "9.9.9")
    assert formats.to_html(markdown, "Report") == page and "9.9.9" not in page


def _schema(name):
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_audit_json_matches_its_schema(name, capsys):
    jsonschema = pytest.importorskip("jsonschema")
    assert main(["audit", name, "--sample", "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    jsonschema.validate(data, _schema("audit-report.schema.json"))
    assert data["format_version"] == formats.FORMAT_VERSION and data["template"] == name and data["passed"]
    assert main(["audit", name, "--sample"]) == 0
    assert data["markdown"] == capsys.readouterr().out.rstrip("\n")


def test_check_json_matches_its_schema_and_the_exit_code(capsys):
    jsonschema = pytest.importorskip("jsonschema")
    assert main(["check", "--sample", "--format", "json"]) == 2
    data = json.loads(capsys.readouterr().out)
    jsonschema.validate(data, _schema("check-report.schema.json"))
    assert data["passed"] is False and data["counts"]["total"] == len(data["claims"])
    assert data["markdown"] == (GOLDEN / "check-sample-industry.md").read_text(encoding="utf-8").rstrip("\n")


def test_html_from_the_command_line_and_the_same_exit_codes(capsys, tmp_path):
    out = tmp_path / "report.html"
    assert main(["audit", "search-term-waste", "--sample", "--format", "html", "--out", str(out)]) == 0
    page = out.read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>") and "<title>Search-term waste audit</title>" in page
    assert main(["check", "--sample", "--format", "html"]) == 2
    assert "<title>Number check</title>" in capsys.readouterr().out
    with pytest.raises(SystemExit) as usage:
        main(["audit", "search-term-waste", "--sample", "--format", "pdf"])
    assert usage.value.code == 1


def test_the_schemas_ship_inside_the_package():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'packages = ["openppc"]' in pyproject  # hatch ships every file under openppc/, json included
    assert {p.name for p in SCHEMAS.glob("*.json")} == {"audit-report.schema.json", "check-report.schema.json"}

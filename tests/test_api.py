"""The stable engine API (ADR-2): FactBook, trace, load_report, run_template, the Template protocol and to_html import
from where the ADR names them, every template provides what the protocol lists, and py.typed ships with them."""
from pathlib import Path

from openppc.engine.trace import trace
from openppc.facts import FactBook
from openppc.formats import to_html
from openppc.ingest import load_report
from openppc.templates import TEMPLATES, Template, run_template

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "examples" / "search_terms_acme.csv"


def test_every_template_provides_what_the_protocol_lists():
    for t in TEMPLATES.values():
        missing = [name for name in Template.__annotations__ if not hasattr(t, name)]
        assert not missing, (t.NAME, missing)
        assert callable(t.accepts) and callable(t.run)
        assert t.INPUT_KIND in ("report", "metrics", "account")


def test_the_api_runs_from_an_export_to_traced_numbers():
    report = load_report(SAMPLE)
    assert len(report.rows) == 18 and report.days == 31
    markdown, facts, passed = run_template("search-term-waste", SAMPLE)
    claims, contradictions = trace(markdown, facts)
    assert passed and claims and not contradictions and all(c.verdict == "traced" for c in claims)
    book = FactBook(currency="EUR")
    assert book.money("cost of the account", 1234.5) == "€1,234.50" and book.facts[0].currency == "EUR"
    page = to_html(markdown, "Search-term waste")
    assert page.startswith("<!doctype html>") and "<title>Search-term waste</title>" in page


def test_the_package_ships_its_types_and_mypy_checks_the_api():
    assert (ROOT / "openppc" / "py.typed").is_file()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for path in ("openppc/facts.py", "openppc/ingest/google_ads_csv.py", "openppc/templates/__init__.py"):
        assert f'"{path}"' in pyproject

"""The fixture corpus: one export per real-world variant, each read the way Google meant it.

The files are built by tools/build_fixtures.py; the first test fails when one drifts from its recipe.
"""
import importlib.util
from pathlib import Path

import pytest

from openppc.checkfacts import facts_for_paths
from openppc.engine.trace import trace
from openppc.ingest import load_report
from openppc.templates import TEMPLATES, run_template

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
BASE_COST = 4347.25   # the cost of the 14 search terms most fixtures share, whatever their format
BASE_CLICKS = 615


def _builder():
    spec = importlib.util.spec_from_file_location("build_fixtures", ROOT / "tools" / "build_fixtures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixtures_match_their_recipes():
    built = _builder().fixtures()
    on_disk = {p.name for p in FIXTURES.glob("*.csv")}
    assert on_disk == set(built), "run python tools/build_fixtures.py"
    stale = [name for name, data in built.items() if (FIXTURES / name).read_bytes() != data]
    assert not stale, f"stale fixtures {stale}: run python tools/build_fixtures.py"
    stale = [name for name, data in _builder().examples().items() if (ROOT / "examples" / name).read_bytes() != data]
    assert not stale, f"stale examples {stale}: run python tools/build_fixtures.py"


@pytest.mark.parametrize("name, currency", [
    ("search_terms_de.csv", "EUR"),          # 1.254,40 and semicolons
    ("search_terms_fr.csv", "EUR"),          # 1 254,40 € with narrow no-break spaces
    ("search_terms_utf16.csv", "USD"),       # Excel's UTF-16, tab separated
    ("search_terms_renamed.csv", "USD"),     # "Impressions", "Search term match type", "Currency"
    ("search_terms_july.csv", "USD"),
    ("search_terms_pmax.csv", "USD"),
    ("search_terms_microsoft.csv", "USD"),   # Spend, Conv., report lines above and a Total row under the table
])
def test_every_format_reads_to_the_same_numbers(name, currency):
    report = load_report(FIXTURES / name)
    assert (report.currency, len(report.rows)) == (currency, 14)
    assert sum(r["cost"] for r in report.rows) == pytest.approx(BASE_COST)
    assert sum(r["clicks"] for r in report.rows) == BASE_CLICKS
    assert report.has("match_type", "impressions")


def test_indian_grouping_reads_lakhs():
    report = load_report(FIXTURES / "search_terms_en_in.csv")
    assert (report.currency, report.rows[0]["cost"]) == ("INR", pytest.approx(119168.0))
    assert sum(r["cost"] for r in report.rows) == pytest.approx(BASE_COST * 95)


def test_a_legacy_encoding_is_read():
    assert load_report(FIXTURES / "search_terms_cp1252.csv").rows[0]["search_term"] == "plombier café montréal"


@pytest.mark.parametrize("name, message", [
    ("search_terms_german_headers.csv", "column names will not match"),
    ("search_terms_mixed_formats.csv", "mix two styles"),
    ("editor_export.csv", "Google Ads Editor export. Use it with the account-structure template"),
])
def test_a_file_that_cannot_be_read_right_is_refused_with_a_reason(name, message):
    with pytest.raises(ValueError, match=message):
        load_report(FIXTURES / name)


def test_a_microsoft_advertising_report_says_so_and_keeps_its_search_campaigns_in_search():
    report = load_report(FIXTURES / "search_terms_microsoft.csv")
    assert (report.platform, report.title, report.days) == ("Microsoft Advertising", "Search terms report", 31)
    markdown, _, passed = run_template("search-term-waste", FIXTURES / "search_terms_microsoft.csv")
    assert passed and "Microsoft Advertising export (experimental)" in markdown.split("\n")[2]
    assert "Performance Max and other automated campaigns" not in markdown  # "Search & content" is Search
    assert "Microsoft" not in run_template("search-term-waste", FIXTURES / "search_terms_july.csv")[0]


def test_fractional_conversions_keep_their_decimals():
    report = load_report(FIXTURES / "search_terms_fractional.csv")
    assert any(r["conversions"] % 1 for r in report.rows)
    assert run_template("search-term-waste", FIXTURES / "search_terms_fractional.csv")[2]


@pytest.mark.parametrize("name", ["search_terms_zero_cost.csv", "search_terms_no_waste.csv"])
def test_an_account_with_nothing_to_flag_still_reports_cleanly(name):
    assert run_template("search-term-waste", FIXTURES / name, min_cost=0)[2]


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("search_terms_*.csv")
                                        if "headers" not in p.name and "mixed" not in p.name))
def test_every_report_template_passes_check_mode_on_every_fixture(name):
    """Our own thresholds are settings, not account data, so check mode rightly cannot trace them; every other
    number must."""
    path = FIXTURES / name
    report = load_report(path)
    for template in TEMPLATES.values():
        if template.INPUT_KIND != "report" or not template.accepts(report):
            continue
        markdown, facts, passed = run_template(template.NAME, path)
        assert passed, template.NAME
        thresholds = {f.value for f in facts if f.metric == "rule"}
        claims, contradictions = trace(markdown, facts_for_paths([path]))
        assert [c.written for c in claims if c.verdict != "traced" and c.value not in thresholds] == [], template.NAME
        assert contradictions == [], template.NAME


def test_a_term_wasting_money_across_ad_groups_is_flagged_once():
    # $15 in each of three ad groups: under the $20 threshold row by row, $45 as one search term
    markdown, _, _ = run_template("search-term-waste", FIXTURES / "search_terms_duplicates.csv")
    assert "**1 search term spent $45.00 and never converted.**" in markdown
    ranked = markdown.split("## Wasted spend, ranked")[1].split("## ")[0]
    assert ranked.count("leaking tap repair") == 1

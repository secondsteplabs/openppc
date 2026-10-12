"""Meta Ads Manager exports (experimental): read into the same columns as a Google Ads report, compared as two
periods by account-read, and refused with a reason everywhere a search export is needed."""
import json
from pathlib import Path

import pytest

from openppc import webapi
from openppc.checkfacts import facts_for_paths
from openppc.engine.findings import classify
from openppc.engine.trace import trace
from openppc.ingest import load_report
from openppc.templates import run_template

FIXTURES = Path(__file__).resolve().parent / "fixtures"
JUNE, JULY = FIXTURES / "meta_june.csv", FIXTURES / "meta_july.csv"
LEAD = "actions:offsite_conversion.fb_pixel_lead"


def _export(tmp_path, text, name="meta.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_meta_export_reads_into_the_same_columns():
    report = load_report(JULY)
    assert (report.platform, report.currency, report.result) == ("Meta Ads Manager", "EUR", LEAD)
    assert (report.start.isoformat(), report.end.isoformat(), report.days) == ("2026-07-01", "2026-07-31", 31)
    assert len(report.rows) == 5  # the summary row above the ad sets is not one of them
    assert sum(r["cost"] for r in report.rows) == pytest.approx(3213.4)
    assert sum(r["clicks"] or 0 for r in report.rows) == 2408  # one ad set's blank Link clicks is none
    assert sum(r["conversions"] or 0 for r in report.rows) == 94
    assert report.notes == ["Meta's link clicks counted as clicks and its Results as conversions"]


def test_two_meta_periods_compare_with_account_read_and_every_number_traces():
    markdown, facts, passed = run_template("account-read", [JULY, JUNE], industry="home-services")
    assert passed
    assert "`meta_july.csv` (current) and `meta_june.csv` (prior) · Meta Ads Manager exports (experimental)" in markdown
    assert "a Meta report leaves them out" in markdown and "## Against the" not in markdown
    assert LEAD not in markdown  # a custom conversion's id is a number the report could not trace
    rules = {f.value for f in facts if f.metric == "rule"}
    claims, contradictions = trace(markdown, facts_for_paths([JULY, JUNE]))
    assert [c.written for c in claims if c.verdict != "traced" and c.value not in rules] == []
    assert contradictions == []


def test_a_results_column_counting_different_things_is_refused():
    with pytest.raises(ValueError, match="counts different things in different rows .* one file per result type"):
        load_report(FIXTURES / "meta_mixed_results.csv")


def test_results_without_a_result_indicator_are_not_conversions(tmp_path):
    path = _export(tmp_path, "Reporting starts,Reporting ends,Campaign name,Results,Amount spent (USD),Link clicks,"
                             "Impressions\n2026-07-01,2026-07-31,Leads,12,300.00,90,4000\n")
    report = load_report(path)
    assert not report.has("conversions") and "conversions" not in report.rows[0]
    assert "Results not counted as conversions" in report.notes[0]
    with pytest.raises(ValueError, match="has no Results it can count as conversions"):
        run_template("account-read", [path, JUNE])


def test_two_periods_counting_different_results_are_refused(tmp_path):
    july = JULY.read_text(encoding="utf-8").replace(LEAD, "actions:link_click")
    with pytest.raises(ValueError, match="counts actions:link_click as its Results .* the same result type"):
        run_template("account-read", [_export(tmp_path, july), JUNE])


def test_a_meta_export_without_its_dates_is_told_what_to_add(tmp_path):
    path = _export(tmp_path, "Campaign name,Results,Result indicator,Amount spent (EUR),Link clicks,Impressions\n"
                             f"Leads,12,{LEAD},300.00,90,4000\n")
    with pytest.raises(ValueError, match="Meta Ads Manager export without its Reporting starts and Reporting ends"):
        load_report(path)


def test_a_google_export_with_a_results_column_is_read_as_google(tmp_path):
    path = _export(tmp_path, "Search terms report\nJuly 1, 2026 - July 31, 2026\n"
                             "Search term,Clicks,Impr.,Cost,Conversions,Results\nplumber,10,100,50.00,2,7\n")
    report = load_report(path)
    assert (report.platform, report.rows[0]["conversions"]) == ("Google Ads", 2)


@pytest.mark.parametrize("name", ["search-term-waste", "keyword-audit"])
def test_a_search_audit_given_a_meta_export_says_what_it_is(name):
    with pytest.raises(ValueError, match="meta_july.csv is a Meta Ads Manager export, which has no search terms"):
        run_template(name, JULY)


def test_the_app_names_a_meta_export_so_two_of_them_pair():
    info = json.loads(webapi.inspect_file(str(JULY)))
    assert (info["kind"], info["templates"], info["currency"]) == ("Meta Ads Manager report", [], "EUR")
    pair = json.loads(webapi.inspect_pair(json.dumps([str(JUNE), str(JULY)])))
    assert pair == {"ok": True, "paths": [str(JULY), str(JUNE)]}


def test_reach_dilution_on_meta_names_audiences_not_match_types():
    m = {"cs": 1000, "ps": 1000, "ci": 20000, "pi": 10000, "cc": 100, "pc": 100, "cv": 30, "pv": 30}
    search = next(f for f in classify(m)[1] if f.startswith("REACH DILUTION"))
    meta = next(f for f in classify(m, search=False)[1] if f.startswith("REACH DILUTION"))
    assert "Broad matching" in search and "Broad matching" not in meta and "placements" in meta

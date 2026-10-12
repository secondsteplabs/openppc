"""A Google Ads Editor export reads into the same account snapshot as OpenPPC's JSON."""
import json
from pathlib import Path

import pytest

from openppc import webapi
from openppc.checkfacts import facts_for_paths
from openppc.engine.trace import trace
from openppc.ingest.account import _geo, load_snapshot
from openppc.ingest.editor import is_editor_export, load_editor
from openppc.templates import run_template
from openppc.templates.account_structure import evaluate

FIXTURES = Path(__file__).parent / "fixtures"
EDITOR = FIXTURES / "editor_export.csv"
CAMPAIGNS = "Campaign\tCampaign Type\tCampaign Status\tBudget\tBudget type\tAd Group\tAd Group Status\n"


def results(data):
    checks, _, _ = evaluate(data)
    return {c.title: (c.status, c.summary) for c in checks}


def test_every_kind_of_row_lands_in_its_section():
    data = load_editor(EDITOR)
    assert [c["name"] for c in data["campaigns"]] == ["Birch Lane | Search", "Birch Lane | Brand"]
    assert {(g["campaign_id"], g["name"], g["status"]) for g in data["ad_groups"]} == {
        ("Birch Lane | Search", "Core", "ENABLED"), ("Birch Lane | Search", "Drains", "ENABLED"),
        ("Birch Lane | Search", "Old offers", "PAUSED"), ("Birch Lane | Brand", "Brand", "ENABLED")}
    assert (len(data["keywords"]), len(data["negatives"]), len(data["ads"]), len(data["assets"])) == (7, 2, 2, 4)


def test_campaign_settings_are_read_from_editor_words():
    search, brand = load_editor(EDITOR)["campaigns"]
    assert (search["channel"], search["bidding"], search["enhanced_cpc"], search["display_network"]) == (
        "SEARCH", "MANUAL_CPC", False, True)
    assert (search["geo_target_type"], brand["geo_target_type"]) == ("PRESENCE", "PRESENCE_OR_INTEREST")
    assert brand["bidding"] == "MAXIMIZE_CONVERSIONS" and brand["display_network"] is False


def test_keywords_keep_match_type_status_and_quality():
    kws = {k["text"]: k for k in load_editor(EDITOR)["keywords"]}
    assert kws["drain cleaning"]["match_type"] == "PHRASE"
    assert kws["blocked drain"]["match_type"] == "EXACT"                  # [brackets] with no Criterion Type
    assert (kws["blocked drain"]["status"], kws["blocked drain"]["serving"]) == ("ENABLED", "RARELY_SERVED")
    assert (kws["plumber near me"]["quality_score"], kws["plumber near me"]["expected_ctr"]) == (4, "BELOW_AVERAGE")


def test_negatives_ads_and_assets():
    data = load_editor(EDITOR)
    assert {(n["level"], n["text"], n["match_type"]) for n in data["negatives"]} == {
        ("CAMPAIGN", "jobs", "BROAD"), ("AD_GROUP", "plumber", "PHRASE")}
    core = next(a for a in data["ads"] if a["ad_group_id"].endswith("Core"))
    assert core["type"] == "RESPONSIVE_SEARCH_AD" and core["strength"] == "POOR"
    assert [h["pin"] for h in core["headlines"]] == ["HEADLINE_1", None, None]
    assert sorted(a["type"] for a in data["assets"]) == ["CALLOUT", "CALLOUT", "SITELINK", "SITELINK"]


def test_the_structure_audit_runs_on_an_editor_export_and_checks_itself():
    _, _, passed = run_template("account-structure", EDITOR, brand="birch lane")
    assert passed
    markdown, facts, passed = run_template("account-structure", EDITOR)  # check mode is not told the brand
    assert passed
    assert "Source: `editor_export.csv`" in markdown and "currency" not in markdown.split("\n")[2]
    assert "| drain cleaning | Phrase | Core, Drains |" in markdown
    thresholds = {f.value for f in facts if f.metric == "rule"}  # settings, not account data
    claims, contradictions = trace(markdown, facts_for_paths([EDITOR]))
    assert [c.written for c in claims if c.verdict != "traced" and c.value not in thresholds] == []
    assert not contradictions


def test_a_missing_column_means_not_in_this_file(tmp_path):
    path = tmp_path / "campaigns_only.csv"
    path.write_text("Campaign,Campaign Type,Campaign Status,Ad Group,Ad Group Status\n"
                    "Acme | Search,Search,Enabled,,\n", encoding="utf-8")
    data = load_editor(path)
    assert data["campaigns"][0]["status"] == "ENABLED"
    assert data["keywords"] is None and data["ads"] is None and data["assets"] is None


def test_an_ad_is_read_when_the_file_has_later_headlines_but_no_headline_1(tmp_path):
    path = tmp_path / "trimmed_columns.csv"
    path.write_text("Campaign,Campaign Status,Ad Group,Ad Group Status,Headline 2,Status\n"
                    "Acme | Search,Enabled,Core,Enabled,,\n"
                    "Acme | Search,Enabled,Core,Enabled,Same-day plumbers,Enabled\n", encoding="utf-8")
    ads = load_editor(path)["ads"]
    assert [[h["text"] for h in a["headlines"]] for a in ads] == [["Same-day plumbers"]]


def test_a_report_is_not_mistaken_for_an_editor_export(tmp_path):
    assert is_editor_export(EDITOR)
    assert not is_editor_export(FIXTURES / "search_terms_july.csv")
    assert not is_editor_export(tmp_path)  # a folder is not an export of any kind
    with pytest.raises(ValueError, match="not a Google Ads Editor export"):
        load_editor(FIXTURES / "search_terms_july.csv")


@pytest.mark.parametrize("cell, budget", [("1,250.00", 1250.0), ("120.00", 120.0), ("75", 75.0)])
def test_a_budget_is_read_with_a_decimal_point(tmp_path, cell, budget):
    path = tmp_path / "budgets.csv"
    path.write_text(CAMPAIGNS + f"Acme | Search\tSearch\tEnabled\t{cell}\tDaily\t\t\n", encoding="utf-16")
    assert load_editor(path)["campaigns"][0]["budget"] == budget


def test_a_budget_is_read_with_the_files_decimal_comma(tmp_path):
    path = tmp_path / "budgets_de.csv"
    path.write_text(CAMPAIGNS + "A\tSearch\tEnabled\t1.250,00\tDaily\t\t\nB\tSearch\tEnabled\t1.450\tDaily\t\t\n",
                    encoding="utf-16")
    assert [c["budget"] for c in load_editor(path)["campaigns"]] == [1250.0, 1450.0]


def test_budgets_in_two_number_styles_are_refused(tmp_path):
    path = tmp_path / "budgets_mixed.csv"
    path.write_text(CAMPAIGNS + "A\tSearch\tEnabled\t1,250.00\tDaily\t\t\nB\tSearch\tEnabled\t1.250,00\tDaily\t\t\n",
                    encoding="utf-16")
    with pytest.raises(ValueError, match="mix two styles"):
        load_editor(path)


def test_only_a_daily_budget_is_kept(tmp_path):
    path = tmp_path / "budget_total.csv"
    path.write_text(CAMPAIGNS + "A\tSearch\tEnabled\t3000.00\tCampaign total\t\t\n", encoding="utf-16")
    assert load_editor(path)["campaigns"][0]["budget"] is None


def test_editor_budgets_without_the_limited_flag_are_not_judged(tmp_path):
    """Editor has the daily budget but not whether Google limits the campaign by it, so the budget check can't
    pass or fail the account."""
    path = tmp_path / "budgets.csv"
    path.write_text(CAMPAIGNS + "A\tSearch\tEnabled\t120.00\tDaily\t\t\n", encoding="utf-16")
    assert results(load_editor(path))["Budget caps"] == (
        "missing", "Not in this file (whether a campaign is limited by budget)")


def test_a_disapproved_ad_in_editor_is_found(tmp_path):
    path = tmp_path / "approvals.csv"
    path.write_text("Campaign\tCampaign Status\tAd Group\tAd Group Status\tAd type\tHeadline 1\tStatus\t"
                    "Approval Status\n"
                    "A\tEnabled\tCore\tEnabled\tResponsive search ad\tSame-day plumbers\tEnabled\tDisapproved\n",
                    encoding="utf-16")
    assert results(load_editor(path))["Ads and keywords held back by policy"] == (
        "found", "1 disapproved, 0 limited")


def test_a_file_in_windows_1252_says_how_it_was_read(tmp_path):
    path = tmp_path / "cafe.csv"
    path.write_bytes("Campaign,Campaign Status,Ad Group,Ad Group Status\nCafé | Search,Enabled,,\n"
                     .encode("cp1252"))
    markdown, _, passed = run_template("account-structure", path)
    assert passed and "_How the file was read: the file is not in Unicode" in markdown


def test_the_web_app_recognizes_an_editor_export():
    chip = json.loads(webapi.inspect_file(str(EDITOR)))
    assert (chip["ok"], chip["kind"], chip["templates"], chip["currency"]) == (
        True, "Google Ads Editor export", ["account-structure"], None)
    done = json.loads(webapi.audit("account-structure", str(EDITOR)))
    assert done["ok"] and done["passed"]


def test_the_editor_sample_audits_like_the_snapshot_it_was_made_from():
    """examples/editor_acme.csv is the Acme snapshot as Editor writes it. It reads back to the same findings, except
    what an Editor file can't hold: shared negative lists, and whether Google limits a campaign by its budget."""
    examples = Path(__file__).resolve().parent.parent / "examples"
    snap = results(load_snapshot(examples / "account_structure_acme.json"))
    editor = results(load_editor(examples / "editor_acme.csv"))
    differ = {t for t in snap if snap[t] != editor[t]}
    assert differ == {"Negatives that block your own keywords", "Budget caps"}
    assert editor["Negatives that block your own keywords"] == ("found", "3 conflicts")
    assert editor["Budget caps"] == ("missing", "Not in this file (whether a campaign is limited by budget)")
    assert [c["budget"] for c in load_editor(examples / "editor_acme.csv")["campaigns"]][:2] == [120.0, 25.0]


@pytest.mark.parametrize("words, key", [
    ("Presence: People in or regularly in your targeted locations", "PRESENCE"),
    ("People in or regularly in your included locations", "PRESENCE"),
    ("Presence or interest: People in, regularly in, or who've shown interest in your targeted locations",
     "PRESENCE_OR_INTEREST"),
    ("People in, regularly in, or who've shown interest in your included locations", "PRESENCE_OR_INTEREST"),
    ("SEARCH_INTEREST", "SEARCH_INTEREST"),
    ("", None),
])
def test_location_options_in_any_wording(words, key):
    assert _geo(words) == key

import json
from pathlib import Path

from openppc import webapi
from openppc.ingest.account import enum, load_snapshot, snapshot
from openppc.ingest.editor import load_editor
from openppc.templates import run_template
from openppc.templates.account_structure import blocks, evaluate

SAMPLE = str(Path(__file__).resolve().parent.parent / "examples" / "account_structure_acme.json")


def results(data, **kw):
    checks, _, _ = evaluate(data, **kw)
    return {c.title: (c.status, c.summary) for c in checks}


def test_every_planted_problem_is_found():
    got = results(load_snapshot(SAMPLE), brand="Acme")
    assert got == {
        "Ads and keywords held back by policy": ("found", "1 disapproved, 1 limited"),
        "Broad match without Smart Bidding": ("found", "3 keywords in 2 campaigns"),
        "Brand and non-brand in one campaign": ("found", "1 campaign"),
        "Duplicate keywords": ("found", "1 keyword"),
        "Negatives that block your own keywords": ("found", "3 conflicts (shared lists not checked)"),
        "Headlines and descriptions": ("found", "3 of 7 ads"),
        "Ads per ad group": ("found", "3 ad groups"),
        "Pinning": ("found", "1 with a lone pin, 1 fully pinned"),
        "Single-keyword ad groups": ("found", "1 ad group"),
        "Keywords that rarely serve": ("found", "1 keyword (6.7%)"),
        "Quality Score parts below average": ("found", "2 keywords"),
        "Bidding for clicks, not conversions": ("found", "2 campaigns"),
        "Search campaigns on the Display Network": ("found", "1 campaign"),
        "Sitelinks, callouts and snippets": ("found", "2 campaigns"),
        "Budget caps": ("found", "1 campaign limited by budget"),
        "Location option": ("info", "Presence or interest 2, Presence 1 (see below)"),
    }


def test_budget_caps_show_what_a_limited_campaign_can_spend():
    markdown, _, passed = run_template("account-structure", SAMPLE, brand="Acme")
    assert passed and "| Acme \\| Search \\| Plumbing | $120.00 | $240.00 | $3,648.00 |" in markdown


def test_disapprovals_are_found_in_every_campaign_type():
    raw = {"campaigns": [{"id": "1", "name": "Acme | PMax", "status": "ENABLED", "channel": "PERFORMANCE_MAX"},
                         {"id": "2", "name": "Paused", "status": "PAUSED", "channel": "SEARCH"}],
           "ad_groups": [{"id": "11", "campaign_id": "1", "name": "Asset group 1", "status": "ENABLED"},
                         {"id": "21", "campaign_id": "2", "name": "Old", "status": "ENABLED"}],
           "ads": [{"ad_group_id": "11", "name": "Spring offer", "status": "ENABLED", "approval": "DISAPPROVED",
                    "policy": ["Unrealistic outcomes"]},
                   {"ad_group_id": "11", "name": "Video 2", "status": "ENABLED", "approval": "AREA_OF_INTEREST_ONLY"},
                   {"ad_group_id": "11", "name": "Fine", "status": "ENABLED", "approval": "APPROVED"},
                   {"ad_group_id": "21", "name": "Paused campaign", "status": "ENABLED", "approval": "DISAPPROVED"}]}
    got = results(snapshot(raw))
    assert got["Ads and keywords held back by policy"] == ("found", "1 disapproved, 1 limited")
    others = {v for t, v in got.items() if t != "Ads and keywords held back by policy"}
    assert others == {("missing", "No live Search campaigns")}


def test_a_disapproved_keyword_from_editor_is_enabled_but_held_back(tmp_path):
    path = tmp_path / "editor.csv"
    path.write_text("Campaign,Campaign Type,Campaign Status,Ad Group,Ad Group Status,Keyword,Criterion Type,Status,"
                    "Approval Status\n"
                    "Acme,Search,Enabled,Core,Enabled,plumber,Phrase,Disapproved,\n"
                    "Acme,Search,Enabled,Core,Enabled,drains,Phrase,Enabled,Approved\n", encoding="utf-8")
    kws = load_editor(path)["keywords"]
    assert [(k["status"], k["approval"]) for k in kws] == [("ENABLED", "DISAPPROVED"), ("ENABLED", "APPROVED")]
    assert results(load_editor(path))["Ads and keywords held back by policy"] == ("found", "1 disapproved, 0 limited")


def test_only_live_search_is_judged():
    # The sample also has a paused campaign, a paused ad group and a Performance Max campaign, all with problems.
    _, _, (camps, groups, kws, ads) = evaluate(load_snapshot(SAMPLE))
    assert (len(camps), len(groups), len(kws), len(ads)) == (3, 5, 15, 7)


def test_report_passes_its_own_number_check():
    # "40 gallon water heater" and "Water Heaters 2024" put digits inside names; they must read as names, not claims.
    markdown, _, passed = run_template("account-structure", SAMPLE, brand="Acme")
    assert passed and "40 gallon water heater" in markdown


def test_a_clean_account_finds_nothing():
    clean = snapshot({
        "campaigns": [{"id": "1", "name": "Search", "status": "ENABLED", "channel": "SEARCH",
                       "bidding": "MAXIMIZE_CONVERSIONS", "display_network": False, "geo_target_type": "PRESENCE"}],
        "ad_groups": [{"id": "11", "campaign_id": "1", "name": "Plumbing repair", "status": "ENABLED"}],
        "keywords": [{"ad_group_id": "11", "text": t, "match_type": "PHRASE", "status": "ENABLED"}
                     for t in ("plumbing repair", "pipe repair")],
        "negatives": [{"level": "CAMPAIGN", "owner_id": "1", "text": "jobs", "match_type": "BROAD"}],
        "ads": [{"ad_group_id": "11", "type": "RESPONSIVE_SEARCH_AD", "status": "ENABLED", "strength": "GOOD",
                 "headlines": [f"Headline {i}" for i in range(15)], "descriptions": ["a", "b", "c", "d"]}] * 2,
        "assets": [{"level": "ACCOUNT", "type": t, "status": "ENABLED"}
                   for t in ["SITELINK"] * 4 + ["CALLOUT"] * 4 + ["STRUCTURED_SNIPPET"]]})
    statuses = {title: status for title, (status, _) in results(clean, brand="Acme").items()}
    assert "found" not in statuses.values()
    # The file has no serving status or Quality Score parts: those checks say so rather than pass.
    assert statuses["Keywords that rarely serve"] == statuses["Quality Score parts below average"] == "missing"


def test_a_missing_section_is_never_a_pass(tmp_path):
    raw = {"campaigns": [{"id": "1", "name": "Search", "status": "ENABLED", "channel": "SEARCH"}]}
    assert {status for status, _ in results(snapshot(raw)).values()} <= {"missing", "needs brand"}
    path = tmp_path / "bare.json"
    path.write_text(json.dumps(raw))
    markdown, _, passed = run_template("account-structure", str(path))
    assert passed and "Not in this file" in markdown


def test_negative_match_types():
    assert blocks("drain cleaning", "EXACT", "drain cleaning")
    assert not blocks("drain cleaning", "EXACT", "drain cleaning near me")
    assert blocks("drain cleaning", "PHRASE", "cheap drain cleaning nj")
    assert not blocks("cleaning drain", "PHRASE", "drain cleaning")
    assert blocks("cleaning drain", "BROAD", "drain cleaning near me")
    assert blocks("repair", None, "water heater repair")  # unknown match type reads as broad, the widest
    assert blocks('"drain cleaning"', "PHRASE", "[drain cleaning]")  # match-type marks are not words


def test_editor_wording_normalizes():
    assert enum("Maximize clicks") == "TARGET_SPEND"
    assert enum("Low search volume") == "RARELY_SERVED"
    camp = snapshot({"campaigns": [{"id": 1, "status": "Enabled", "enhanced_cpc": "yes",
                                    "geo_target_type": "Presence or interest: People in, regularly in, or who've "
                                                       "shown interest in your targeted locations (recommended)"}]})
    c = camp["campaigns"][0]
    assert (c["id"], c["status"], c["enhanced_cpc"], c["geo_target_type"]) == ("1", "ENABLED", True, "PRESENCE_OR_INTEREST")


def test_the_web_app_recognizes_a_snapshot():
    info = json.loads(webapi.inspect_file(SAMPLE))
    assert (info["kind"], info["templates"]) == ("Account snapshot", ["account-structure"])

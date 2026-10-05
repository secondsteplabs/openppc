import json
from pathlib import Path

from openppc import webapi
from openppc.ingest.account import enum, load_snapshot, snapshot
from openppc.templates import run_template
from openppc.templates.account_structure import blocks, evaluate

SAMPLE = str(Path(__file__).resolve().parent.parent / "examples" / "account_structure_acme.json")


def results(data, **kw):
    checks, _, _ = evaluate(data, **kw)
    return {c.title: (c.status, c.summary) for c in checks}


def test_every_planted_problem_is_found():
    got = results(load_snapshot(SAMPLE), brand="Acme")
    assert got == {
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
        "Location option": ("info", "Presence or interest 2, Presence 1 (see below)"),
    }


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

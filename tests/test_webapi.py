"""The browser bridge returns the same answers as the CLI, and the web bundle is up to date."""
import importlib.util
import json
from pathlib import Path

from openppc import webapi

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"
SAMPLE_CSV = str(EX / "search_terms_acme.csv")


def _build_web():
    spec = importlib.util.spec_from_file_location("build_web", ROOT / "tools" / "build_web.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_web_bundle_is_fresh():
    built = _build_web().bundle()
    on_disk = (ROOT / "web" / "engine.js").read_text(encoding="utf-8")
    assert on_disk == built, "web/engine.js is stale: run python tools/build_web.py"


def test_meta_lists_templates_and_industries():
    m = json.loads(webapi.meta())
    assert {t["name"] for t in m["templates"]} == {"search-term-waste", "keyword-audit", "account-structure",
                                                  "account-read"}
    assert any(i["key"] == "home-services" for i in m["industries"])


def test_inspect_search_terms_export():
    info = json.loads(webapi.inspect_file(SAMPLE_CSV))
    assert info["ok"] and info["kind"] == "Search terms report" and info["rows"] == 18
    assert (info["start"], info["end"], info["currency"]) == ("2026-07-01", "2026-07-31", "USD")
    assert "search-term-waste" in info["templates"]


def test_inspect_rejects_a_file_that_is_not_an_export(tmp_path):
    bad = tmp_path / "notes.csv"
    bad.write_text("hello,world\n1,2\n", encoding="utf-8")
    info = json.loads(webapi.inspect_file(str(bad)))
    assert not info["ok"]
    assert info["name"] == "notes.csv" and str(tmp_path) not in info["error"]  # the chip shows the name itself


def test_check_matches_the_cli():
    text = (EX / "ai_audit_sample.md").read_text(encoding="utf-8")
    assert webapi.count_numbers(text) == 11
    res = json.loads(webapi.check(text, json.dumps([SAMPLE_CSV]), "home-services"))
    assert res["ok"]
    assert res["counts"] == {"total": 11, "traced": 6, "mismatch": 1, "not_in_data": 3, "cant_check": 1,
                             "contradictions": 1}  # "fell from 9%": an earlier figure no one-month export holds
    assert {c["written"] for c in res["claims"] if c["verdict"] != "traced"} == {"$4,200", "22", "9%", "14%", "62%"}
    assert res["contradictions"][0]["line"] == 11


def test_audit_passes_its_own_check():
    res = json.loads(webapi.audit("search-term-waste", SAMPLE_CSV, "home-services", 20))
    assert res["ok"] and res["passed"] and "$767.20" in res["markdown"]


def test_audit_refuses_a_file_the_template_cannot_read():
    res = json.loads(webapi.audit("account-read", SAMPLE_CSV))
    assert not res["ok"] and "search_terms_acme.csv" in res["error"]


def test_audit_hands_the_app_structured_results():
    res = json.loads(webapi.audit("search-term-waste", str(ROOT / "examples" / "search_terms_acme.csv"), "home-services"))
    cards = res["cards"]
    assert res["passed"] and [k["label"] for k in cards["kpis"]] == [
        "Wasted spend", "Share of total cost", "A year at this rate", "Cost per conversion", "CTR"]
    assert cards["kpis"][0]["value"] == "$767.20" and cards["kpis"][3]["note"] == "vs $90.92 industry"
    assert [a["kind"] for a in cards["actions"]] == ["watch", "review", "add"]
    first = cards["waste"][0]
    assert (first["term"], first["cost"], first["chance"], first["sure"]) == ("free plumbing estimate", "$312.00", "79%", False)
    # every action sentence is also in the report, so the number check covered it
    assert all(a["detail"] in res["markdown"] for a in cards["actions"])
    other = json.loads(webapi.audit("keyword-audit", str(ROOT / "examples" / "keywords_acme.csv")))
    assert other["cards"] == {}

"""Rule packs, suppressions, fingerprints, baselines and scores, and the JSON schemas the companion ships."""
import json
from pathlib import Path

import jsonschema
import pytest
from sites import acme, by_id, local, page

from openppc_online.siteaudit import checks, packs, tags, triage
from openppc_online.siteaudit.crawl import PROBE, crawl
from openppc_online.siteaudit.lab.lhr import read
from openppc_online.siteaudit.render import Observation, Rendered, Vitals
from openppc_online.siteaudit.report import Extras, report
from openppc_online.siteaudit.tags import VENDORS, vendor_of

COMPANION = Path(__file__).resolve().parent.parent
SCHEMAS = COMPANION / "openppc_online" / "schemas"
EXAMPLES = sorted((COMPANION / "examples" / "rulepacks").glob("*.json"))

PACK = {"openppc_site": 1, "name": "agency basics",
        "signatures": [{"id": "our-collector", "name": "Our collector", "kind": "analytics",
                        "hit": [{"host": "t.example.com"}], "source": ["ourCollector.init("]}],
        "rules": [{"id": "gtm-everywhere", "category": "tracking", "severity": "high", "effort": "low",
                   "title": "Pages without GTM-ABC123", "fix": "Add the container to all 3 templates.",
                   "require": {"field": "source", "contains": "GTM-ABC123"}},
                  {"id": "short-titles", "category": "seo", "severity": "low", "pages": "/item*",
                   "title": "Item titles over 5 characters", "fix": "Shorten them.",
                   "require": {"field": "title", "max_length": 5}},
                  {"id": "collector-installed", "category": "tracking", "severity": "medium",
                   "title": "Our collector isn't installed", "fix": "Install it.",
                   "require": {"tag": "our-collector"}}],
        "suppress": [{"rule": "site-broken-*", "match": "/broken", "reason": "Removed in sprint 12."},
                     {"rule": "site-never-fires", "reason": "Left over."}]}


def _pack(tmp_path, doc=PACK, name="pack.json"):
    path = tmp_path / name
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return str(path), path.read_text(encoding="utf-8")


@pytest.fixture
def own_signatures():
    """add_vendors is process-wide: put the tables back after a test that adds to them."""
    vendors, sources, hosts = dict(VENDORS), dict(tags._SOURCE), set(tags._HOSTS)
    yield
    VENDORS.clear()
    VENDORS.update(vendors)
    tags._SOURCE.clear()
    tags._SOURCE.update(sources)
    tags._HOSTS.clear()
    tags._HOSTS.update(hosts)


@pytest.mark.parametrize("change, message", [
    (lambda d: d["rules"][0].update(titel="x"), r"rules\[0\]: unknown key \"titel\""),
    (lambda d: d["rules"][0].update(id="site-mine"), r"kept for the built-in rules"),
    (lambda d: d["rules"][1]["require"].update(field="colour"), r"rules\[1\]\.require\.field: unknown field"),
    (lambda d: d["rules"][1]["require"].update(contains=5), r"wrong type"),
    (lambda d: d["rules"][1]["require"].update(max_length=True), r"wrong type"),
    (lambda d: d["rules"][2]["require"].update(tag="nope"), r"unknown tag \"nope\""),
    (lambda d: d["rules"][2].update(pages="/x"), r"whole site"),
    (lambda d: d["suppress"][0].pop("reason"), r"suppress\[0\]: missing \"reason\""),
    (lambda d: d["signatures"][0].update(id="ga4"), r"already a known tag"),
    (lambda d: d.update(openppc_site=2), r"reads version 1 files"),
])
def test_a_pack_mistake_names_the_place(change, message):
    doc = json.loads(json.dumps(PACK))
    change(doc)
    with pytest.raises(packs.PackError, match=message):
        packs.parse(json.dumps(doc), "pack.json", packs.Config())


def test_a_pack_that_isnt_json_says_where():
    with pytest.raises(packs.PackError, match=r"pack.json: line 3, column \d"):
        packs.parse('{"openppc_site": 1,\n "rules": []\n,}', "pack.json", packs.Config())


def test_rule_packs_add_findings_signatures_and_suppressions(serve, tmp_path, own_signatures):
    base = serve(acme)
    config = packs.load([_pack(tmp_path)])
    assert vendor_of("https://t.example.com/c?x=1") == ("our-collector", "hit")
    c = crawl(base, local(), fast=True, external=False)
    found = by_id(packs.evaluate(config, c, None))
    assert set(found) == {"gtm-everywhere", "short-titles", "collector-installed"}
    assert sorted(found["short-titles"].items) == sorted(f"{base}/item?id={i}" for i in range(10))  # 10: the cap
    assert found["short-titles"].notes[f"{base}/item?id=3"] == "`title` is `6` characters long"
    assert "run with `--render`" in found["collector-installed"].notes["Our collector"]
    findings, used = triage.suppress(checks.evaluate(c) + list(found.values()), config.suppress)
    assert "site-broken-internal" not in by_id(findings)
    assert used[0].items == [("site-broken-internal", base + "/broken")] and used[1].items == []
    markdown, _, passed = report(c, None, findings, Extras(config.files, used))
    assert passed, markdown
    assert "Removed in sprint 12." in markdown and "matched nothing, so it can go" in markdown
    assert "Pages without GTM-ABC123" in markdown and "effort low" in markdown


def test_a_pack_can_require_an_event_a_browser_pass_saw(serve, tmp_path):
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    c = crawl(base, local(), fast=True, external=False)
    hit = "https://region1.google-analytics.com/g/collect?v=2&en=page_view"
    r = Rendered(pages=[Observation(base + "/", before=[hit], events={"ga4": ["page_view", "step_2"]})])
    rule = {"id": "lead-sent", "category": "tracking", "severity": "high", "title": "No lead event", "fix": "Fix it.",
            "require": {"tag": "ga4", "event": "generate_lead"}}
    config = packs.load([_pack(tmp_path, {"openppc_site": 1, "rules": [rule]})])
    note = by_id(packs.evaluate(config, c, r))["lead-sent"].notes["Google Analytics 4"]
    assert note == "no `generate_lead` event on the rendered pages; it sent `page_view`, `step_2`"
    rule["require"]["event"] = "PAGE_VIEW"
    assert packs.evaluate(packs.load([_pack(tmp_path, {"openppc_site": 1, "rules": [rule]})]), c, r) == []
    rule["require"]["event"] = "x" * 101
    with pytest.raises(packs.PackError, match="longer than 100"):
        packs.load([_pack(tmp_path, {"openppc_site": 1, "rules": [rule]})])


BUDGET = {"id": "landing-speed", "severity": "high", "pages": "/lp/*",
          "max": {"lcp": 2500, "script-kb": 100}, "min": {"speed-score": 80}}


@pytest.mark.parametrize("change, message", [
    (lambda b: b["max"].update(inp=200), r"budgets\[0\]\.max\.inp: isn't a budget line here"),
    (lambda b: b["min"].update(lcp=1), r"budgets\[0\]\.min\.lcp: isn't a budget line here"),
    (lambda b: b["max"].update(lcp=-1), r"must be a number, 0 or more"),
    (lambda b: b["max"].update(lcp=True), r"must be a number, 0 or more"),
    (lambda b: b["min"].update({"speed-score": 101}), r"must be 0 to 100"),
    (lambda b: (b.pop("max"), b.pop("min")), r"needs a line in \"max\" or \"min\""),
    (lambda b: b.update(device="tablet"), r"budgets\[0\]\.device: must be one of mobile, desktop"),
    (lambda b: b.update(id="gtm-everywhere"), r"\"gtm-everywhere\" is defined twice"),
    (lambda b: b.update(id="site-speed"), r"kept for the built-in rules"),
    (lambda b: b.update(limit=1), r"budgets\[0\]: unknown key \"limit\""),
])
def test_a_budget_mistake_names_the_place(change, message):
    doc = json.loads(json.dumps(PACK))
    doc["budgets"] = [json.loads(json.dumps(BUDGET))]
    change(doc["budgets"][0])
    with pytest.raises(packs.PackError, match=message):
        packs.parse(json.dumps(doc), "pack.json", packs.Config())


def _site(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home")), "/lp/spring": (200, {}, page("Spring"))})
    return base, crawl(base, local(), fast=True, external=False)


def test_a_budget_checks_lighthouses_numbers_on_its_pages(serve, tmp_path):
    base, c = _site(serve)
    config = packs.load([_pack(tmp_path, {"openppc_site": 1, "budgets": [BUDGET]})])
    lhr = json.loads((COMPANION / "tests" / "fixtures" / "lhr-13.5-mobile.json").read_text(encoding="utf-8"))
    speed = [read(lhr, base + "/lp/spring", "Lighthouse"), read(lhr, base + "/", "Lighthouse")]
    found = by_id(packs.evaluate(config, c, None, speed))["landing-speed"]
    assert found.items == [base + "/lp/spring"]  # the home page is outside /lp/*
    assert found.notes[base + "/lp/spring"] == ("`lcp` is `10885 ms`, over `2500 ms`; `script-kb` is `164 KB`, over "
                                                "`100 KB`; `speed-score` is `32`, under `80` (Lighthouse, mobile)")
    markdown, _, passed = report(c, None, [found], Extras(config.files, speed=speed))
    assert passed, markdown
    assert "Pages over the landing-speed budget" in markdown
    roomy = dict(BUDGET, max={"lcp": 20000}, min={})
    assert packs.evaluate(packs.load([_pack(tmp_path, {"openppc_site": 1, "budgets": [roomy]})]), c, None, speed) == []
    desktop = dict(BUDGET, device="desktop")
    found = packs.evaluate(packs.load([_pack(tmp_path, {"openppc_site": 1, "budgets": [desktop]})]), c, None, speed)
    assert [(f.title, f.severity) for f in found] == [("Budget `landing-speed` wasn't checked", "info")]


def test_a_budget_falls_back_to_the_lab_timings_and_says_when_nothing_was_measured(serve, tmp_path):
    base, c = _site(serve)
    config = packs.load([_pack(tmp_path, {"openppc_site": 1, "budgets": [BUDGET]})])
    lab = Vitals(base + "/lp/spring", runs=[{"lcp": 3120.4, "fcp": 900.0, "tbt": 0.0, "cls": 0.0, "ttfb": 80.0,
                                            "si": 1000.0}])
    found = by_id(packs.evaluate(config, c, Rendered(vitals=[lab])))["landing-speed"]
    assert found.notes == {base + "/lp/spring": "`lcp` is `3120 ms`, over `2500 ms` (OpenPPC lab, mobile)"}
    sizes_only = dict(BUDGET, max={"script-kb": 100})
    found = packs.evaluate(packs.load([_pack(tmp_path, {"openppc_site": 1, "budgets": [sizes_only]})]), c,
                           Rendered(vitals=[lab]))
    assert [f.severity for f in found] == ["info"]
    assert "sizes and the speed score `--psi` or `--lighthouse`" in found[0].notes["landing-speed"]
    found = packs.evaluate(config, c, None)
    assert [(f.id, f.items, f.severity) for f in found] == [("landing-speed", ["landing-speed"], "info")]


def test_fingerprints_ignore_the_origin_and_secrets_are_masked():
    assert triage.fingerprint("site-noindex", "https://staging.a.test/x?id=1") == \
        triage.fingerprint("site-noindex", "https://www.a.test/x?id=1")
    assert triage.fingerprint("site-noindex", "/x") != triage.fingerprint("site-title-missing", "/x")
    assert triage.item_key("https://a.test/openppc-missing-page-1a2b3c") == triage.item_key("https://a.test" + PROBE)
    assert triage.redact("https://a.test/p?id=3&access_token=abc&Email=a@b.c#top") == \
        "https://a.test/p?id=3&access_token=REDACTED&Email=REDACTED#top"
    assert triage.redact_text("see `https://a.test/?session=1` and https://a.test/") == \
        ("see `https://a.test/?session=REDACTED` and https://a.test/", 1)


def test_a_baseline_says_what_is_new_and_what_was_fixed(tmp_path):
    old = {"findings": [{"id": "site-noindex", "title": "Noindex", "items": ["https://staging.a.test/x"]},
                        {"id": "site-title-missing", "title": "No title", "items": ["https://a.test/gone"]}]}
    path = tmp_path / "old.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    now = [checks.Finding("site-noindex", ["https://www.a.test/x", "https://www.a.test/y"])]
    diff = triage.compare(now, triage.read_baseline("old.json", json.dumps(old)), "old.json")
    assert diff.new == {"site-noindex": ["https://www.a.test/y"]} and diff.unchanged == 1
    assert diff.fixed == [("No title", "https://a.test/gone")]
    with pytest.raises(ValueError, match="old.json isn't an `openppc-online site --format json` result"):
        triage.read_baseline("old.json", "{}")


def test_scores_lose_points_by_severity():
    f = [checks.Finding("site-title-missing", ["/a"]), checks.Finding("site-noindex", ["/b"]),
         checks.Finding("site-broken-internal", ["/c"]), checks.Finding("site-a11y", ["/d"], severity="high")]
    s = triage.scores(f, rendered=False)
    assert s["seo"].score == 100 - triage.SCORE_MEDIUM and s["seo"].grade == "A"
    assert s["links"].score == 100 - triage.SCORE_HIGH and s["links"].grade == "B"
    assert s["accessibility"].score is None and s["accessibility"].why_not == "needs `--render`"
    assert "crawl" not in s
    assert triage.scores(f, rendered=True)["accessibility"].score == 100 - triage.SCORE_HIGH


def test_an_axe_finding_an_seo_rule_already_counts_costs_nothing():
    seo = checks.Finding("site-img-alt-missing", ["/a"])
    axe = checks.Finding("site-a11y", ["/a"], key="site-a11y:image-alt")
    other = checks.Finding("site-a11y", ["/a"], key="site-a11y:color-contrast")
    s = triage.scores([seo, axe, other], rendered=True)
    assert s["seo"].score == 100 - triage.SCORE_MEDIUM
    assert s["accessibility"].score == 100 - triage.points(other.level)


def test_the_schemas_are_valid_and_ship_inside_the_package():
    assert {p.name for p in SCHEMAS.glob("*.json")} == {"site-config.schema.json", "site-report.schema.json"}
    for p in SCHEMAS.glob("*.json"):
        jsonschema.Draft202012Validator.check_schema(json.loads(p.read_text(encoding="utf-8")))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_the_example_rule_packs_match_the_schema_and_load(path, own_signatures):
    jsonschema.validate(json.loads(path.read_text(encoding="utf-8")),
                        json.loads((SCHEMAS / "site-config.schema.json").read_text(encoding="utf-8")))
    assert packs.load([(path.name, path.read_text(encoding="utf-8"))]).files == [path.name]

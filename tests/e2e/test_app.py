"""What a visitor does on the web app, in Chromium: every route, the sample check and audit, each template on its
example export, the branded PDF, Stop on a big export, accessibility, and the phone layout.

These pin the app as it is (0.1.11). When a change to the app breaks one, the test or the app is wrong; decide which.
"""
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import BOOT, READY, ROOT

from openppc.templates import TEMPLATES

expect = pytest.importorskip("playwright.sync_api", reason='needs pip install -e ".[e2e]"').expect
pytestmark = pytest.mark.e2e

RUN = 120_000  # ms: one audit or check in the browser, generous for slow CI machines
EXAMPLES = ROOT / "examples"
AXE = "https://cdn.jsdelivr.net/npm/axe-core@4.10.3/axe.min.js"
# Serious or critical axe rules the app is allowed to break. Empty since 0.1.11, when the two grey text tokens were
# darkened to reach 4.5:1; add a rule here only with a reason.
KNOWN_AXE: set[str] = set()

WASTED = ["free plumbing estimate", "plumber jobs hiring", "how to unclog a drain yourself", "plumbing franchise cost",
          "plumbing supply store", "plumber reviews"]


def _hash(page, route):
    page.evaluate("(r) => { location.hash = r; }", route)


def _flagged(page):
    return {kind: page.locator(f".card.msg .items .pills .pill.{kind}").count() for kind in ("p-nid", "p-mis", "p-con")}


@pytest.mark.parametrize("route, mode, crumb, section", [
    ("#home", "OpenPPC", "Home", "#home"),
    ("#check", "Check an AI audit", "New check", "#compose"),
    ("#audit", "Audit my account", "New audit", "#compose"),
    ("#templates", "OpenPPC", "Templates", "#gallery"),
    ("#rules", "OpenPPC", "Rules", "#rules"),
    ("#branded", "OpenPPC", "Branded PDF", "#branded"),
    ("#no-such-page", "OpenPPC", "Home", "#home"),
])
def test_every_route_shows_its_page(app, route, mode, crumb, section):
    _hash(app, route)
    expect(app.locator("#crumb-mode")).to_have_text(mode)
    expect(app.locator("#crumb-page")).to_have_text(crumb)
    expect(app.locator(section)).to_be_visible()


def test_branded_pdf_asks_for_an_audit_first(app):
    _hash(app, "#branded")
    expect(app.locator("#branded-main")).to_contain_text("Run an audit first")


def test_the_sample_check_flags_the_same_numbers_precomputed_and_live(app):
    _hash(app, "#check")
    app.locator("#sample-btn").click()
    expect(app.locator("#run-btn")).to_be_enabled(timeout=RUN)
    app.locator("#run-btn").click()
    expect(app.get_by_text("Number check · the sample, checked in advance")).to_be_visible(timeout=RUN)
    expected = {"p-nid": 3, "p-mis": 1, "p-con": 1}
    assert _flagged(app) == expected
    lead = app.locator(".card.msg .lead")
    for wrong in ("$4,200",):
        expect(lead).to_contain_text(wrong)
    expect(lead).to_contain_text("can't be checked from an export")

    with app.expect_download() as dl:
        app.get_by_role("button", name="Download .md").click()
    assert dl.value.suggested_filename == "openppc-number-check.md"
    app.get_by_role("button", name="Copy fix list").click()
    fixes = app.evaluate("navigator.clipboard.readText()")
    for wrong in ("$4,200", "14%", "62%"):
        assert f'"{wrong}"' in fixes

    # any edit means the precomputed answer no longer applies: the engine checks it, with the same verdicts
    app.get_by_role("button", name="Edit the audit and check again").click()
    text = app.locator("#audit-text")
    text.fill(text.input_value() + "\n")
    expect(app.locator("#run-btn")).to_be_enabled(timeout=RUN)
    app.locator("#run-btn").click()
    expect(app.locator(".who").filter(has_text="on this device")).to_be_visible(timeout=RUN)
    assert _flagged(app) == expected


def test_the_sample_audit_exports_negatives_and_makes_the_branded_pdf(app, tmp_path):
    _hash(app, "#home")
    app.locator("#home-sample").click()
    expect(app.locator(".badge-ok")).to_have_text("Every number traced to your file", timeout=RUN)
    expect(app.locator("h2.rep-title")).to_have_text(TEMPLATES["search-term-waste"].TITLE)
    expect(app.get_by_text("Every number in this report traces back to your data.", exact=True)).to_be_visible()
    expect(app.locator(".kpi b").first).to_have_text("$767.20")

    with app.expect_download() as dl:
        app.get_by_role("button", name="Download .md").click()
    assert dl.value.suggested_filename == "openppc-search-term-waste.md"

    app.get_by_role("checkbox", name="Select every search term").check()
    expect(app.get_by_text("6 terms selected")).to_be_visible()
    app.get_by_role("button", name="Copy as negatives").click()
    expect(app.locator(".toast")).to_contain_text("6 negatives copied")
    assert app.evaluate("navigator.clipboard.readText()").splitlines() == [f"[{t}]" for t in WASTED]

    with app.expect_download() as dl:
        app.get_by_role("button", name="Download .csv").click()
    assert dl.value.suggested_filename == "openppc-negatives.csv"
    saved = tmp_path / "negatives.csv"
    dl.value.save_as(saved)
    lines = saved.read_bytes().decode("utf-8").split("\r\n")
    assert lines[0] == "Campaign,Negative keyword,Match type,Cost,Clicks,Chance it's bad"
    assert [line.split(",")[1] for line in lines[1:-1]] == WASTED
    assert lines[-1] == ""

    app.get_by_role("link", name="Make the branded PDF").click()
    status = app.locator(".pdf-status.ok")
    expect(status).to_contain_text("all traced to search_terms_acme.csv", timeout=RUN)
    expect(app.get_by_role("button", name="Save as PDF")).to_be_enabled()


@pytest.mark.parametrize("name, export", [
    ("search-term-waste", "search_terms_acme.csv"),
    ("keyword-audit", "keywords_acme.csv"),
    ("account-structure", "account_structure_acme.json"),
    ("account-read", "account_acme.json"),
])
def test_each_template_runs_on_its_example_in_the_browser(app, name, export):
    app.locator("#file-input").set_input_files(str(EXAMPLES / export))
    expect(app.locator(".file-name")).to_have_text(export, timeout=RUN)
    title = TEMPLATES[name].TITLE
    expect(app.locator('#templates [role="radio"][aria-checked="true"]')).to_contain_text(title)
    expect(app.locator("#run-btn")).to_be_enabled(timeout=RUN)
    app.locator("#run-btn").click()
    expect(app.locator(".badge-ok")).to_be_visible(timeout=RUN)
    expect(app.locator("h2.rep-title")).to_have_text(title)
    expect(app.locator(".who").filter(has_text="on this device")).to_be_visible()


def test_a_file_it_cannot_read_offers_a_report_with_only_its_column_names(app, tmp_path):
    export = tmp_path / "birch_lane_terms.csv"
    export.write_bytes((ROOT / "tests" / "fixtures" / "search_terms_german_headers.csv").read_bytes())
    app.locator("#file-input").set_input_files(str(export))
    report = app.locator(".report-file")
    expect(report).to_be_visible(timeout=RUN)
    report.locator("summary").click()
    preview = report.locator(".report-preview").inner_text()
    columns = "Suchbegriff Keyword-Option Kampagne Anzeigengruppe Klicks Impr. Kosten Conversions".split()
    assert "\n".join(columns) in preview
    link = parse_qs(urlsplit(report.get_by_role("link", name="Open the issue on GitHub").get_attribute("href")).query)
    assert link["template"] == ["file_not_read.yml"]
    assert link["columns"] == ["\n".join(columns)]
    sent = preview + " ".join(v[0] for v in link.values())
    for private in ("birch_lane", "notdienst", "Birch Lane", "Juli", "1.254,40", "Suchbegriffbericht"):
        assert private not in sent
    assert _axe(app) <= KNOWN_AXE


def _big_export(path: Path, rows: int):
    head = ("Search terms report\nJuly 1, 2026 - July 31, 2026\n"
            "Search term,Match type,Added/Excluded,Campaign,Ad group,Clicks,Impr.,CTR,Currency code,Avg. CPC,Cost,"
            "Conv. rate,Conversions,Cost / conv.\n")
    body = []
    for i in range(rows):
        clicks = 1 + i % 17
        conversions = 1 if i % 9 == 0 else 0
        cost = clicks * 2.5
        body.append(f"term number {i},Broad match,None,Search {i % 4},Group {i % 30},{clicks},{clicks * 12},8.33%,USD,"
                    f"2.50,{cost:.2f},{conversions / clicks:.2%},{conversions}.00,{cost / conversions if conversions else 0:.2f}")
    path.write_text(head + "\n".join(body) + "\n", encoding="utf-8")


def test_stop_restarts_the_checker_and_the_next_run_works(app, tmp_path):
    export = tmp_path / "big_search_terms.csv"
    _big_export(export, 100_000)
    app.locator("#file-input").set_input_files(str(export))
    expect(app.locator("#run-btn")).to_be_enabled(timeout=RUN)
    app.locator("#run-btn").click()
    expect(app.locator("#run-btn")).to_contain_text("Auditing 100,000 rows")
    app.locator("#stop-btn").click()
    expect(app.locator(".toast")).to_contain_text("Stopped.")
    expect(app.locator("#engine-status")).to_have_text(READY, timeout=BOOT)
    expect(app.locator("#run-btn")).to_be_enabled()
    app.locator("#run-btn").click()
    expect(app.locator(".badge-ok")).to_be_visible(timeout=RUN)


def _axe(page):
    page.add_script_tag(url=AXE)
    found = page.evaluate("""async () => {
        const r = await axe.run(document, { resultTypes: ['violations'] });
        return r.violations.filter((v) => ['serious', 'critical'].includes(v.impact)).map((v) => v.id);
    }""")
    return set(found)


@pytest.mark.parametrize("route", ["#home", "#check", "#audit", "#templates", "#rules", "#branded"])
def test_no_new_serious_accessibility_findings_on_desktop(app, route):
    _hash(app, route)
    assert _axe(app) <= KNOWN_AXE


def test_no_new_serious_accessibility_findings_on_a_phone_after_an_audit(phone):
    phone.locator("#home-sample").click()
    expect(phone.locator(".badge-ok")).to_be_visible(timeout=RUN)
    assert _axe(phone) <= KNOWN_AXE


def test_nothing_scrolls_sideways_on_a_phone(phone):
    for route in ("#home", "#check", "#audit", "#templates", "#rules", "#branded"):
        _hash(phone, route)
        wide = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert wide <= 0, f"{route} is {wide}px wider than the screen"
    _hash(phone, "#home")
    phone.locator("#home-sample").click()
    expect(phone.locator(".badge-ok")).to_be_visible(timeout=RUN)
    assert phone.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0

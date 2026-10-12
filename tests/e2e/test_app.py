"""What a visitor does on the web app, in Chromium: every route, the sample check and audit, each template on its
example export, the branded PDF, Stop on a big export, accessibility, and the phone layout.

These pin the app as it is (0.1.11). When a change to the app breaks one, the test or the app is wrong; decide which.
"""
import json
import re
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
# axe rules the app is allowed to break, at any impact. Empty since 0.1.13 (serious and critical ones since 0.1.11);
# add a rule here only with a reason.
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
    # the sample was audited in advance: its .html and .json wait for the checker, which the branded PDF then reuses
    with app.expect_download(timeout=RUN) as dl:
        app.get_by_role("button", name=".html", exact=True).click()
    assert dl.value.suggested_filename == "openppc-search-term-waste.html"
    page = Path(dl.value.path()).read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>") and "$767.20" in page and "<script" not in page
    with app.expect_download(timeout=RUN) as dl:
        app.get_by_role("button", name=".json", exact=True).click()
    report = json.loads(Path(dl.value.path()).read_text(encoding="utf-8"))
    assert (report["format_version"], report["template"], report["passed"]) == (1, "search-term-waste", True)

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
    ("account-structure", "editor_acme.csv"),
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


def test_two_exports_of_one_report_pick_account_read_and_make_the_branded_pdf(app):
    app.locator("#file-input").set_input_files([str(EXAMPLES / "search_terms_acme_june.csv"),
                                                str(EXAMPLES / "search_terms_acme.csv")])
    expect(app.locator(".file-name")).to_have_count(2, timeout=RUN)
    chosen = app.locator('#templates [role="radio"][aria-checked="true"]')
    expect(chosen).to_contain_text(TEMPLATES["account-read"].TITLE, timeout=RUN)
    expect(chosen).to_contain_text("Matches your files")
    expect(app.locator("#run-btn")).to_be_enabled()
    app.locator("#run-btn").click()
    expect(app.locator(".badge-ok")).to_be_visible(timeout=RUN)
    expect(app.locator(".report")).to_contain_text(
        "search_terms_acme.csv (current) and search_terms_acme_june.csv (prior)")
    with app.expect_download(timeout=RUN) as dl:
        app.get_by_role("button", name=".json", exact=True).click()
    assert dl.value.suggested_filename == "openppc-account-read.json"
    report = json.loads(Path(dl.value.path()).read_text(encoding="utf-8"))
    assert report["template"] == "account-read" and report["passed"]
    assert "search_terms_acme_june.csv" in report["markdown"]

    app.get_by_role("link", name="Make the branded PDF").click()
    expect(app.locator(".pdf-status.ok")).to_contain_text(
        "all traced to search_terms_acme.csv and search_terms_acme_june.csv", timeout=RUN)
    expect(app.locator("#pdf-pages")).to_contain_text("Fingerprint of search_terms_acme_june.csv")


def test_two_exports_that_do_not_pair_say_why_under_run(app):
    app.locator("#file-input").set_input_files([str(EXAMPLES / "search_terms_acme.csv"),
                                                str(EXAMPLES / "keywords_acme.csv")])
    expect(app.locator(".file-name")).to_have_count(2, timeout=RUN)
    option = app.locator('#templates [data-name="account-read"]')
    expect(option).to_contain_text("Your last two exports can't be compared", timeout=RUN)
    expect(app.locator("#run-btn")).to_be_enabled()  # the newest file's own template stays picked
    option.click()
    expect(app.locator("#run-btn")).to_be_disabled()
    expect(app.locator("#run-hint")).to_have_text(
        re.compile(r"\.csv are different reports\. Compare two exports of the same report\.$"))


def test_a_greyed_out_run_button_says_why(app):
    expect(app.locator("#run-btn")).to_be_disabled()
    expect(app.locator("#run-hint")).to_have_text("Add an export to audit.")
    _hash(app, "#check")
    app.locator("#file-input").set_input_files(str(EXAMPLES / "search_terms_acme.csv"))
    expect(app.locator("#run-hint")).to_have_text("Paste the audit to check.", timeout=RUN)
    app.locator("#audit-text").fill("The account is fine.")
    expect(app.locator("#run-hint")).to_have_text("There are no numbers in the audit to check.")
    app.locator("#audit-text").fill("Cost was $4,973.64.")
    expect(app.locator("#run-btn")).to_be_enabled()
    expect(app.locator("#run-hint")).to_be_empty()


def test_the_engine_is_downloaded_once(browser, site):
    ctx = browser.new_context()
    fetched = []
    ctx.on("request", lambda r: fetched.append(r.url.split("?")[0].rsplit("/", 1)[-1]))
    page = ctx.new_page()
    page.goto(site + "#audit")
    expect(page.locator("#engine-status")).to_have_text(READY, timeout=BOOT)
    ctx.close()
    assert "pyodide.mjs" in fetched  # the worker's own requests are seen too
    assert fetched.count("engine.js") == 1


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
    expect(app.locator("#run-hint")).to_have_text("Running the audit…")
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
        return r.violations.map((v) => v.id);
    }""")
    return set(found)


@pytest.mark.parametrize("route", ["#home", "#check", "#audit", "#templates", "#rules", "#branded"])
def test_no_new_accessibility_findings_on_desktop(app, route):
    _hash(app, route)
    assert _axe(app) <= KNOWN_AXE


def _results_and_pdf(page):
    """The check's results, the audit's results and the branded PDF made from it, each scanned by axe."""
    _hash(page, "#check")
    page.locator("#sample-btn").click()
    expect(page.locator("#run-btn")).to_be_enabled(timeout=RUN)
    page.locator("#run-btn").click()
    expect(page.locator("#all")).to_be_visible(timeout=RUN)
    found = _axe(page)
    _hash(page, "#home")
    page.locator("#home-sample").click()
    expect(page.locator(".badge-ok")).to_be_visible(timeout=RUN)
    found |= _axe(page)
    _hash(page, "#branded")
    expect(page.locator(".pdf-status.ok")).to_be_visible(timeout=RUN)
    return found | _axe(page)


def test_no_new_accessibility_findings_on_results_and_the_pdf_on_desktop(app):
    assert _results_and_pdf(app) <= KNOWN_AXE


def test_no_new_accessibility_findings_on_results_and_the_pdf_on_a_phone(phone):
    assert _results_and_pdf(phone) <= KNOWN_AXE


def test_the_keyboard_reaches_everything(app):
    app.keyboard.press("Tab")
    expect(app.locator("#skip-link")).to_be_focused()
    app.keyboard.press("Enter")
    expect(app.locator("#main")).to_be_focused()
    assert app.evaluate("location.hash") == "#audit"  # skipping is not a page change
    app.locator("#file-input").focus()
    assert app.evaluate("getComputedStyle(document.getElementById('drop')).outlineStyle") == "solid"

    assert app.locator('.tpl[tabindex="0"]').count() == 1  # the radio group is one tab stop
    app.locator('.tpl[tabindex="0"]').focus()
    app.keyboard.press("ArrowDown")
    checked = app.locator('.tpl[aria-checked="true"]')
    expect(checked).to_contain_text(TEMPLATES["keyword-audit"].TITLE)
    expect(checked).to_be_focused()
    expect(checked).to_have_attribute("tabindex", "0")
    app.keyboard.press("ArrowUp")
    expect(app.locator('.tpl[aria-checked="true"]')).to_contain_text(TEMPLATES["search-term-waste"].TITLE)


def test_each_page_has_its_own_title_and_an_unknown_one_goes_home(app):
    assert app.title() == "Audit my export · OpenPPC"
    _hash(app, "#templates")
    expect(app).to_have_title("Templates · OpenPPC")
    _hash(app, "#nope")
    expect(app).to_have_title("OpenPPC: check every number in your Google Ads audit")
    assert app.evaluate("location.hash") == "#home"


def test_copy_works_without_the_clipboard_api_and_messages_stay_in_one_live_region(app):
    _hash(app, "#home")
    app.locator("#home-sample").click()
    expect(app.locator(".badge-ok")).to_be_visible(timeout=RUN)
    app.evaluate("() => { navigator.clipboard.writeText = () => Promise.reject(new Error('plain HTTP')); }")
    app.get_by_role("button", name="Copy", exact=True).click()
    expect(app.locator("#toasts .toast")).to_have_text("Report copied as markdown")
    assert app.evaluate("navigator.clipboard.readText()").startswith("# Search-term waste audit")
    app.get_by_role("button", name="Copy as negatives").click()  # nothing ticked: a message, not a copy
    expect(app.locator(".toast")).to_have_count(1)
    expect(app.locator("#toasts")).to_have_attribute("aria-live", "polite")


def test_nothing_scrolls_sideways_on_a_phone(phone):
    for route in ("#home", "#check", "#audit", "#templates", "#rules", "#branded"):
        _hash(phone, route)
        wide = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert wide <= 0, f"{route} is {wide}px wider than the screen"
    _hash(phone, "#home")
    phone.locator("#home-sample").click()
    expect(phone.locator(".badge-ok")).to_be_visible(timeout=RUN)
    assert phone.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0

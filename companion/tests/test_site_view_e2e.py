"""The Site view in Chromium: it audits a site served on 127.0.0.1, downloads the report, stops a run, steps
aside for the rest of the app, and fits a phone."""
import pytest
from sites import PSI_HOST, acme, page
from test_lab_lhr import LHR, psi_answer

from openppc_online.siteaudit.lab import psi

sync_api = pytest.importorskip("playwright.sync_api", reason='needs pip install -e "companion[e2e]"')
pytestmark = pytest.mark.e2e

WAIT = 60_000  # ms


def _audit(page, base):
    page.get_by_label("The site").fill(base)
    page.get_by_label("Your agency").fill("Acme Agency\u0007")   # the control character is dropped
    page.get_by_text("Allow private addresses").click()
    page.get_by_text("Check links to other sites").click()
    page.get_by_text("Fast", exact=True).click()
    page.get_by_role("button", name="Audit the site").click()


def test_the_site_view_audits_downloads_stops_and_steps_aside(server, serve, tmp_path):
    base = serve(acme)
    blocked = []
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(accept_downloads=True)
        page.on("console", lambda m: blocked.append(m.text) if "Content Security Policy" in m.text else None)
        page.on("pageerror", lambda e: blocked.append(str(e)))
        page.goto(f"http://127.0.0.1:{server.port}/#check")
        site = page.locator(".rail [data-local-view='site']")
        site.click(timeout=WAIT)  # the page's scripts come from cdn.jsdelivr.net first
        assert blocked == []
        sync_api.expect(page.locator("#site")).to_be_visible()
        sync_api.expect(page.locator("#compose")).to_be_hidden()
        sync_api.expect(page.locator("#crumb-page")).to_have_text("Site audit")

        _audit(page, base)
        sync_api.expect(page.locator("#site .rep-title")).to_have_text("Site audit", timeout=WAIT)
        sync_api.expect(page.locator("#site .badge-ok")).to_be_visible()
        sync_api.expect(page.locator("#site .report")).to_contain_text("Broken internal links")
        assert "null" not in page.locator("#site .col:not([hidden])").evaluate(
            "n => [...n.childNodes].filter(c => c.nodeType === 3).map(c => c.textContent).join('')")
        with page.expect_download() as got:
            page.get_by_role("button", name="Download .md").click()
        saved = tmp_path / "site.md"
        got.value.save_as(saved)
        assert got.value.suggested_filename == "openppc-site-127.0.0.1_" + base.rsplit(":", 1)[1] + ".md"
        assert saved.read_text(encoding="utf-8").startswith("# Site audit")

        summary = page.locator("#site .site-summary")
        sync_api.expect(summary).to_contain_text("Landing page check: 127.0.0.1")
        sync_api.expect(summary).to_contain_text("prepared by Acme Agency")
        answers = summary.locator(".site-answer")
        sync_api.expect(answers).to_have_count(4)
        sync_api.expect(answers.filter(has_text="Loads fast on phones")).to_contain_text("Not checked")
        sync_api.expect(answers.filter(has_text="Ad click IDs survive redirects")).to_contain_text("Pass")
        sync_api.expect(summary.locator(".site-fixes li")).to_have_count(3)
        sync_api.expect(summary.locator(".site-gauge", has_text="Links")).to_have_count(1)
        sync_api.expect(summary.locator(".site-gauge", has_text="Performance")).to_have_count(0)  # no PSI: no gauge
        sync_api.expect(summary.locator(".site-next")).to_contain_text("Check with PageSpeed")
        summary.get_by_role("button", name="Re-check").click()   # this result becomes the baseline
        sync_api.expect(page.locator("#site .report")).to_contain_text("Compared with the baseline", timeout=WAIT)

        page.get_by_role("button", name="Audit another site").click()
        sync_api.expect(page.get_by_label("The site")).to_have_value(base)  # the form keeps what was set
        page.get_by_text("Fast", exact=True).click()  # off: polite, so there is time to stop it
        page.get_by_role("button", name="Audit the site").click()
        sync_api.expect(page.locator("#site .status")).to_contain_text("pages", timeout=WAIT)
        page.get_by_role("button", name="Stop").click()
        sync_api.expect(page.locator("#site .report")).to_contain_text("stopped with the Stop button", timeout=WAIT)

        page.locator(".rail [data-mode='check']").click()  # the hash is already #check: no hashchange
        sync_api.expect(page.locator("#compose")).to_be_visible()
        sync_api.expect(page.locator("#site")).to_be_hidden()
        site.click()
        sync_api.expect(page.locator("#site .rep-title")).to_be_visible()  # the result waits there
        page.locator(".rail-logo").click()
        sync_api.expect(page.locator("#home")).to_be_visible()

        page.set_viewport_size({"width": 360, "height": 780})
        assert page.evaluate("document.querySelector('.rail').scrollWidth <= window.innerWidth")
        browser.close()
    assert blocked == []


def test_the_quick_check_with_pagespeed_shows_its_score_on_the_summary(server, serve, public, monkeypatch):
    site = serve(lambda b: {"/": (200, {}, page("Home"))})
    api = serve(lambda b: {"/psi": psi_answer()})
    monkeypatch.setattr(psi, "ENDPOINT", api.replace("127.0.0.1", PSI_HOST) + "/psi")
    score = round(LHR["categories"]["performance"]["score"] * 100)
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page_ = browser.new_page()
        page_.goto(f"http://127.0.0.1:{server.port}/#check")
        page_.locator(".rail [data-local-view='site']").click(timeout=WAIT)
        page_.get_by_label("The site").fill(site.replace("127.0.0.1", "shop.test"))
        page_.get_by_role("button", name="Check with Google PageSpeed").click()
        summary = page_.locator("#site .site-summary")
        sync_api.expect(summary).to_be_visible(timeout=WAIT)
        fast = summary.locator(".site-answer", has_text="Loads fast on phones")
        sync_api.expect(fast).to_contain_text(f"Speed score {score} of 100 on a phone")
        sync_api.expect(summary.locator(".site-gauge", has_text="Performance")).to_contain_text(str(score))
        sync_api.expect(summary.locator(".site-visitors")).to_contain_text("Core Web Vitals failed")
        sync_api.expect(summary.locator(".site-measures")).to_contain_text("Speed Index")
        summary.get_by_role("button", name="Desktop").click()
        sync_api.expect(summary.locator(".site-measures")).to_contain_text("Largest Contentful Paint")
        page_.get_by_role("button", name="Audit another site").click()   # the choice was for that run only
        sync_api.expect(page_.locator("label.site-check", has_text="Measure with PageSpeed Insights").locator("input")) \
            .not_to_be_checked()
        browser.close()

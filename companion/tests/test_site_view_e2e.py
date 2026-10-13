"""The Site view in Chromium: it audits a site served on 127.0.0.1, downloads the report, stops a run, steps
aside for the rest of the app, and fits a phone."""
import pytest
from sites import acme

sync_api = pytest.importorskip("playwright.sync_api", reason='needs pip install -e "companion[e2e]"')
pytestmark = pytest.mark.e2e

WAIT = 60_000  # ms


def _audit(page, base):
    page.get_by_label("The site").fill(base)
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

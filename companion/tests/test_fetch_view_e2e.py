"""The Download view in Chromium: it downloads an account from a fake Google Ads, saves a file, hands the files to the
audit in the same tab, takes turns with the Site view, and fits a phone."""
import pytest
from test_fetch_command import ACCOUNTS, ENVS
from test_fetch_google import FakeGoogle

from openppc_online.fetch import command, http

sync_api = pytest.importorskip("playwright.sync_api", reason='needs pip install -e "companion[e2e]"')
pytestmark = pytest.mark.e2e

WAIT = 60_000  # ms
LABELS = {"GOOGLE_ADS_DEVELOPER_TOKEN": "Developer token", "GOOGLE_ADS_CLIENT_ID": "OAuth client ID",
          "GOOGLE_ADS_CLIENT_SECRET": "OAuth client secret", "GOOGLE_ADS_REFRESH_TOKEN": "Refresh token",
          "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "Manager account ID"}


def _shown(page):
    return page.evaluate("[...document.querySelectorAll('.main > .view')].filter(n => !n.hidden).map(n => n.id)")


def test_the_download_view_downloads_saves_audits_and_steps_aside(server, monkeypatch, tmp_path):
    monkeypatch.setattr(command, "Gate", lambda p, send=None: http.Gate(p, FakeGoogle()))
    for name in ENVS["google"]:
        monkeypatch.delenv(name, raising=False)
    blocked = []
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(accept_downloads=True)
        page.on("console", lambda m: blocked.append(m.text) if "Content Security Policy" in m.text else None)
        page.on("pageerror", lambda e: blocked.append(str(e)))
        page.goto(f"http://127.0.0.1:{server.port}/#check")
        download = page.locator(".rail [data-local-view='fetch']")
        download.click(timeout=WAIT)  # the page's scripts come from cdn.jsdelivr.net first
        assert blocked == []
        view = page.locator("#fetch")
        sync_api.expect(view).to_be_visible()
        sync_api.expect(page.locator("#crumb-page")).to_have_text("Download")
        assert _shown(page) == ["fetch"]

        view.get_by_role("button", name="Download", exact=True).click()
        sync_api.expect(view.locator(".status")).to_contain_text("Give the account")
        view.get_by_label("The account", exact=True).fill(ACCOUNTS["google"])
        keys = view.locator(".fetch-keys:not([hidden])")
        for name, value in ENVS["google"].items():
            keys.get_by_label(LABELS[name]).fill(value)
        page.screenshot(path=tmp_path / "download-form.png", full_page=True)
        view.get_by_role("button", name="Download", exact=True).click()
        sync_api.expect(view.locator(".rep-title")).to_have_text("Downloaded from Google Ads", timeout=WAIT)
        sync_api.expect(view.locator(".fetch-file")).to_have_count(len(command.NAMES["google"]))
        sync_api.expect(view.locator(".fetch-notes")).to_have_count(0)  # Google's four files leave nothing out
        page.screenshot(path=tmp_path / "download-result.png", full_page=True)
        with page.expect_download() as got:
            view.locator(".fetch-file", has_text="search_terms.csv").get_by_role("button", name="Save").click()
        saved = tmp_path / "search_terms.csv"
        got.value.save_as(saved)
        assert got.value.suggested_filename == "search_terms.csv"
        assert saved.read_text(encoding="utf-8").startswith("Search terms report")
        assert all(s not in page.content() for s in ENVS["google"].values() if "SENTINEL" in s)
        assert page.evaluate("[...document.querySelectorAll('#fetch input[type=password]')].every(n => n.value === '')")

        page.locator(".rail [data-local-view='site']").click()
        assert _shown(page) == ["site"]
        download.click()
        assert _shown(page) == ["fetch"]  # the result waits there
        sync_api.expect(view.locator(".rep-title")).to_be_visible()

        view.get_by_role("button", name="Audit them here").click()
        sync_api.expect(page.locator("#compose")).to_be_visible()
        sync_api.expect(view).to_be_hidden()
        assert page.evaluate("location.hash") == "#audit"
        assert download.get_attribute("aria-current") is None
        names = page.locator("#files .file-name")
        sync_api.expect(names).to_have_count(len(command.NAMES["google"]), timeout=WAIT)
        assert sorted(names.all_text_contents()) == sorted(command.NAMES["google"])
        sync_api.expect(page.locator("#files")).not_to_contain_text("Waiting for the checker", timeout=3 * WAIT)
        sync_api.expect(page.locator("#files .file.bad")).to_have_count(0)  # each one read as the export it stands for
        page.screenshot(path=tmp_path / "audit-files.png", full_page=True)

        page.set_viewport_size({"width": 360, "height": 780})
        assert page.evaluate("document.querySelector('.rail').scrollWidth <= window.innerWidth")
        right = page.evaluate("Math.max(...[...document.querySelectorAll('.rail .ri')].map(n => n.getBoundingClientRect().right))")
        assert right <= 360
        download.click()
        page.screenshot(path=tmp_path / "download-phone.png", full_page=True)
        browser.close()
    assert blocked == []

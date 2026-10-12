"""The app `openppc-online app` serves, in Chromium: its checker loads and audits as on openppc.si, it says it runs on
this computer, and its policy blocks nothing it needs."""
from pathlib import Path

import pytest

from openppc_online import __version__

sync_api = pytest.importorskip("playwright.sync_api", reason='needs pip install -e "companion[e2e]"')
pytestmark = pytest.mark.e2e

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
BOOT = 180_000  # ms: the first visit downloads the Python runtime
READY = "Ready. Everything runs on this device."


def test_the_app_served_here_audits_and_says_where_it_runs(server):
    blocked = []
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda m: blocked.append(m.text) if "Content Security Policy" in m.text else None)
        page.goto(f"http://127.0.0.1:{server.port}/#audit")
        sync_api.expect(page.locator("html")).to_have_attribute("data-local", "on", timeout=30_000)
        sync_api.expect(page.locator(".privacy-long")).to_have_text(
            f"On this device · nothing uploaded · openppc-online {__version__}")
        sync_api.expect(page.locator("#engine-status")).to_have_text(READY, timeout=BOOT)
        page.locator("#file-input").set_input_files(str(EXAMPLES / "keywords_acme.csv"))
        sync_api.expect(page.locator("#run-btn")).to_be_enabled(timeout=BOOT)
        page.locator("#run-btn").click()
        sync_api.expect(page.locator(".badge-ok")).to_be_visible(timeout=BOOT)
        sync_api.expect(page.locator(".who").filter(has_text="on this device")).to_be_visible()
        browser.close()
    assert blocked == []

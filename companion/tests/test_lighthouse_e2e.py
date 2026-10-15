"""Lighthouse attached to OpenPPC's own browser (lab/lighthouse.py), on a calibration fixture: its load goes through
the guard's proxy, its report reads, and no page can reach the DevTools port it attaches over. Needs Node and the
calibration's Lighthouse (npm ci --ignore-scripts in companion/calibration); skipped without them.

No network: only the fixtures' names resolve."""
import shutil
from pathlib import Path

import pytest
from calibration.fixtures import Server, url

from openppc_online.siteaudit import render
from openppc_online.siteaudit.lab import lighthouse
from openppc_online.siteaudit.net import Guard, GuardProxy, Sink

sync_api = pytest.importorskip("playwright.sync_api", reason='needs pip install -e "companion[e2e]"')
pytestmark = pytest.mark.e2e
LIGHTHOUSE = Path(__file__).resolve().parent.parent / "calibration"


@pytest.fixture(scope="module")
def lh():
    if not shutil.which("node"):
        pytest.skip("needs Node.js")
    try:
        return lighthouse.folder(LIGHTHOUSE)
    except ValueError:
        pytest.skip("needs npm ci --ignore-scripts in companion/calibration")


def test_lighthouse_measures_through_the_guard_and_the_devtools_port_stays_shut(lh):
    asked = []

    def resolve(host, port):
        asked.append(host)
        if host.endswith(".test"):
            return ["127.0.0.1"]
        if host in ("127.0.0.1", "localhost"):
            return ["127.0.0.1"]
        raise OSError("offline")
    guard = Guard(allow_private=True, resolve=resolve)
    with Server() as server, GuardProxy(guard) as proxy, Sink() as sink, sync_api.sync_playwright() as pw:
        browser = render._launch(pw, sink.url, devtools=True)
        try:
            address = lighthouse.attach(browser, guard)
            port = int(address.split(":")[2].split("/")[0])
            lhr = lighthouse.run(browser, address, lh, url("hero", server.port), "mobile", proxy.url)
            context = browser.new_context(proxy={"server": proxy.url})
            page = context.new_page()
            try:
                page.goto(f"http://127.0.0.1:{port}/json/version")
                text = page.content()
            except sync_api.Error as e:  # the guard's empty 403, which Chrome shows as an error page
                text = str(e)
            context.close()
        finally:
            browser.close()
    assert lhr["lighthouseVersion"].startswith("13.") and lhr["configSettings"]["throttlingMethod"] == "devtools"
    m = lighthouse.measured(lhr)
    assert m["fcp"] and m["lcp"] and m["lcp"] >= m["fcp"] and m["cls"] == 0
    assert "site.test" in asked                      # Lighthouse's load went through the guard
    assert "ERR_HTTP_RESPONSE_CODE_FAILURE" in text and "webSocketDebuggerUrl" not in text
    assert port in guard.closed and "127.0.0.1" in guard.refused

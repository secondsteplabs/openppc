"""Lighthouse attached to OpenPPC's own browser (lab/lighthouse.py), on a calibration fixture: its load goes through
the guard's proxy, its report reads, and no page can reach the DevTools port it attaches over. Needs Node and the
calibration's Lighthouse (npm ci --ignore-scripts in companion/calibration); skipped without them.

No network: only the fixtures' names resolve."""
import json
import shutil
from pathlib import Path

import pytest
from calibration.fixtures import Server, url
from sites import page

from openppc_online.cli import main
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


def test_the_lighthouse_switch_measures_the_page_on_a_phone_and_a_desktop_and_checks_budgets(lh, serve, tmp_path):
    base = serve(lambda b: {"/": (200, {}, page("Home", "<h1>Spring sale</h1><p>Everything half price.</p>"))})
    pack = tmp_path / "budget.json"
    pack.write_text(json.dumps({"openppc_site": 1, "budgets": [
        {"id": "tight", "severity": "high", "max": {"fcp": 1, "document-kb": 0}, "min": {"speed-score": 100}},
        {"id": "roomy", "severity": "high", "device": "desktop", "max": {"lcp": 60000}}]}), encoding="utf-8")
    out = tmp_path / "site.json"
    assert main(["site", base + "/", "--allow-private", "--fast", "--single", "--render", "--lighthouse", str(lh),
                 "--config", str(pack), "--format", "json", "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    speed = doc["speed"]
    assert [(s["device"], s["source"], s["method"], s["error"]) for s in speed] == [
        ("mobile", "Lighthouse", "simulate", None), ("desktop", "Lighthouse", "simulate", None)]
    assert all(set(s["categories"]) == set(lighthouse.CATEGORIES) and s["score"] is not None for s in speed)
    assert doc["rendered"]["vitals"] == []  # Lighthouse measured the page: the lab doesn't load it again
    found = {f["id"]: f for f in doc["findings"]}
    assert "tight" in found and "roomy" not in found
    assert found["tight"]["notes"][base + "/"].endswith("(Lighthouse, mobile)")
    assert "Your own Lighthouse loaded each page in OpenPPC's browser" in doc["markdown"] and doc["passed"]

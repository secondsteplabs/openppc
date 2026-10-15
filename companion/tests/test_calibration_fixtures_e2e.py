"""The calibration's pages as the harness loads them (tests/calibration/fixtures.py): over HTTPS through the guard's
proxy, HTTP/2 on every host but the HTTP/1.1-only one, the web font loading, and the tag pages' hits reaching the
server, chained pixel included. Needs Node and cryptography; skipped without them. No network."""
import importlib.util
import shutil

import pytest
from calibration.bypass import trusting
from calibration.fixtures import HOST, OTHER_HOSTS, Server, url

from openppc_online.siteaudit import render
from openppc_online.siteaudit.net import Guard, GuardProxy, Sink

sync_api = pytest.importorskip("playwright.sync_api", reason='needs pip install -e "companion[e2e]"')
pytestmark = pytest.mark.e2e
LOCAL = {HOST, *OTHER_HOSTS}

PROTOCOLS = """() => ({page: performance.getEntriesByType('navigation')[0].nextHopProtocol,
  files: [...new Set(performance.getEntriesByType('resource').map(e => new URL(e.name).hostname + ' '
                                                                       + e.nextHopProtocol))]})"""
SHIFTS = """() => new Promise(done => { setTimeout(() => done(0), 500);
  new PerformanceObserver(list => done(list.getEntries().reduce((sum, e) => sum + e.value, 0)))
    .observe({type: 'layout-shift', buffered: true}); })"""


@pytest.fixture(scope="module")
def tls_server():
    if not shutil.which("node") or not importlib.util.find_spec("cryptography"):
        pytest.skip("needs Node.js and cryptography")
    with Server(tls=True) as server:
        yield server


def resolve(host, port):
    if host in LOCAL:
        return ["127.0.0.1"]
    raise OSError("offline")


def test_the_pages_load_over_http2_beside_an_http1_host_with_the_font_and_the_hits(tls_server):
    guard = Guard(allow_private=True, resolve=resolve)
    with GuardProxy(guard) as proxy, Sink() as sink, sync_api.sync_playwright() as pw:
        browser = render._launch(trusting(pw), sink.url)
        try:
            context = browser.new_context(proxy={"server": proxy.url})
            page = context.new_page()
            page.goto(url("http1-host", tls_server.on), wait_until="load")
            seen = page.evaluate(PROTOCOLS)
            page.goto(url("font-swap", tls_server.on), wait_until="load")
            page.wait_for_function("document.fonts.status === 'loaded'")
            font = page.evaluate("document.fonts.check('16px cal')")
            shifted = page.evaluate(SHIFTS)
            for name in ("tags", "tags-chained"):
                page.goto(url(name, tls_server.on), wait_until="load")
                page.wait_for_timeout(2500)
            context.close()
        finally:
            browser.close()
    assert url("text", tls_server.on).startswith("https://site.test:")
    assert seen["page"] == "h2" and seen["files"] == ["old.test http/1.1"], seen
    assert font and shifted > 0.1, shifted  # the swap rewraps the text, a shift Lighthouse and OpenPPC both see
    paths = tls_server.hits
    assert any("en=page_view" in p for p in paths) and any("en=scroll" in p for p in paths)
    assert any(p.startswith("/b/ss/") and "events=event1" in p for p in paths)
    assert any("en=chained" in p for p in paths)  # the pixel's redirect was followed
    assert set(guard.refused) <= {"127.0.0.1"}, guard.refused

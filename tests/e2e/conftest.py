"""The web app in a real browser, served from web/ as openppc.si serves it.

These tests need Playwright and Chromium, and the network: the page downloads Pyodide and its two libraries from
cdn.jsdelivr.net, as it does for every visitor. They are marked e2e and left out of a plain `pytest`:

    pip install -e ".[dev,e2e]" && playwright install chromium
    pytest -m e2e tests/e2e
"""
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

try:
    from playwright import sync_api
except ImportError:  # the tests skip themselves; a plain `pytest` must not fail on the import
    sync_api = None

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
BOOT = 180_000  # ms: the first visit downloads the Python runtime
READY = "Ready. Everything runs on this device."


class _Handler(SimpleHTTPRequestHandler):
    # a worker script must be served as JavaScript; Windows' registry sometimes says text/plain
    extensions_map: ClassVar = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}
    # HTTP/1.0 closes after each response, and on Windows that close can reset a large file mid-transfer
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True


@pytest.fixture(scope="session")
def site():
    server = _Server(("127.0.0.1", 0), functools.partial(_Handler, directory=str(WEB)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


@pytest.fixture(scope="session")
def browser():
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


def _open(browser, site, hash_, **context):
    ctx = browser.new_context(**context)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(site + hash_)
    sync_api.expect(page.locator("#engine-status")).to_have_text(READY, timeout=BOOT)
    return ctx, page


@pytest.fixture
def app(browser, site):
    """A desktop page with the checker loaded, on the audit view."""
    ctx, page = _open(browser, site, "#audit", viewport={"width": 1440, "height": 900},
                      permissions=["clipboard-read", "clipboard-write"])
    yield page
    errors = page.errors
    ctx.close()
    assert errors == []


@pytest.fixture
def phone(browser, site):
    """A phone-sized page with the checker loaded."""
    ctx, page = _open(browser, site, "#home", viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                      device_scale_factor=3)
    yield page
    errors = page.errors
    ctx.close()
    assert errors == []

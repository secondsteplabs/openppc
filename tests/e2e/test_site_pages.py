"""The website's pages (home, docs, articles) scanned by axe in Chromium, on a desktop and on a phone.

The app itself is scanned in test_app.py. The site's Content-Security-Policy blocks a script tag from the CDN, so the
axe source is fetched once and evaluated in the page instead.
"""
import functools
import importlib.util
import threading

import pytest
from conftest import ROOT, _Handler, _Server
from test_app import AXE

pytest.importorskip("playwright.sync_api", reason='needs pip install -e ".[e2e]"')
pytestmark = pytest.mark.e2e

# axe rules the website is allowed to break, at any impact; add a rule here only with a reason.
KNOWN_SITE_AXE: set[str] = set()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "tools" / "build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = tmp_path_factory.mktemp("site")
    pages = [url for url in module.build(out)["pages"] if url != "/app/"]
    server = _Server(("127.0.0.1", 0), functools.partial(_Handler, directory=str(out)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", pages
    server.shutdown()


@pytest.mark.parametrize("size", [{"viewport": {"width": 1440, "height": 900}},
                                  {"viewport": {"width": 390, "height": 844}, "is_mobile": True}],
                         ids=["desktop", "phone"])
def test_no_accessibility_findings_on_any_site_page(browser, built, size):
    base, pages = built
    assert len(pages) >= 9
    ctx = browser.new_context(**size)
    page = ctx.new_page()
    source = page.request.get(AXE).text()
    found = {}
    for url in pages:
        page.goto(base + url)
        page.evaluate(source)
        ids = page.evaluate("""async () => {
            const r = await axe.run(document, { resultTypes: ['violations'] });
            return r.violations.map((v) => v.id);
        }""")
        if set(ids) - KNOWN_SITE_AXE:
            found[url] = sorted(set(ids) - KNOWN_SITE_AXE)
    ctx.close()
    assert found == {}

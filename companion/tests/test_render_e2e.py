"""`openppc-online site --render`'s browser pass in Chromium, on a local shop with a consent banner: tags that fire
before consent are caught, the banner is accepted, the after-consent hits are seen, axe finds the image with no alt
text, and Web Vitals are measured. The browser goes through the guard's proxy, so a page on a private address is
refused unless --allow-private opens it, and it contacts only the hosts the pages load (fitness function 9).

No network: every host name resolves to the local test server."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from openppc.formats import to_html
from sites import qa_site

from openppc_online.cli import main
from openppc_online.siteaudit import checks
from openppc_online.siteaudit import crawl as crawl_module
from openppc_online.siteaudit.checks import evaluate, tracking
from openppc_online.siteaudit.crawl import crawl, follow
from openppc_online.siteaudit.net import Guard
from openppc_online.siteaudit.render import render
from openppc_online.siteaudit.report import report

pytest.importorskip("playwright.sync_api", reason='needs pip install -e "companion[e2e]"')
pytestmark = pytest.mark.e2e

HOSTILE = "<img src=x onerror=alert(1)>`<b>"
# .test names, not the real tracker hosts: those are on Chrome's HTTPS-only (HSTS preload) list
SHOP = """<!doctype html><html lang="en"><head><title>Shop</title>
<meta name="viewport" content="width=device-width"></head><body>
<h1>Shop</h1><p>Everything for the garden, delivered.</p><img src="/hero.gif">
<div id="banner"><button id="onetrust-accept-btn-handler">Accept all</button></div>
<script>
const port = location.port;
const hit = (url) => { new Image().src = url; };
window.dataLayer = [{event: "gtm.js"}, {event: "lead_form"}, {event: "HOSTILE"}];
if (document.cookie.includes("consent=yes")) {
  navigator.sendBeacon(`http://stats.shop.test:${port}/g/collect?v=2&tid=G-TEST1234&gcs=G111`,
                       "en=page_view\\nen=purchase");
} else {
  hit(`http://stats.shop.test:${port}/g/collect?v=2&tid=G-TEST1234&gcs=G100`);
  hit(`http://metrics.shop.test:${port}/b/ss/shop/1/JS-2.0`);
}
const more = document.createElement("a");
more.href = "/spa/page";
more.textContent = "More";
document.body.appendChild(more);
document.getElementById("onetrust-accept-btn-handler").onclick = () => {
  document.cookie = "consent=yes; path=/";
  document.getElementById("banner").remove();
};
</script></body></html>""".replace("HOSTILE", HOSTILE.replace("`", "\\`"))


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        page = self.path in ("/", "/spa/page", "/thanks")
        body, kind = (SHOP.encode(), "text/html; charset=utf-8") if page else (b"", "image/gif")
        self.send_response(200 if page or self.path == "/hero.gif" or "?" in self.path or "/b/ss/" in self.path
                           else 404)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_HEAD = do_GET

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def shop():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def recording():
    """A guard on which every name resolves to the test server, noting each name it was asked for."""
    asked = []

    def resolve(host, port):
        asked.append(host)
        return ["127.0.0.1"]
    return Guard(allow_private=True, resolve=resolve), asked


def test_the_browser_pass_sees_tags_consent_accessibility_and_vitals(shop, tmp_path):
    guard, asked = recording()
    c = crawl(shop, guard, fast=True, external=False)
    r = render(c, guard, pages=1, screenshots=str(tmp_path / "shots"), also=[shop + "/thanks"])
    o = r.pages[0]
    assert not o.error
    assert [p.url for p in r.pages] == [shop + "/", shop + "/thanks"]
    assert o.events["ga4"] == ["page_view", "purchase"] and o.datalayer == ["lead_form", HOSTILE]
    assert o.screenshot.endswith("01-home.png") and (tmp_path / "shots" / "01-home.png").stat().st_size > 0
    assert set(asked) == {"127.0.0.1", "stats.shop.test", "metrics.shop.test"}  # the site and what its pages load
    assert checks.js_only_links(c, r) == {shop + "/spa/page": shop + "/"}
    assert follow(c, guard, checks.js_only_links(c, r), fast=True) == 1
    assert o.consent == "onetrust" and o.accepted
    assert any("/b/ss/" in u for u in o.before) and any("gcs=G100" in u for u in o.before)
    assert any("gcs=G111" in u for u in o.after)
    tags = tracking(c, r)
    assert tags["ga4"]["ping"] and tags["ga4"]["after"] and not tags["ga4"]["before"]
    findings = {f.id: f for f in evaluate(c, r)}
    assert findings["site-tag-before-consent"].items == ["Adobe Analytics"]
    assert "(WCAG `1.1.1`)" in findings["site-a11y:image-alt"].title
    assert findings["site-js-only-links"].items == [shop + "/spa/page"]
    v = r.vitals[0]
    assert len(r.vitals) == 1 and len(v.runs) == 3 and v.median["lcp"] is not None
    assert v.hits_answered == 6  # each speed load's GA4 and Adobe hits answered here, the tags still loaded
    assert v.details["lcp_element"] and isinstance(v.details["heavy"], list)
    markdown, _, passed = report(c, r, list(findings.values()))
    assert passed, markdown
    assert "What slows it down" in markdown and "### Check by hand" in markdown
    assert "<img src=x onerror=alert(1)>'<b>" in markdown  # the event, in a code span its backtick can't close
    assert "<img" not in re.sub(r"`[^`\n]*`", "", markdown)
    assert "<img src=x" not in to_html(markdown, "Site audit")


def test_qa_site_29_screenshots_a_page_no_link_leads_to_and_measures_two_pages(serve, tmp_path, monkeypatch):
    monkeypatch.setattr(crawl_module, "POLITE_INTERVAL", 0.02)
    bad, out, shots = qa_site(serve, "bad"), tmp_path / "site_render.json", tmp_path / "shots"
    assert main(["site", bad, "--allow-private", "--fast", "--render", "--screenshots", str(shots), "--render-url",
                 "/final", "--vitals-pages", "2", "--format", "json", "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    rendered = doc["rendered"]
    assert bad + "final" in [p["url"] for p in rendered["pages"]] and len(rendered["vitals"]) == 2
    assert sorted(p.name for p in shots.iterdir()) == [Path(p["screenshot"]).name for p in rendered["pages"]]
    assert doc["passed"] and doc["scores"]["accessibility"]["not_scored"] is None


def test_qa_site_30_takes_a_consent_selector(serve, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(crawl_module, "POLITE_INTERVAL", 0.02)
    out = tmp_path / "site_render.md"
    assert main(["site", qa_site(serve, "bad"), "--allow-private", "--fast", "--render", "--consent-selector",
                 "#accept", "--vitals-pages", "0", "--out", str(out)]) == 0
    markdown = out.read_text(encoding="utf-8")
    assert "in Chromium for tags, consent" in markdown and "--render`" not in markdown


def test_the_browser_is_held_to_the_same_address_rules(shop):
    c = crawl(shop, Guard(allow_private=True, resolve=lambda host, port: ["127.0.0.1"]), fast=True, external=False)
    r = render(c, Guard(), pages=1, vitals=0)
    assert r.refused == ["127.0.0.1"]
    assert not any("/b/ss/" in u for u in r.pages[0].before)

"""The Tag Inspector in Chromium: it reads a shop page's tags, dataLayer and consent, shows the page's text as
text, and sends nothing. Offline: every request is answered by the test, and any it didn't expect fails it.

A test can't click the toolbar button that grants activeTab, so the copy loaded here also has host permission
for the fixture's address, and an empty background worker that tells the test the extension's id."""
import json
import re
import shutil
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason='needs pip install -e "companion[e2e]"')
pytestmark = pytest.mark.e2e

EXTENSION = Path(__file__).parents[1] / "extension"
WAIT = 30_000  # ms
HOSTILE = "<img src=x onerror=alert(1)>"
SHOP = """<!doctype html><html lang="en"><head><title>Shop</title>
<meta name="description" content="Things to buy."><link rel="canonical" href="https://shop.test/">
<script src="https://cdn.cookielaw.org/scripttemplates/otSDKStub.js"></script>
<script src="https://www.googletagmanager.com/gtag/js?id=G-ABC123"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('consent', 'default', {ad_storage: 'denied', analytics_storage: 'denied'});
dataLayer.push({event: 'gtm.js'}, {event: 'add_to_cart'}, {event: 'HOSTILE'});
for (const src of ['https://region1.google-analytics.com/g/collect?v=2&en=page_view&gcs=G100',
                   'https://www.facebook.com/tr/?id=1&ev=PageView', 'https://cdn.taboola.com/px.gif']) {
  new Image().src = src;
}
</script></head><body><h1>Shop</h1></body></html>""".replace("HOSTILE", HOSTILE)
ANSWERS = {
    "https://shop.test/": ("text/html", SHOP),
    "https://cdn.cookielaw.org/": ("text/javascript", ""),
    "https://www.googletagmanager.com/": ("text/javascript", ""),
    "https://region1.google-analytics.com/": ("image/gif", "GIF89a"),
    "https://www.facebook.com/": ("image/gif", "GIF89a"),
    "https://cdn.taboola.com/": ("image/gif", "GIF89a"),
}
READ = """async () => {
  const { inspect } = await import(chrome.runtime.getURL('inspect.js'));
  const { render } = await import(chrome.runtime.getURL('view.js'));
  const signatures = await (await fetch(chrome.runtime.getURL('signatures.json'))).json();
  const [shop] = await chrome.tabs.query({ url: 'https://shop.test/*' });
  render(document.getElementById('report'), await inspect(shop.id), signatures);
  const self = await chrome.tabs.getCurrent();
  return inspect(self.id).then(() => 'read', () => 'refused');
}"""


def _loadable_copy(tmp_path):
    copy = tmp_path / "extension"
    shutil.copytree(EXTENSION, copy)
    manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    manifest["host_permissions"] = ["https://shop.test/*"]
    manifest["background"] = {"service_worker": "id.js"}
    (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (copy / "id.js").write_text("", encoding="utf-8")
    return copy


def test_the_inspector_reads_a_shop_and_sends_nothing(tmp_path):
    copy = _loadable_copy(tmp_path)
    unexpected, problems = [], []

    def answer(route):
        url = route.request.url
        for prefix, (kind, body) in ANSWERS.items():
            if url.startswith(prefix):
                return route.fulfill(body=body, content_type=kind)
        unexpected.append(url)
        return route.abort()

    with sync_api.sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(tmp_path / "profile"), channel="chromium", headless=True,
            args=[f"--disable-extensions-except={copy}", f"--load-extension={copy}"])
        try:
            context.route(re.compile(r"^https?://"), answer)  # not the extension's own chrome-extension:// files
            worker = context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker")
            extension_id = worker.url.split("/")[2]
            shop = context.new_page()
            shop.goto("https://shop.test/")
            shop.wait_for_function("performance.getEntriesByType('resource').length >= 5", timeout=WAIT)

            popup = context.new_page()
            popup.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
            popup.on("pageerror", lambda e: problems.append(str(e)))
            popup.goto(f"chrome-extension://{extension_id}/popup.html")
            sync_api.expect(popup.locator("#report")).not_to_contain_text("Reading this page", timeout=WAIT)
            assert popup.evaluate(READ) == "refused"  # the browser keeps it out of extension pages

            report = popup.locator("#report")
            sync_api.expect(report).to_contain_text("https://shop.test/")
            for text in ("Google Analytics 4", "page_view", "Meta Pixel", "PageView", "Consent banner: OneTrust.",
                         "Google Consent Mode is on, with 1 cookieless ping(s) sent before consent.",
                         "Consent Mode default: ad_storage denied, analytics_storage denied.",
                         "cdn.taboola.com: not in OpenPPC's tag list", "Shop (4 characters)"):
                sync_api.expect(report).to_contain_text(text)
            events = report.locator("h2:has-text('Events in the dataLayer') + p")
            sync_api.expect(events).to_have_text(f"add_to_cart, {HOSTILE}")
            assert report.locator("img").count() == 0
            assert problems == []
        finally:
            context.close()
    assert unexpected == []

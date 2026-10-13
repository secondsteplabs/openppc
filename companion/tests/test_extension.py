"""The Tag Inspector browser extension (companion/extension/): the same signatures as the crawler, and its
Node tests, run here so `pytest companion` covers them."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

COMPANION = Path(__file__).parents[1]
EXTENSION = COMPANION / "extension"
SHIPPED = {"manifest.json", "popup.html", "popup.css", "popup.js", "inspect.js", "view.js", "match.js",
           "signatures.json", "README.md"}
CODE = [p for p in EXTENSION.iterdir() if p.suffix in (".js", ".html")]
SENDS = ("XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource", "importScripts", "import(", "chrome.storage",
         "chrome.runtime.sendMessage", "chrome.runtime.connect", "window.open")
MARKUP = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function")


def test_the_extension_folder_is_what_ships():
    assert {p.name for p in EXTENSION.iterdir()} == SHIPPED


def test_the_extension_asks_for_the_least():
    m = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    assert m["manifest_version"] == 3
    assert m["permissions"] == ["activeTab", "scripting"]
    for key in ("host_permissions", "optional_permissions", "optional_host_permissions", "background",
                "content_scripts", "web_accessible_resources", "externally_connectable"):
        assert key not in m, key
    assert m["content_security_policy"] == {
        "extension_pages": "script-src 'self'; object-src 'none'; connect-src 'self'"}
    assert len(m["description"]) <= 132  # the stores' limit


@pytest.mark.parametrize("path", CODE, ids=lambda p: p.name)
def test_the_extension_has_no_way_to_send_or_inject_anything(path):
    src = path.read_text(encoding="utf-8")
    for word in SENDS + MARKUP:
        assert word not in src, word
    assert not re.search(r"https?://", src)
    fetches = re.findall(r"\bfetch\([^)]*\)", src)
    assert fetches in ([], ["fetch(chrome.runtime.getURL('signatures.json')"]), fetches


def test_the_popup_runs_only_its_own_scripts():
    html = (EXTENSION / "popup.html").read_text(encoding="utf-8")
    assert re.findall(r"<script[^>]*>", html) == ['<script type="module" src="popup.js">']
    assert not re.search(r"\son\w+\s*=|\sstyle\s*=", html)


def test_the_extension_knows_the_crawlers_tags():
    crawler = COMPANION / "openppc_online" / "siteaudit" / "signatures.json"
    assert (EXTENSION / "signatures.json").read_bytes() == crawler.read_bytes(), \
        "copy openppc_online/siteaudit/signatures.json to extension/signatures.json"


def test_the_extensions_node_tests_pass():
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("CI needs Node.js 22 or later for these tests")
        pytest.skip("needs Node.js 22 or later")
    tests = sorted(str(p) for p in (Path(__file__).parent / "js").glob("*.test.mjs"))
    assert tests
    run = subprocess.run([node, "--test", *tests], capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr

"""Lighthouse attached to OpenPPC's own page (lab/lighthouse.py), without a browser or Node: finding the package,
refusing a node script, reading the DevTools port, the run's arguments and failures, and the report's metrics. The
real run is in test_lighthouse_e2e.py."""
import json
import subprocess
from pathlib import Path

import pytest

from openppc_online.siteaudit.lab import lighthouse
from openppc_online.siteaudit.net import Guard

FIXTURE = Path(__file__).parent / "fixtures" / "lhr-13.5-mobile.json"


def install(where: Path, version: str = "13.5.0", name: str = "lighthouse") -> Path:
    (where / "core").mkdir(parents=True)
    (where / "core" / "index.js").write_text("export default 1;", encoding="utf-8")
    (where / "package.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")
    return where


def test_the_package_is_found_as_given_or_in_node_modules(tmp_path):
    pkg = install(tmp_path / "proj" / "node_modules" / "lighthouse")
    assert lighthouse.folder(tmp_path / "proj") == pkg.resolve()
    assert lighthouse.folder(pkg) == pkg.resolve()


@pytest.mark.parametrize("version, name, match", [
    ("12.8.2", "lighthouse", "has Lighthouse 12.8.2; OpenPPC reads Lighthouse 13"),
    ("13.5.0", "not-lighthouse", "no Lighthouse in"),
])
def test_another_version_or_package_is_refused(tmp_path, version, name, match):
    install(tmp_path / "lh", version, name)
    with pytest.raises(ValueError, match=match):
        lighthouse.folder(tmp_path / "lh")


def test_nothing_there_says_how_to_install_it(tmp_path):
    with pytest.raises(ValueError, match="npm install lighthouse@13"):
        lighthouse.folder(tmp_path)


@pytest.mark.parametrize("found", [r"C:\node\node.cmd", r"C:\node\node.BAT"])
def test_a_node_script_is_refused(monkeypatch, found):
    monkeypatch.setattr(lighthouse.shutil, "which", lambda name: found)
    with pytest.raises(ValueError, match="cmd.exe"):
        lighthouse.node()


def test_no_node_says_so(monkeypatch):
    monkeypatch.setattr(lighthouse.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="needs Node.js"):
        lighthouse.node()


class FakeContext:
    def __init__(self, browser):
        self.browser = browser
        self.closed = False

    def new_page(self):
        return FakePage(self)

    def close(self):
        self.closed = True


class FakePage:
    def __init__(self, context):
        self.context = context

    def goto(self, url):
        self.context.browser.visited.append(url)

    def locator(self, selector):
        assert selector == "#profile_path"
        return self

    def inner_text(self):
        return str(self.context.browser.profile) + "\n"


class FakeBrowser:
    def __init__(self, profile):
        self.profile = profile
        self.visited = []
        self.contexts = []

    def new_page(self):
        return FakeContext(self).new_page()

    def new_context(self, **kwargs):
        c = FakeContext(self)
        c.kwargs = kwargs
        self.contexts.append(c)
        return c


def test_attach_reads_the_port_file_and_closes_the_port(tmp_path):
    (tmp_path / "DevToolsActivePort").write_text("51234\n/devtools/browser/abc-123\n", encoding="utf-8")
    guard = Guard()
    address = lighthouse.attach(FakeBrowser(tmp_path / "Default"), guard)
    assert address == "ws://127.0.0.1:51234/devtools/browser/abc-123" and guard.closed == {51234}


@pytest.mark.parametrize("text", ["", "abc\n/devtools/browser/x", "9222\n/json/version"])
def test_attach_refuses_a_missing_or_odd_port_file(tmp_path, monkeypatch, text):
    monkeypatch.setattr(lighthouse, "PORT_WAIT_S", 0.0)
    if text:
        (tmp_path / "DevToolsActivePort").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="DevTools"):
        lighthouse.attach(FakeBrowser(tmp_path / "Default"), Guard())


def fake_node(monkeypatch, result=None, raises=None):
    calls = []
    monkeypatch.setattr(lighthouse, "node", lambda: "node")

    def fake(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if raises:
            raise raises
        return result
    monkeypatch.setattr(lighthouse.subprocess, "run", fake)
    return calls


def test_a_run_attaches_to_a_marked_page_behind_the_proxy(tmp_path, monkeypatch):
    lhr = json.loads(FIXTURE.read_text(encoding="utf-8"))
    calls = fake_node(monkeypatch, subprocess.CompletedProcess([], 0, json.dumps(lhr), ""))
    browser = FakeBrowser(tmp_path)
    got = lighthouse.run(browser, "ws://127.0.0.1:1/devtools/browser/x", tmp_path, "https://example.com/", "mobile",
                         "http://127.0.0.1:2")
    assert got["lighthouseVersion"] == lhr["lighthouseVersion"]
    (cmd, kwargs), = calls
    script, lh, address, marker, url, device, method, categories = cmd[1:]
    assert script.endswith("lighthouse.mjs") and Path(script).is_file()
    assert (lh, address, url, device, method, categories) == (
        str(tmp_path), "ws://127.0.0.1:1/devtools/browser/x", "https://example.com/", "mobile", "devtools",
        "performance")
    assert marker.startswith("about:blank#openppc-") and browser.visited == [marker]
    context, = browser.contexts
    assert context.kwargs["proxy"] == {"server": "http://127.0.0.1:2"} and context.closed
    assert kwargs["timeout"] == lighthouse.RUN_S and "shell" not in kwargs
    lighthouse.run(browser, "ws://x", tmp_path, "https://example.com/", "mobile", "p", "simulate", lighthouse.CATEGORIES)
    assert calls[-1][0][-2:] == ["simulate", "performance,accessibility,best-practices,seo"]


@pytest.mark.parametrize("result, raises, match", [
    (subprocess.CompletedProcess([], 1, "", "noise\nError: Lighthouse was unable to reliably load the page\n"),
     None, "Lighthouse stopped: Error: Lighthouse was unable to reliably load the page"),
    (subprocess.CompletedProcess([], 3, "", ""), None, "exit code 3"),
    (subprocess.CompletedProcess([], 0, "not json", ""), None, "isn't a report"),
    (subprocess.CompletedProcess([], 0, "[1, 2]", ""), None, "isn't a report"),
    (None, subprocess.TimeoutExpired("node", 300), "ran past 300 seconds"),
])
def test_a_failed_run_says_why_and_closes_its_context(tmp_path, monkeypatch, result, raises, match):
    fake_node(monkeypatch, result, raises)
    browser = FakeBrowser(tmp_path)
    with pytest.raises(lighthouse.Failed, match=match):
        lighthouse.run(browser, "ws://x", tmp_path, "https://example.com/", "desktop", "http://127.0.0.1:2")
    assert browser.contexts[0].closed


def test_an_unknown_device_or_method_is_refused_before_anything_starts(tmp_path):
    with pytest.raises(ValueError, match="no Lighthouse run"):
        lighthouse.run(FakeBrowser(tmp_path), "ws://x", tmp_path, "https://a/", "tablet", "p")
    with pytest.raises(ValueError, match="no Lighthouse run"):
        lighthouse.run(FakeBrowser(tmp_path), "ws://x", tmp_path, "https://a/", "mobile", "p", "provided")
    with pytest.raises(ValueError, match="no Lighthouse run"):
        lighthouse.run(FakeBrowser(tmp_path), "ws://x", tmp_path, "https://a/", "mobile", "p", "simulate", ("pwa",))


def test_the_reports_metrics_are_named_as_the_lab_names_them():
    m = lighthouse.measured(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert m == {"fcp": 6795.0, "lcp": 10885.0, "tbt": 1055.0, "cls": 0.099576, "si": 8296.0, "ttfb": 10.0,
                 "tti": 8012.0}
    assert lighthouse.measured({"audits": {}}) == dict.fromkeys(lighthouse.METRICS)
    assert lighthouse.measured({"audits": {"metrics": {"details": {"items": [{"interactive": True}]}}}})["tti"] is None

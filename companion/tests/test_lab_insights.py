"""Lighthouse's insights (lab.insights) without a browser: the vendored trace engine is the build of the pinned
sources, the engine's answer becomes Insights as Lighthouse reports them, and the page it runs in is closed. The
engine on real loads is checked against Lighthouse in tests/calibration/insights.py and in test_render_e2e.py."""
import hashlib

import pytest

from openppc_online.siteaudit.lab import insights
from openppc_online.siteaudit.lab.throttle import MOBILE

# companion/calibration's `npm run vendor` from its lockfile (trace engine 0.0.65, esbuild 0.28.2); the calibration
# workflow rebuilds it and compares
ENGINE_SHA256 = "c5a75c7e2fa81109c63ff13da56974c000a4832885e7a9ffe59873efd37312a2"


def test_the_vendored_trace_engine_is_the_pinned_build_with_its_licences():
    source = insights.engine_source()
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == ENGINE_SHA256
    head = source[:4000]
    assert head.startswith(f"/*! OpenPPC's bundle of @paulirish/trace_engine {insights.ENGINE_VERSION} (BSD-3-Clause)")
    assert "Copyright 2014 The Chromium Authors" in head and "Patrick Hulce" in head and "Apache License" in head


@pytest.mark.parametrize("name, audit", [
    ("LCPDiscovery", "lcp-discovery-insight"), ("CLSCulprits", "cls-culprits-insight"), ("DOMSize", "dom-size-insight"),
    ("ModernHTTP", "modern-http-insight"), ("DuplicatedJavaScript", "duplicated-javascript-insight")])
def test_the_engines_names_are_lighthouses_audit_ids(name, audit):
    assert insights.audit_id(name) == audit


def test_savings_are_rounded_as_lighthouse_rounds_them():
    assert insights.quantized({"FCP": 892.4, "LCP": 24, "CLS": 0.12449, "TBT": -5, "INP": True}) == \
        {"FCP": 900, "CLS": 0.124}


class Page:
    def __init__(self, answer):
        self.answer, self.sent, self.args, self.closed = answer, [], None, False
        self.context = self

    def new_cdp_session(self, page):
        return self

    def send(self, method, params):
        self.sent.append(method)

    def evaluate(self, js, args):
        self.args = args
        return self.answer

    def close(self):
        self.closed = True


class Browser:
    def __init__(self, answer):
        self.page = Page(answer)

    def new_page(self):
        return self.page


def test_the_engines_answer_becomes_insights_failing_first():
    answer = {"url": "https://a.test/", "insights": {
        "Cache": {"state": "pass", "title": "Use efficient cache lifetimes", "metricSavings": {}, "wastedBytes": 0},
        "RenderBlocking": {"state": "fail", "title": "Render blocking requests", "metricSavings": {"FCP": 901.2},
                           "wastedBytes": None, "failed": [], "items": ["https://a.test/app.css"]},
        "DocumentLatency": {"state": "fail", "title": "Document request latency", "metricSavings": {"FCP": 10},
                            "wastedBytes": 2610.4, "failed": ["Applies text compression"]},
        "ForcedReflow": {"error": "Error: no stacks"}}}
    browser = Browser(answer)
    found = insights.run(browser, [{"name": "x"}], "mobile").insights
    assert [(i.id, i.state) for i in found] == [("render-blocking-insight", "fail"),
                                                ("document-latency-insight", "fail"), ("cache-insight", "pass")]
    assert found[0].savings == {"FCP": 900} and found[0].items == ["https://a.test/app.css"]
    assert found[1].savings == {} and found[1].bytes == 2610 and found[1].failed == ["Applies text compression"]
    page = browser.page
    assert page.sent == ["Runtime.evaluate"] and page.closed
    text, settings, dpr, debug = page.args
    assert text == '[{"name": "x"}]' and settings["cpuSlowdownMultiplier"] == 4 and settings["rttMs"] == 150
    assert settings["requestLatencyMs"] == MOBILE.latency_ms and dpr == MOBILE.scale and debug is False


def test_each_tags_files_are_summed_and_the_site_and_unknown_hosts_left_out():
    costs = [
        {"url": "https://www.googletagmanager.com/gtm.js?id=GTM-X", "bytes": 90_000, "ms": 120.4},
        {"url": "https://www.googletagmanager.com/gtag/js?id=G-X", "bytes": 40_000, "ms": 30},
        {"url": "https://www.google-analytics.com/g/collect?v=2", "bytes": 0, "ms": 0.5},
        {"url": "https://connect.facebook.net/en_US/fbevents.js", "bytes": 60_000.4, "ms": 15},
        {"url": "https://cdn.cookielaw.org/scripttemplates/otSDKStub.js", "bytes": 20_000, "ms": 200},
        {"url": "https://a.test/app.js", "bytes": 500_000, "ms": 900},
        {"url": "https://cdn.unknown.test/x.js", "bytes": 1, "ms": 1},
        {"url": "https://connect.facebook.net/signals/config", "bytes": None, "ms": "x"}]
    got = {t.id: (t.kind, t.bytes, round(t.ms, 1), t.files) for t in insights.tag_costs(costs)}
    assert got == {"onetrust": ("consent", 20_000, 200.0, 1), "gtm": ("tag", 90_000, 120.4, 1),
                   "ga4": ("tag", 40_000, 30.5, 2), "meta": ("tag", 60_000, 15.0, 2)}
    assert [t.id for t in insights.tag_costs(costs)] == ["onetrust", "gtm", "ga4", "meta"]
    assert insights.tag_costs(costs, answered=True)[2].files == 1  # GA4's hit was answered here, so isn't its cost


def test_the_engines_costs_come_back_per_tag():
    answer = {"url": "https://a.test/", "insights": {}, "costs": [
        {"url": "https://connect.facebook.net/en_US/fbevents.js", "bytes": 1000, "ms": 5}, "junk"]}
    found = insights.run(Browser(answer), [], "mobile")
    assert found.insights == [] and [(t.name, t.bytes) for t in found.tags] == [("Meta Pixel", 1000)]


def test_a_trace_with_no_page_load_is_an_error_and_the_page_still_closes():
    browser = Browser({"error": "no navigation in the trace"})
    with pytest.raises(ValueError, match="no navigation"):
        insights.run(browser, [], "desktop")
    assert browser.page.closed and browser.page.args[2] == 1.0


def test_unthrottled_keeps_the_screen_and_drops_the_throttling():
    fast = MOBILE.unthrottled()
    assert (fast.width, fast.scale, fast.user_agent) == (MOBILE.width, MOBILE.scale, MOBILE.user_agent)
    assert fast.cpu == 1 and fast.network() is None

"""PageSpeed Insights (--psi), the Lighthouse report reader and its parity matrix, the one-page check (--single), and
the report's speed score, real-visitor and Lighthouse audit sections. Nothing here reaches Google: PSI is a local
server, and the fitness test maps the names it uses to a public address that connects to this computer."""
import gzip
import json
import threading
from concurrent.futures import Future
from pathlib import Path

import jsonschema
import pytest
from sites import PSI_HOST, PUBLIC, by_id, local, page

from openppc_online import site
from openppc_online.cli import main
from openppc_online.siteaudit import checks, crux, words
from openppc_online.siteaudit.crawl import Crawl, crawl
from openppc_online.siteaudit.lab import lhr, psi
from openppc_online.siteaudit.net import Guard, Response
from openppc_online.siteaudit.report import Extras, data, report

COMPANION = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
LHR = json.loads((FIXTURES / "lhr-13.5-mobile.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((COMPANION / "openppc_online" / "schemas" / "site-report.schema.json").read_text(encoding="utf-8"))

def _share(good, middle, poor):
    return [{"min": 0, "max": 1, "proportion": good}, {"min": 1, "max": 2, "proportion": middle},
            {"min": 2, "proportion": poor}]


EXPERIENCE = {"overall_category": "AVERAGE", "metrics": {
    "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 3100, "distributions": _share(0.61, 0.27, 0.12)},
    "INTERACTION_TO_NEXT_PAINT": {"percentile": 180, "distributions": _share(0.8, 0.15, 0.05)},
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 5, "distributions": _share(0.9, 0.06, 0.04)},
    "FIRST_CONTENTFUL_PAINT_MS": {"percentile": 2000, "distributions": _share(0.5, 0.3, 0.2)},
    "EXPERIMENTAL_TIME_TO_FIRST_BYTE": {"percentile": 900, "distributions": _share(0.4, 0.4, 0.2)}}}


def psi_answer(fallback=False):
    """PSI's answer as a route for `serve`, gzipped as Google sends it (and small enough for Windows loopback)."""
    body = json.dumps({"lighthouseResult": LHR, "originLoadingExperience": EXPERIENCE,
                       "loadingExperience": {**EXPERIENCE, "origin_fallback": True} if fallback else EXPERIENCE})
    return 200, {"Content-Type": "application/json", "Content-Encoding": "gzip"}, gzip.compress(body.encode())


def test_the_parity_matrix_maps_every_audit_in_the_fixtures():
    mapped = lhr.matrix()
    for path in FIXTURES.glob("lhr-*.json"):
        audits = set(json.loads(path.read_text(encoding="utf-8"))["audits"])
        assert audits <= set(mapped), sorted(audits - set(mapped))
    assert {m.openppc for m in mapped.values()} - {"", "llms.txt"} <= set(checks.RULES)
    assert {m.section for m in mapped.values()} == {"ad-click", "other"}
    assert set(words.AUDITS) <= {a for a, m in mapped.items() if m.section == "ad-click"}


def test_psi_real_visitor_data_reads_as_pagespeed_shows_it():
    d = crux.from_psi(EXPERIENCE, "https://a.test/", False, "phone")
    assert d.p75 == {"lcp": 3100, "inp": 180, "cls": 0.05, "fcp": 2000, "ttfb": 900}
    assert d.shares["lcp"] == [0.61, 0.27, 0.12] and d.verdict == "failed" and d.source == "PageSpeed Insights"
    assert crux.from_psi({**EXPERIENCE, "overall_category": "FAST"}, "https://a.test", True, "phone").verdict == "passed"
    assert crux.from_psi({**EXPERIENCE, "origin_fallback": True}, "https://a.test/", False, "phone").error.startswith(
        "too few real visitors")
    assert crux.from_psi(None, "https://a.test", True, "desktop").error == crux.NO_DATA


@pytest.mark.parametrize("p75, verdict", [
    ({"lcp": 2500, "inp": 200, "cls": 0.1}, "passed"),     # the line itself is good
    ({"lcp": 2501, "inp": 100, "cls": 0.05}, "failed"),
    ({"lcp": 2000, "cls": 0.05}, "passed"),                 # no INP: LCP and CLS decide
    ({"lcp": 2000, "inp": 201, "cls": 0.05}, "failed"),
    ({"lcp": 2000, "inp": 100}, "")])                       # no CLS: no assessment
def test_the_core_web_vitals_assessment(p75, verdict):
    assert crux.assess(p75) == verdict


def test_psi_is_asked_through_the_guard_with_the_key_in_a_header(serve, monkeypatch):
    api = serve(lambda b: {"/psi": psi_answer(),
                           "/quota": (429, {}, json.dumps({"error": {"message": "Quota exceeded"}})),
                           "/refused": (400, {}, json.dumps({"error": {"message": "API key not valid."}}))})
    monkeypatch.setattr(psi, "ENDPOINT", api + "/psi")
    s = psi.measure_one("https://a.test/", "mobile", "SENTINEL-PSI-KEY", local())
    path, headers = serve.heard[-1]
    assert "SENTINEL-PSI-KEY" not in path and headers["X-Goog-Api-Key"] == "SENTINEL-PSI-KEY"
    assert "strategy=mobile" in path and "category=seo" in path and "url=https%3A%2F%2Fa.test%2F" in path
    assert s.score == round(LHR["categories"]["performance"]["score"] * 100) and s.device == "mobile" and not s.error
    assert [(d.origin, d.device) for d in s.field_data] == [(False, "phone"), (True, "phone")]
    monkeypatch.setattr(psi, "ENDPOINT", api + "/quota")
    assert psi.measure_one("https://a.test/", "mobile", "", local()).error == psi.QUOTA
    calls = []

    def dropped(url, *a, **kw):
        calls.append(url)
        return Response(url, url, 0, error="ConnectionResetError" if len(calls) == 1 else "timed out")
    monkeypatch.setattr(psi, "fetch", dropped)
    assert psi.measure_one("https://a.test/", "mobile", "", local()).error.endswith("timed out") and len(calls) == 2
    monkeypatch.undo()
    monkeypatch.setattr(psi, "ENDPOINT", api + "/refused")
    assert psi.measure_one("https://a.test/", "desktop", "SENTINEL-PSI-KEY", local()).error == \
        "the PSI key was refused"


@pytest.mark.parametrize("urls, resolves, allow_private, message", [
    (["https://a.test/"], PUBLIC, True, "can't be used with --allow-private"),
    ([f"https://a.test/{n}" for n in range(psi.MAX_PAGES + 1)], PUBLIC, False, "at most 5 pages"),
    (["https://a.test/?token=abc"], PUBLIC, False, "secret-looking value"),
    (["https://a.test/"], "10.0.0.5", False, "public pages only"),
    (["https://a.test/"], "", False, "public pages only")])
def test_psi_refuses_what_it_cant_measure_before_sending_anything(urls, resolves, allow_private, message):
    def resolve(host, port):
        if not resolves:
            raise OSError("no such name")
        return [resolves]
    with pytest.raises(ValueError, match=message):
        psi.check(urls, Guard(allow_private=allow_private, resolve=resolve))


def test_one_page_only_skips_what_needs_the_whole_site(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home", "<a href='/a'>a</a><a href='http://elsewhere.test/'>x</a>")),
                            "/a": (200, {}, page("Home")), "/thanks": (200, {}, page("Thanks"))})
    c = crawl(base, local(), fast=True, single=True, also=[base + "/thanks"])
    assert set(c.pages) == {c.start, base + "/thanks"} and c.single
    assert c.probe is None and not c.sitemap_files and not c.external and not c.llms_txt
    found = by_id(checks.evaluate(c))
    assert not set(found) & checks.WHOLE_SITE and "site-no-https" in found
    assert checks.WHOLE_SITE <= set(checks.RULES)
    markdown, _, passed = report(c, None, list(found.values()))
    assert passed and "One page only" in markdown and "URLs listed in the sitemap" not in markdown


def _speed(url, device="mobile"):
    s = lhr.read(LHR, url, psi.SOURCE)
    s.device = device
    who = "phone" if device == "mobile" else "desktop"
    s.field_data = [crux.from_psi(EXPERIENCE, url, False, who), crux.from_psi(EXPERIENCE, "https://a.test", True, who)]
    return s


def test_the_speed_score_is_the_performance_area_and_the_report_traces(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    c = crawl(base, local(), fast=True, external=False, single=True)
    speed = [_speed(c.start), _speed(c.start, "desktop")]
    field = [d for s in speed for d in s.field_data]
    findings = checks.evaluate(c, None, field, speed)
    assert "site-lcp-slow" in by_id(findings)   # the fixture's LCP is slow, so Lighthouse's numbers made a finding
    extras = Extras(field_data=field, speed=speed)
    markdown, _, passed = report(c, None, findings, extras)
    assert passed, markdown
    score = speed[0].score
    assert f"| Performance | {score} |" in markdown and "no points of their own" in markdown
    for heading in ("## Speed (PageSpeed Insights)", "## All Lighthouse audits", "### What affects the ad click",
                    "### Not about the ad click", "### On phones", "### On desktops"):
        assert heading in markdown, heading
    assert "Core Web Vitals assessment: **failed**" in markdown and "61%" in markdown
    assert "Web Vitals) need a browser" not in markdown   # the LHR covered them
    plain = markdown.split("## What the speed measures mean")[1].split("\n## ")[0]
    assert all(f"**{name}:**" in plain for name, _ in words.MEASURES.values())  # PSI shows all seven
    assert f"In plain words: {words.AUDITS['render-blocking-insight']}" in markdown
    glossary = markdown.split("## Glossary")[1]
    assert "**Lighthouse:**" in glossary and "**p75:**" in glossary and "**Canonical:**" not in glossary
    doc = data(c, None, findings, extras)
    perf = doc["scores"]["performance"]
    assert perf["score"] == score and perf["method"] == "PageSpeed Insights speed score"
    assert perf["lost"] and all(x["points"] == 0 for x in perf["lost"])
    assert [s["device"] for s in doc["speed"]] == ["mobile", "desktop"] and doc["speed"][0]["metrics"]


def test_the_page_is_shown_first_and_the_site_stands_in_when_it_has_too_few_visitors(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    c = crawl(base, local(), fast=True, external=False, single=True)
    s = _speed(c.start)
    s.field_data[0] = crux.from_psi({**EXPERIENCE, "origin_fallback": True}, c.start, False, "phone")
    markdown, _, passed = report(c, None, [], Extras(field_data=s.field_data, speed=[s]))
    assert passed and "has too few real visitors of its own, so these are the whole site's" in markdown
    empty = [crux.from_psi(None, c.start, False, "phone"), crux.from_psi(None, base, True, "phone")]
    markdown, _, passed = report(c, None, [], Extras(field_data=empty))
    assert passed and "Not enough real visitors yet" in markdown


def test_psi_is_never_sent_a_page_robots_txt_keeps_openppc_out_of(serve, public, monkeypatch):
    robots = "User-agent: *\nDisallow: /thanks\n"
    site_ = serve(lambda b: {"/": (200, {}, page("Home")), "/thanks": (200, {}, page("Thanks")),
                             "/robots.txt": (200, {"Content-Type": "text/plain"}, robots)})
    api = serve(lambda b: {"/psi": psi_answer()})
    monkeypatch.setattr(psi, "ENDPOINT", api.replace("127.0.0.1", PSI_HOST) + "/psi")
    start = site_.replace("127.0.0.1", "shop.test") + "/"
    result, _ = site.run(start, max_per_pattern=500, fast=True, psi_key="", single=True, render_url=["/thanks"])
    asked = [path for path, _ in serve.heard if path.startswith("/psi")]
    assert asked and not any("thanks" in path for path in asked) and result.passed
    hidden = serve(lambda b: {"/": (200, {}, page("Home")),
                              "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nDisallow: /\n")})
    before = len(serve.heard)
    site.run(hidden.replace("127.0.0.1", "shop.test") + "/", max_per_pattern=500, psi_key="", single=True)
    assert not any(path.startswith("/psi") for path, _ in serve.heard[before:])


def test_psi_contacts_only_its_declared_host_and_the_key_never_shows(serve, public, tmp_path, capsys, monkeypatch):
    site = serve(lambda b: {"/": (200, {}, page("Home"))})
    api = serve(lambda b: {"/psi": psi_answer(fallback=True)})
    monkeypatch.setattr(psi, "ENDPOINT", api.replace("127.0.0.1", PSI_HOST) + "/psi")
    start = site.replace("127.0.0.1", "shop.test") + "/"
    key = "SENTINEL-PSI-KEY-5b0e"
    out = tmp_path / "site.json"
    assert main(["site", start, "--single", "--fast", "--format", "json", "--out", str(out)]) == 0
    assert set(public) == {"shop.test", PUBLIC}   # no --psi: Google isn't asked
    public.clear()
    assert main(["site", start, "--single", "--fast", "--psi-key", key, "--format", "json", "--out", str(out)]) == 0
    assert set(public) == {"shop.test", PSI_HOST, PUBLIC}
    asked = [(path, headers) for path, headers in serve.heard if path.startswith("/psi")]
    assert {"mobile" if "strategy=mobile" in p else "desktop" for p, _ in asked} == {"mobile", "desktop"}
    assert all(h["X-Goog-Api-Key"] == key for _, h in asked)
    text = out.read_text(encoding="utf-8")
    assert key not in text + capsys.readouterr().err
    doc = json.loads(text)
    jsonschema.validate(doc, SCHEMA)
    assert doc["passed"] and doc["single"] and doc["scores"]["performance"]["method"] == "PageSpeed Insights speed score"
    assert doc["field_data"][0]["error"].startswith("too few real visitors") and doc["field_data"][1]["p75"]


def _gzipped(answer):
    return 200, {"Content-Type": "application/json", "Content-Encoding": "gzip"}, gzip.compress(json.dumps(answer).encode())


def test_a_malformed_answer_is_an_error_on_that_page(serve, monkeypatch):
    broken = {**LHR, "categories": {**LHR["categories"], "performance": "fast"}}
    api = serve(lambda b: {"/psi": _gzipped({"lighthouseResult": broken}),
                           "/crux-list": _gzipped({"record": {"metrics": []}}),
                           "/crux-word": _gzipped({"record": {"metrics": {
                               "largest_contentful_paint": {"percentiles": {"p75": "slow"}}}}})})
    monkeypatch.setattr(psi, "ENDPOINT", api + "/psi")
    assert psi.measure_one("https://a.test/", "mobile", "", local()).error == "PageSpeed Insights' answer couldn't be read"
    for path in ("/crux-list", "/crux-word"):
        monkeypatch.setattr(crux, "ENDPOINT", api + path)
        d = crux.query("https://a.test/", "k", False, local())
        assert d.error == "the API's answer couldn't be read" and not d.p75 and d.device == "phone"


def test_an_api_error_with_a_number_in_it_passes_the_number_check(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    c = crawl(base, local(), fast=True, external=False, single=True)
    errors = [crux.FieldData(c.start, False, error="the API answered 429"),
              crux.FieldData(base, True, error="couldn't reach the API: OSError: [Errno 11001] getaddrinfo failed")]
    markdown, _, passed = report(c, None, [], Extras(field_data=errors))
    assert passed, markdown
    assert "`the API answered 429`" in markdown


def test_a_stop_starts_no_more_psi_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(psi, "fetch", lambda url, *a, **kw: calls.append(url) or Response(url, url, 0, error="reset"))
    stop = threading.Event()
    stop.set()
    assert psi.measure_one("https://a.test/", "mobile", "", local(), stop=stop).error.startswith("stopped") and not calls

    def progress(message):
        raise KeyboardInterrupt
    stop = threading.Event()
    with pytest.raises(KeyboardInterrupt):
        psi.measure(["https://a.test/"], "", local(), progress=progress, stop=stop)
    assert stop.is_set()


def test_waiting_for_psi_outlasts_its_one_second_waits_and_a_stop_keeps_the_crawl():
    c = Crawl("https://a.test/", "https://a.test", False)
    later: Future = Future()
    threading.Timer(1.5, later.set_result, [["measured"]]).start()
    assert site._speed(later, c, None) == ["measured"] and not c.incomplete

    class Interrupted(Future):
        def result(self, timeout=None):
            raise KeyboardInterrupt  # Ctrl-C lands in the wait, not in progress
    assert site._speed(Interrupted(), c, None) == [] and "before PageSpeed Insights answered" in c.incomplete


@pytest.mark.parametrize("key_from", [psi.key_from, crux.key_from])
def test_a_key_with_a_line_break_is_refused(key_from):
    with pytest.raises(ValueError, match="letters, digits") as refused:
        key_from("AIza-secret\r\nX-Injected: 1")
    assert "AIza" not in str(refused.value)
    assert key_from(" AIza_good-key ") == "AIza_good-key"

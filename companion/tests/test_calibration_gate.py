"""The calibration gate (calibration/gate.py), on made-up runs: the plan's tolerances, the score's band rule, and the
one miss allowed; and the trace-engine spike's comparison (calibration/insights.py). The harness and the spike need
Chromium and Lighthouse; the harness runs in the scheduled workflow."""
import pytest
from calibration import gate, insights
from calibration.fixtures import fixtures, png, url


def run(fcp=1000.0, lcp=2000.0, si=1500.0, tbt=100.0, cls=0.05, ttfb=100.0, tti=3000.0):
    return {"fcp": fcp, "lcp": lcp, "si": si, "tbt": tbt, "cls": cls, "ttfb": ttfb, "tti": tti}


@pytest.mark.parametrize("metric, reference, allowed", [
    ("fcp", 1000, 150), ("fcp", 3000, 300), ("lcp", 5000, 500), ("si", 1000, 250), ("si", 4000, 600),
    ("tbt", 100, 50), ("tbt", 2000, 500), ("ttfb", 100, 20), ("ttfb", 1000, 50), ("cls", 0.3, 0.01)])
def test_each_metric_allows_the_larger_of_its_share_and_its_floor(metric, reference, allowed):
    assert gate.allowance(metric, reference) == pytest.approx(allowed)


def test_medians_inside_the_lines_pass_and_tti_is_never_a_miss():
    rows = gate.compare("text", "mobile", [run(), run(fcp=1100), run(fcp=1300)],
                        [run(fcp=990), run(), run(fcp=1010, tti=9000)], [80, 79, 70], [80, 80, 80])
    by = {r.metric: r for r in rows}
    assert [r.metric for r in rows] == ["fcp", "lcp", "si", "tbt", "cls", "ttfb", "tti", "score"]
    assert by["fcp"].ours == 1100 and by["fcp"].reference == 1000 and by["fcp"].ok
    assert by["tti"].gated is False and gate.misses(rows) == []
    assert by["score"].ours == 79 and by["score"].reference == 80  # each side's representative load


def test_one_miss_passes_and_two_fail():
    rows = gate.compare("a", "mobile", [run(fcp=1200)], [run()], [80], [80])
    assert [r.metric for r in gate.misses(rows)] == ["fcp"] and gate.passed(rows)
    rows += gate.compare("b", "mobile", [run(cls=0.07)], [run()], [80], [80])
    assert not gate.passed(rows)
    assert "Gate: failed, 2 misses (1 allowed)." in gate.table(rows)
    assert "| a | mobile | fcp | 1200 | 1000 | 200 | 150 | miss |" in gate.table(rows)


def test_a_metric_one_side_lacks_is_a_miss_and_both_lacking_it_is_not():
    rows = gate.compare("x", "desktop", [run(lcp=None)], [run()], [None], [90])
    assert {r.metric for r in gate.misses(rows)} == {"lcp", "score"}
    rows = gate.compare("x", "desktop", [run(lcp=None)], [run(lcp=None)], [None], [None])
    assert gate.misses(rows) == []


@pytest.mark.parametrize("ours, reference, ok", [
    (80, 84, True), (80, 86, False), (56, 47, False),   # within 5, or not
    (86, 91, True), (48, 53, True),                     # other bands, one within 2 of the line between them
    (86, 89, True), (44, 47, True), (95, 100, True)])
def test_the_score_rule(ours, reference, ok):
    assert gate.score_ok(ours, reference) is ok
    assert gate.score_ok(reference, ours) is ok


def test_every_fixture_has_a_page_and_a_url():
    pages = fixtures(8000)
    assert len(pages) >= 17
    for name, html in pages.items():
        assert url(name, 8000).startswith("http://site.test:8000/")
        assert name == "redirect" or html.startswith("<!doctype html>")


@pytest.mark.parametrize("name, audit", [
    ("LCPDiscovery", "lcp-discovery-insight"), ("CLSCulprits", "cls-culprits-insight"), ("DOMSize", "dom-size-insight"),
    ("ModernHTTP", "modern-http-insight"), ("SlowCSSSelector", "slow-css-selector-insight"),
    ("DuplicatedJavaScript", "duplicated-javascript-insight"), ("Cache", "cache-insight")])
def test_the_trace_engines_insights_get_lighthouses_audit_ids(name, audit):
    assert insights.audit_id(name) == audit


def insight(state, **savings):
    nbytes = savings.pop("bytes", None)
    return {"state": state, "metricSavings": savings, "wastedBytes": nbytes}


def test_the_spike_compares_failing_insights_and_their_savings():
    mine = {"insights": {"render-blocking-insight": insight("fail", FCP=950, LCP=950),
                         "image-delivery-insight": insight("fail", LCP=300, bytes=1000), "cache-insight": insight("pass")}}
    theirs = {"insights": {"render-blocking-insight": insight("fail", FCP=900, LCP=900),
                           "image-delivery-insight": insight("fail", LCP=350, bytes=1050),
                           "cache-insight": insight("not applicable")}}
    c = insights.compare(mine, theirs)
    assert c["same_failing"] and not c["passed"]
    assert [(s["insight"], s["metric"], s["ok"]) for s in c["savings"]] == [
        ("image-delivery-insight", "LCP", False), ("image-delivery-insight", "bytes", True),
        ("render-blocking-insight", "FCP", True), ("render-blocking-insight", "LCP", True)]
    theirs["insights"]["image-delivery-insight"] = insight("pass")
    assert not insights.compare(mine, theirs)["same_failing"]


def test_a_fixture_with_nothing_failing_or_an_error_does_not_count():
    assert not insights.compare({"insights": {}}, {"insights": {}})["passed"]
    failing = {"insights": {"cache-insight": insight("fail")}}
    assert insights.compare(failing, failing)["passed"]
    assert not insights.compare({**failing, "error": "no page"}, failing)["passed"]


def test_the_fixture_image_is_a_png_its_size_says():
    data = png(40, 30)
    assert data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) > 40 * 30 * 3
    assert png(40, 30) is data and png(40, 30, 1) != data

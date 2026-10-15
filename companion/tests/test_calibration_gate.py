"""The calibration gate (calibration/gate.py), on made-up runs: the plan's tolerances, the score's band rule, and the
one miss allowed; and the trace-engine spike's comparison (calibration/insights.py). The harness and the spike need
Chromium and Lighthouse; the harness runs in the scheduled workflow."""
import re
import struct

import pytest
from calibration import gate, insights
from calibration.fixtures import TAG_FIXTURES, _sum, fixtures, font, plain, png, tls, url

from openppc_online.siteaudit import tags


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


def test_the_tag_pages_are_published_side_by_side_not_gated():
    text = gate.tag_table({"tags": {"answered": [run(tbt=100), run(tbt=140)], "sent": [run(tbt=300)],
                                    "reference": [run(tbt=310), run(tbt=290), run(tbt=330)]}})
    assert "| tags | tbt | 120 | 300 | 310 |" in text and "| tags | cls | 0.050 | 0.050 | 0.050 |" in text
    assert "Gate" not in text


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
    pages = fixtures(plain(8000))
    assert len(pages) >= 21 and set(TAG_FIXTURES) <= set(pages)
    for name, html in pages.items():
        assert url(name, plain(8000)).startswith("http://site.test:8000/")
        assert name == "redirect" or html.startswith("<!doctype html>")
    secure = fixtures(tls(8443, 8444))
    assert url("text", tls(8443, 8444)) == "https://site.test:8443/f/text"
    assert "https://old.test:8444/r/img" in secure["http1-host"] and "https://t1.test:8443/g/collect" in secure["tags"]


def test_the_tag_pages_send_hits_openppc_answers():
    page = fixtures(plain(8000))
    hits = re.findall(r"'(http://[^']+/(?:g/collect|b/ss/)[^']*)'", page["tags"] + page["tags-chained"])
    assert len(hits) >= 2 and all(tags.is_hit(h) for h in hits)


def test_the_font_is_a_truetype_file_whose_checksums_add_up():
    data = font()
    version, count = struct.unpack(">IH", data[:6])
    assert version == 0x10000 and count == 10
    tables = {}
    for i in range(count):
        tag, checksum, offset, length = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
        tables[tag.decode()] = (checksum, offset, length)
    assert list(tables) == sorted(tables)
    for tag, (checksum, offset, length) in tables.items():
        if tag != "head":  # its checksum is taken with checkSumAdjustment as 0
            assert _sum(data[offset:offset + length]) == checksum, tag
    assert _sum(data) == 0xB1B0AFBA


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

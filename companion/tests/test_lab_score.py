"""Lighthouse's performance score, checked against a real Lighthouse 13.5 report: every metric's score and the
category's to the digit."""
import json
from pathlib import Path

import pytest

from openppc_online.siteaudit.lab import score

LHR = json.loads((Path(__file__).parent / "fixtures" / "lhr-13.5-mobile.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("metric", sorted(score.WEIGHTS))
def test_each_metric_scores_as_lighthouse_scored_it(metric):
    audit = LHR["audits"][metric]
    assert score.metric_score(metric, "mobile", audit["numericValue"]) == audit["score"]


def test_the_weights_are_the_reports_and_the_category_score_matches():
    refs = {r["id"]: r["weight"] for r in LHR["categories"]["performance"]["auditRefs"] if r["weight"]}
    assert refs == score.WEIGHTS
    values = {m: LHR["audits"][m]["numericValue"] for m in score.WEIGHTS}
    assert score.performance(values, "mobile") == round(LHR["categories"]["performance"]["score"] * 100) == 32


@pytest.mark.parametrize("device", ["mobile", "desktop"])
def test_the_control_points_score_0_9_and_0_5(device):
    for metric, (p10, median) in score.CONTROL[device].items():
        assert score.metric_score(metric, device, p10) == 0.9
        assert score.metric_score(metric, device, median) == 0.5
        assert score.metric_score(metric, device, 0) == 1


def test_a_perfect_load_scores_100_and_the_bands_are_psis():
    assert score.performance(dict.fromkeys(score.WEIGHTS, 0), "desktop") == 100
    assert [score.band(s) for s in (100, 90, 89, 50, 49, 0)] == [
        "good", "good", "needs improvement", "needs improvement", "poor", "poor"]


def test_a_very_slow_load_scores_0():
    assert score.performance({m: 1e9 for m in score.WEIGHTS}, "mobile") == 0

from pathlib import Path

import pytest

from openppc.checkfacts import facts_for_paths
from openppc.engine.findings import classify
from openppc.engine.trace import trace
from openppc.templates import TEMPLATES, run_template

EXAMPLES = Path(__file__).parent.parent / "examples"
DATA = {"search-term-waste": "search_terms_acme.csv", "keyword-audit": "keywords_acme.csv",
        "account-read": "account_acme.json", "account-structure": "account_structure_acme.json"}


def test_search_term_waste_numbers():
    md, _, passed = run_template("search-term-waste", EXAMPLES / DATA["search-term-waste"])
    assert passed
    assert "**6 search terms spent $767.20 and never converted.**" in md
    assert "That is 15.4% of the $4,973.64 total cost" in md
    assert "$9,033.16 a year" in md


def test_the_waste_figure_ties_to_the_all_in_figure_a_number_check_uses():
    # The audit counts terms of $20 or more; a number check counts every term with no conversions. Say both.
    md, _, _ = run_template("search-term-waste", EXAMPLES / DATA["search-term-waste"])
    assert "All 7 search terms with no conversions, whatever they cost, spent $784.70." in md
    every = next(f for f in facts_for_paths([EXAMPLES / DATA["search-term-waste"]])
                 if f.label == "cost of all search terms with no conversions")
    assert round(every.value, 2) == 784.70
    assert "| water heater replacement cost | $402.80 | 2 | $201.40 |" in md       # expensive converter
    assert "| leak detection service | 6 | $47.25 | Phrase match |" in md  # worth adding


def test_account_read_classifies():
    md, _, passed = run_template("account-read", EXAMPLES / DATA["account-read"])
    assert passed
    assert "EFFICIENCY GAIN. Conversions up 20% and CPA down 20%" in md


@pytest.mark.parametrize("name", sorted(TEMPLATES))
@pytest.mark.parametrize("industry", [None, "home-services"])
def test_every_report_passes_its_own_number_check(name, industry):
    _, _, passed = run_template(name, EXAMPLES / DATA[name], industry=industry)
    assert passed


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_every_report_passes_check_mode_from_scratch(name):
    """Dogfood: run `openppc check` on our own report, with facts rebuilt from the raw file.
    Our own thresholds ($20.00 minimum cost, the 3% flat band) are settings, not account data,
    so check mode rightly cannot trace them; every other number must trace."""
    md, facts, _ = run_template(name, EXAMPLES / DATA[name], industry="home-services")
    thresholds = {f.value for f in facts if f.metric == "rule"}
    claims, contradictions = trace(md, facts_for_paths([EXAMPLES / DATA[name]], "home-services"))
    assert [c for c in claims if c.verdict != "traced" and c.value not in thresholds] == []
    assert contradictions == []


def test_findings_rules():
    base = dict(cs=1000, ps=1000, ci=10000, pi=10000, cc=500, pc=500)
    assert classify(dict(base, cv=0, pv=0))[0].startswith("NO TRACKED CONVERSIONS")
    assert classify(dict(base, cv=5, pv=8))[0].startswith("SAMPLE TOO SMALL")
    assert classify(dict(base, cs=1500, cv=40, pv=60))[0].startswith("OVER-EXPANSION")

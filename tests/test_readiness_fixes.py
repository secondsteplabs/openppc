"""What the readiness test (4 Oct 2026) found, pinned so it cannot come back.

The checker on real AI-written audits: compact formats read right, sums of the rows a sentence names,
match-type groups, "this term", targets and forecasts marked "can't check", and no accusation when the
row is only implied. The engine: A$ money, digits inside search terms, the 90% rule, European numbers,
Google's Total rows, day-first dates.
"""
import json

import pytest

from openppc import webapi
from openppc.checkfacts import facts_for_paths
from openppc.engine.trace import trace
from openppc.facts import Fact
from openppc.ingest import load_report
from openppc.templates import run_template_book

ACME = "examples/search_terms_acme.csv"
KEYWORDS = "examples/keywords_acme.csv"


@pytest.fixture(scope="module")
def acme():
    return facts_for_paths([ACME])


def verdicts(text, facts):
    return [(c.written, c.verdict) for c in trace(text, facts)[0]]


@pytest.mark.parametrize("line", [
    "- **Plumber near me** (Exact): $1,361 / 31 conversions / $43.90 CPA.",
    "- **plumbing services** (phrase): 168 clicks, $1,008.00, 22 conversions, $45.82 CPA",
    "- **Water heater prices**: $331 / 7 conv / $47.23 CPA (12.07% conv rate).",
])
def test_compact_formats_trace_every_number(acme, line):
    assert {v for _, v in verdicts(line, acme)} == {"traced"}, verdicts(line, acme)


def test_sums_of_the_rows_a_sentence_names(acme):
    text = ('A softer leak: "cheap water heater" and "water heater replacement cost" cost $498.80 for 3 '
            "conversions ($166.27 each).")
    assert {v for _, v in verdicts(text, acme)} == {"traced"}, verdicts(text, acme)
    wrong = text.replace("$498.80", "$598.80")
    assert ("$598.80", "not in data") in verdicts(wrong, acme)


def test_these_three_refers_back_to_the_rows_just_named(acme):
    text = ("- **plumber near me** (exact): 31 conversions\n- **plumbing services** (phrase): 22 conversions\n"
            "- **water heater prices** (phrase): 7 conversions\n\n"
            "These three keywords deliver 60 of 85 conversions (70.6%) on 54.3% of spend, at $44.99 CPA.")
    assert {v for _, v in verdicts(text, acme)} == {"traced"}, verdicts(text, acme)


def test_match_types_are_groups(acme):
    text = "Broad: $1,886.50 (37.9% of spend) for 16 conversions (18.8%), at $117.91 CPA."
    assert {v for _, v in verdicts(text, acme)} == {"traced"}, verdicts(text, acme)
    kw = facts_for_paths([KEYWORDS])
    table = ("| Group | Spend | Conversions | Cost/conv. |\n|---|---|---|---|\n"
             "| 5 exact/phrase keywords | $3,173.94 (59%) | 70 (85%) | $45.34 |")
    assert {v for _, v in verdicts(table, kw)} == {"traced"}, verdicts(table, kw)


def test_all_terms_that_never_converted(acme):
    text = "**Verdict:** $784.70 (15.8% of spend) went to seven queries that never converted, 113 clicks in all."
    assert {v for _, v in verdicts(text, acme)} == {"traced"}, verdicts(text, acme)


def test_this_term_refers_to_the_row_named_just_before(acme):
    text = ("### Secondary Bleed: $402.80 on Water Heater Replacement Cost\n\n"
            "This term generated only 2 conversions at $201.40 each.")
    assert {v for _, v in verdicts(text, acme)} == {"traced"}, verdicts(text, acme)


@pytest.mark.parametrize("text", [
    "Annualized, that is about $9,400 of waste if July is typical.",
    "Raise the budget by 35% on the best terms.",
    "Blocking them cuts CPA from $58.51 to $49.28.",
    "Keywords under 60 clicks are directional only.",
])
def test_targets_and_forecasts_are_not_failures(acme, text):
    claims, _ = trace(text, acme)
    assert not [c for c in claims if c.verdict in ("mismatch", "not in data")], [(c.written, c.verdict) for c in claims]
    assert any(c.verdict == "can't check" for c in claims)


def test_the_headline_never_counts_what_cannot_be_checked(tmp_path):
    audit = tmp_path / "audit.md"
    audit.write_text("The account spent $4,973.64. Annualized, that is about $59,000 if July is typical.\n")
    res = json.loads(webapi.check(audit.read_text(), json.dumps([ACME])))
    assert res["counts"]["traced"] == 1 and res["counts"]["cant_check"] == 1
    assert res["counts"]["mismatch"] == 0 and res["counts"]["not_in_data"] == 0
    assert "can't be checked from an export" in res["markdown"]


def test_wrong_numbers_are_still_caught(acme):
    for text in ("The account spent $5,500 in July.", "plumbing services cost $1,108.00.",
                 "Seven terms took 140 clicks and never converted."):
        assert any(v in ("mismatch", "not in data") for _, v in verdicts(text, acme)), (text, verdicts(text, acme))


def test_no_accusation_when_the_row_is_only_implied(acme):
    # "this" carries the term from the line before, but a guess is never grounds to call a number a mismatch
    text = "### plumber jobs hiring\n\nAt this account's 11.6% conversion rate, it would need far more clicks."
    assert ("11.6%", "mismatch") not in verdicts(text, acme)


def test_another_rows_figure_is_flagged_without_accusing():
    facts = [Fact("conversion rate of 'brand'", 14.2, "pct", "cvr", "Brand"),
             Fact("conversion rate of 'brightpath academy'", 15.71, "pct", "cvr", "brightpath academy")]
    claims, _ = trace("- BrightPath brand at 15.7% conversion rate.", facts)
    assert claims[0].verdict == "not in data" and "14.2%" in claims[0].detail  # what the named row really has


@pytest.mark.parametrize("written, value", [("A$1,234.50", 1234.5), ("CA$88.10", 88.1), ("747.71 JPY", 747.71),
                                            ("Rs 1,500", 1500.0), ("INR 2,999", 2999.0)])
def test_money_written_with_letters_or_codes(written, value):
    facts = [Fact("cost of the account", value, "money", "cost")]
    assert verdicts(f"The account's cost was {written}.", facts) == [(written, "traced")]


def test_quoted_names_count_at_any_length():
    short = [Fact("cost per conversion of '日本'", 585.68, "money", "cpa", "日本")]
    assert verdicts("“日本” converts, at £585.68 each.", short) == [("£585.68", "traced")]
    digits = [Fact("cost of '24 hour 190'", 33.0, "money", "cost", "24 hour 190")]
    assert verdicts("“24 hour 190” spent $33.00.", digits) == [("$33.00", "traced")]  # 24 and 190 are its name


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


HEADER = "Search term,Match type,Added/Excluded,Campaign,Ad group,Campaign type,Clicks,Impr.,Currency code,Cost,Conversions"


def test_aud_accounts_pass_their_own_check(tmp_path):
    rows = [f"24 hour plumber {k},Broad match,None,Search,Core,Search,{10 + k},{100 + k},AUD,{40 + k}.50,{k % 3}"
            for k in range(30)]
    p = _write(tmp_path, "aud.csv", "Search terms report\nJuly 1, 2026 - July 31, 2026\n" + HEADER + "\n" + "\n".join(rows))
    _, _, passed = run_template_book("search-term-waste", str(p))
    assert passed


def test_the_ninety_percent_bar_is_always_a_fact(tmp_path):
    rows = ["drain cleaning,Exact match,None,Search,Core,Search,40,400,USD,180.00,6",
            "faucet parts,Exact match,None,Search,Core,Search,2,30,USD,8.00,0"]
    p = _write(tmp_path, "small.csv", "Search terms report\nJuly 1, 2026 - July 31, 2026\n" + HEADER + "\n" + "\n".join(rows))
    md, _, passed = run_template_book("search-term-waste", str(p))
    assert "90% is the bar" in md and passed


def test_european_numbers_read_right(tmp_path):
    rows = ['drain cleaning;Exact match;None;Search;Core;Search;1.212;5.100;EUR;1.361,04;31',
            'faucet parts;Exact match;None;Search;Core;Search;9;80;EUR;25,50;0']
    p = _write(tmp_path, "eu.csv", "Search terms report\nJuly 1, 2026 - July 31, 2026\n" + HEADER.replace(",", ";")
               + "\n" + "\n".join(rows))
    rep = load_report(str(p))
    assert [r["cost"] for r in rep.rows] == [1361.04, 25.5] and rep.rows[0]["clicks"] == 1212


def test_mixed_number_styles_are_refused(tmp_path):
    rows = ["drain cleaning,Exact match,None,Search,Core,Search,12,51,EUR,\"1,361.04\",3",
            "faucet parts,Exact match,None,Search,Core,Search,9,80,EUR,\"25,50\",0"]
    p = _write(tmp_path, "mixed.csv", "Search terms report\n" + HEADER + "\n" + "\n".join(rows))
    with pytest.raises(ValueError, match="mix two styles"):
        load_report(str(p))


def test_total_rows_are_skipped_but_a_term_called_total_is_kept(tmp_path):
    rows = ["total gym repair,Exact match,None,Search,Core,Search,5,50,USD,25.00,1",
            "drain cleaning,Exact match,None,Search,Core,Search,40,400,USD,180.00,6",
            "Total: Account,,,,,,45,450,USD,205.00,7", "Total: Search,,,,,,45,450,USD,205.00,7"]
    p = _write(tmp_path, "t.csv", "Search terms report\n1 July 2026 - 31 July 2026\n" + HEADER + "\n" + "\n".join(rows))
    rep = load_report(str(p))
    assert [r["search_term"] for r in rep.rows] == ["total gym repair", "drain cleaning"]
    assert rep.days == 31  # a day-first date line is read too


def test_other_languages_get_a_clear_reason(tmp_path):
    p = _write(tmp_path, "de.csv", "Suchbegriff,Klicks,Kosten\nabfluss,3,9.00\n")
    with pytest.raises(ValueError, match="switch it to English"):
        load_report(str(p))

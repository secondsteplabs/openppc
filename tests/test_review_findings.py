"""The four findings from the outside code review, each pinned so it cannot come back.

1. Waste is judged per search term, not per row of Google's export.
2. A row's figure backs a number only when the text names that row.
3. Small whole numbers are checked when they count clicks, conversions or impressions.
4. Thresholds and benchmarks follow the export's currency.
"""
import json
import random
import re

from openppc import webapi
from openppc.checkfacts import facts_for_paths
from openppc.engine.trace import trace
from openppc.facts import Fact
from openppc.ingest import load_report
from openppc.templates import search_term_waste

HEADER = "Search term,Match type,Added/Excluded,Campaign,Ad group,Campaign type,Clicks,Impr.,Currency code,Cost,Conversions"


def _export(tmp_path, rows, currency="USD", name="terms.csv"):
    lines = ["Search terms report", "July 1, 2026 - July 31, 2026", HEADER]
    for term, campaign, kind, clicks, cost, conversions in rows:
        lines.append(f"{term},Exact match,None,{campaign},Core,{kind},{clicks},{clicks * 10},{currency},{cost},{conversions}")
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _audit(path, **kw):
    out, book = search_term_waste.run(load_report(str(path)), **kw)
    return "\n".join(out), book


def test_a_term_that_converts_on_another_row_is_never_waste(tmp_path):
    path = _export(tmp_path, [
        ("drain cleaning", "Search - Drains", "Search", 10, 30.0, 0),   # $30, no conversion here...
        ("drain cleaning", "Search - Plumbing", "Search", 6, 18.0, 2),   # ...but it converts in another campaign
        ("faucet parts", "Search - Plumbing", "Search", 9, 25.0, 0),
    ])
    text, book = _audit(path)
    flagged = {r["term"] for r in book.cards["waste"]}
    assert flagged == {"faucet parts"}
    assert "**1 search term spent $25.00 and never converted.**" in text


def test_a_term_split_across_rows_is_judged_on_its_total(tmp_path):
    path = _export(tmp_path, [
        ("pipe repair cost", "Search - Plumbing", "Search", 4, 12.0, 0),        # $12 + $11: each row is under $20,
        ("pipe repair cost", "PMax - Plumbing", "Performance Max", 3, 11.0, 0),  # the term is not
        ("water heater", "Search - Plumbing", "Search", 30, 90.0, 3),
    ])
    text, book = _audit(path)
    assert [(r["term"], r["cost"]) for r in book.cards["waste"]] == [("pipe repair cost", "$23.00")]
    assert "### In both Search and automated campaigns" in text
    assert "Of that, $12.00 is in Search campaigns and $11.00 in Performance Max" in text


def test_the_checker_backs_a_term_by_its_total_and_by_each_row(tmp_path):
    path = _export(tmp_path, [("pipe repair cost", "Search - Plumbing", "Search", 4, 12.0, 0),
                              ("pipe repair cost", "PMax - Plumbing", "Performance Max", 3, 11.0, 0),
                              ("water heater", "Search - Plumbing", "Search", 30, 90.0, 3)])
    facts = facts_for_paths([path])
    claims, _ = trace("'pipe repair cost' cost $23.00 in total: $12.00 in Search and $11.00 in Performance Max.", facts)
    assert [c.verdict for c in claims] == ["traced", "traced", "traced"]


def test_an_unnamed_rows_figure_does_not_trace():
    sample = "examples/search_terms_acme.csv"
    facts = facts_for_paths([sample])
    named, _ = trace("'plumbing services' cost $1,008.00.", facts)
    unnamed, _ = trace("One search term cost $1,008.00.", facts)
    assert named[0].verdict == "traced"
    assert unnamed[0].verdict == "can't check" and "doesn't name" in unnamed[0].detail  # never traced


def test_made_up_numbers_only_ever_trace_to_account_figures():
    """The reviewer's case: invented numbers that happen to equal some row's figure. Anything still traced
    must be an account-level figure, which a careful reader can see in the "traced to" column."""
    random.seed(7)
    lines = []
    for _ in range(60):
        kind = random.choice(["money", "round", "clicks", "pct"])
        if kind == "money":
            lines.append(f"- The account spent ${random.uniform(25, 900):,.2f} on terms that never converted.")
        elif kind == "round":
            lines.append(f"- Roughly ${random.randint(2, 40) * 50:,} went to low-intent searches.")
        elif kind == "clicks":
            lines.append(f"- Those searches drew {random.randint(13, 400)} clicks last month.")
        else:
            lines.append(f"- The click-through rate was {random.uniform(1, 12):.1f}% across these terms.")
    claims, _ = trace("\n".join(lines), facts_for_paths(["examples/search_terms_acme.csv"]))
    traced = [c for c in claims if c.verdict == "traced"]
    assert traced and not [c.detail for c in traced if re.search(r"'[^']+'", c.detail)]  # never "cost of 'a term'"


def test_small_counts_are_checked_when_they_say_what_they_count():
    facts = facts_for_paths(["examples/search_terms_acme.csv"])
    claims, _ = trace("'plumbing services' got 7 conversions.", facts)  # it got 22
    assert [c.written for c in claims] == ["7"] and claims[0].verdict != "traced"
    right, _ = trace("'plumbing services' got 22 conversions, and the account 9 in total.", facts)
    assert right[0].verdict == "traced"
    for text in ("Here are the top 5 search terms.", "Step 3: add the negatives.", "These terms got 3 conversions."):
        assert trace(text, facts)[0] == [], text  # list numbers, steps and unnamed groups stay skipped


def test_a_rupee_account_gets_a_rupee_threshold_and_no_dollar_benchmarks(tmp_path):
    path = _export(tmp_path, [("drain cleaning", "Search - Drains", "Search", 40, 1800.0, 0),
                              ("faucet parts", "Search - Plumbing", "Search", 9, 900.0, 0),
                              ("water heater", "Search - Plumbing", "Search", 120, 9000.0, 6)], currency="INR")
    text, book = _audit(path, industry="home-services")
    assert "each one cost at least ₹1,500.00" in text
    assert {r["term"] for r in book.cards["waste"]} == {"drain cleaning"}  # ₹900 is under the rupee threshold
    assert "averages are in US dollars, so cost per click and cost per conversion are left out" in text
    bench = text.split("## Against the", 1)[1].split("## How this was computed", 1)[0]
    assert "| CPC |" not in bench and "| Cost per conversion |" not in bench and "| CTR |" in bench
    info = json.loads(webapi.inspect_file(str(path)))
    assert info["min_cost"] == 1500 and info["currency_sign"] == "₹"


def test_an_unfamiliar_currency_says_which_threshold_it_used(tmp_path):
    path = _export(tmp_path, [("drain cleaning", "Search - Drains", "Search", 40, 50.0, 0)], currency="XYZ")
    text, _ = _audit(path)
    assert re.search(r"no default waste threshold for XYZ, so it used 20\.00 XYZ", text)


def test_a_threshold_the_user_sets_always_wins(tmp_path):
    path = _export(tmp_path, [("drain cleaning", "Search - Drains", "Search", 40, 400.0, 0)], currency="INR")
    text, book = _audit(path, min_cost=300)
    assert "each one cost at least ₹300.00" in text and book.cards["waste_total"] == 1


def test_a_table_row_names_its_row_even_when_the_name_is_short():
    facts = [Fact('number of search terms containing "got"', 47, "count", "terms", "got"),
             Fact('cost of search terms containing "got"', 18.81, "money", "cost", "got")]
    markdown = "| Word or phrase | Search terms | Cost |\n|---|---|---|\n| got | 47 | $18.81 |"
    pdf_line = "got | 47 | $18.81 |"
    for text in (markdown, pdf_line):
        assert [c.verdict for c in trace(text, facts)[0]] == ["traced", "traced"], text

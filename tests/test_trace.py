from pathlib import Path

from openppc.checkfacts import facts_for_paths
from openppc.engine.trace import trace
from openppc.facts import Fact

FACTS = [
    Fact("cost of the account", 1361.04, "money", "cost"),
    Fact("clicks of 'free plumbing estimate'", 41, "count", "clicks", "free plumbing estimate"),
    Fact("wasted cost as a share of total cost", 16.78, "pct", "cost"),
]


def verdicts(text):
    claims, _ = trace(text, FACTS)
    return [(c.written, c.verdict) for c in claims]


def test_matches_at_the_precision_written():
    assert verdicts("We spent $1.4k, exactly $1,361.04, not $1,500.") == [
        ("$1.4k", "traced"), ("$1,361.04", "traced"), ("$1,500", "not in data")]


def test_percent_rounding():
    assert verdicts("Waste is 17% of spend, or 16.8% to be precise.") == [("17%", "traced"), ("16.8%", "traced")]


def test_right_number_wrong_metric():
    assert verdicts("'free plumbing estimate' drove 41 conversions.") == [("41", "mismatch")]
    assert verdicts("'free plumbing estimate' drove 41 clicks.") == [("41", "traced")]


def test_table_columns_give_context():
    table = "| Search term | Conversions |\n|---|---|\n| free plumbing estimate | 41 |"
    assert verdicts(table) == [("41", "mismatch")]


def test_skips_list_markers_small_numbers_years_and_dates():
    assert verdicts("1. Top 5 fixes for July 31, 2026") == []


def test_and_hands_the_next_metric_its_own_number():
    facts = FACTS + [Fact("CTR of the account", 7.43, "pct", "ctr"),
                     Fact("cost per conversion of the account", 58.51, "money", "cpa"),
                     Fact("clicks of the account", 732, "count", "clicks"),
                     Fact("conversions of the account", 85, "count", "conversions")]
    claims, _ = trace("CTR was 7.43% and cost per conversion $58.5. It got 732 clicks and 85 conversions.", facts)
    assert [(c.written, c.verdict) for c in claims] == [
        ("7.43%", "traced"), ("$58.5", "traced"), ("732", "traced"), ("85", "traced")]


def test_a_dollar_figure_is_never_a_click_count():
    # From a real export: "clicks" sat nearer to the dollar figure than "spent" did.
    # "41" is only one search term's clicks, and the sentence is about the account: chance, so not traced
    claims = verdicts("The account spent about $1.4k on search terms, $1,361.04 exactly, for 41 clicks.")
    assert claims[:2] == [("$1.4k", "traced"), ("$1,361.04", "traced")] and claims[2][0] == "41"
    assert claims[2][1] != "traced"


def test_a_named_row_only_counts_for_metrics_it_has():
    # From a real export: the brand is also a search term, but no search term has a figure in days.
    facts = [Fact("days in the date range", 30, "count", "days"),
             Fact("CTR of 'pipewell plumbing'", 31.5, "pct", "ctr", "pipewell plumbing")]
    claims, _ = trace("# Pipewell Plumbing Google Ads audit, last 30 days", facts)
    assert [(c.written, c.verdict, c.detail) for c in claims] == [("30", "traced", "days in the date range")]


def test_a_rows_own_figure_on_the_wrong_metric_is_still_a_mismatch():
    facts = FACTS + [Fact("conversions of 'free plumbing estimate'", 0, "count", "conversions", "free plumbing estimate")]
    claims, _ = trace('"free plumbing estimate" drove 41 conversions.', facts)
    assert [(c.written, c.verdict) for c in claims] == [("41", "mismatch")]


def test_a_coincidence_with_an_unnamed_row_is_not_a_mismatch():
    # From a real export: "$18" rounds to the cost of one word's terms, which the sentence never mentions.
    facts = [Fact('cost of search terms containing "brookfield"', 17.74, "money", "cost", "brookfield"),
             Fact("account cost per conversion", 24.60, "money", "cpa"),
             Fact("clicks of the account", 318, "count", "clicks")]
    claims, _ = trace("Cost per conversion dropped from $18 to $24.60. The terms drove 318 conversions.", facts)
    assert [(c.written, c.verdict) for c in claims] == [
        ("$18", "can't check"), ("$24.60", "traced"), ("318", "mismatch")]  # $18 is the earlier, unexported value


def test_numbers_inside_code_are_identifiers_not_claims():
    assert verdicts("Source: `search_terms_2026-07-01_to_07-31.csv` shows $1,361.04 spent.") == [
        ("$1,361.04", "traced")]


def test_contradiction():
    _, contradictions = trace("Conversion rate fell from 9% to 14% after the change.", FACTS)
    assert len(contradictions) == 1
    _, fine = trace("Conversion rate rose from 9% to 14% after the change.", FACTS)
    assert fine == []


ACME = facts_for_paths([Path(__file__).parent.parent / "examples" / "search_terms_acme.csv"])


def acme(text):
    claims, _ = trace(text, ACME)
    return [(c.written, c.verdict) for c in claims]


def test_european_decimals_are_one_number():
    assert acme("The account's cost per conversion is €58,51.") == [("€58,51", "traced")]
    assert acme("Total cost was $4.973,64 this month.") == [("$4.973,64", "traced")]
    assert acme("Total cost was $4,973.64 and 732 clicks.") == [("$4,973.64", "traced"), ("732", "traced")]


def test_a_range_holds_when_the_real_figure_falls_inside_it():
    assert acme("The account's average CPC is $5–$7.") == [("$5", "traced"), ("$7", "traced")]
    assert acme("The account's CTR sits between 7% and 8%.") == [("7%", "traced"), ("8%", "traced")]
    assert acme("The account's CTR is 7–8%.") == [("7", "traced"), ("8%", "traced")]  # the 7 is a percentage too
    claims, _ = trace("The account's average CPC is $8–$9.", ACME)
    assert [c.verdict for c in claims] == ["not in data"] * 2 and claims[0].detail == "no: the CPC of the account is $6.79"
    claims, _ = trace("The account cost ₹6–7k last month.", [Fact("cost of the account", 6500, "money", "cost")])
    assert [c.verdict for c in claims] == ["traced"] * 2  # the k is for both ends


def test_a_range_is_never_traced_on_loose_grounds():
    assert {v for _, v in acme("Expect a CPC of $5 to $7 after the change.")} == {"can't check"}  # a forecast
    keywords = facts_for_paths([Path(__file__).parent.parent / "examples" / "keywords_acme.csv"])
    claims, _ = trace("Your top two (plumber near me and plumbing services phrase) convert at 9–14%.", keywords)
    assert {c.verdict for c in claims} == {"can't check"}  # plumber near me converts at 14.6%, outside it
    assert "plumber near me' is 14.6%, outside this range" in claims[0].detail
    assert acme("Conversion rate fell from 9% to 14%.") == [("9%", "can't check"), ("14%", "not in data")]  # a change


def test_a_minus_sign_stays_with_its_number():
    assert [w for w, _ in acme("Spend changed by -$0.00, and CPC by −$0.12.")] == ["-$0.00", "−$0.12"]
    assert [w for w, _ in acme("The account's average CPC is $5-$7.")] == ["$5", "$7"]  # a dash between two numbers


def test_a_waste_figure_over_a_slice_is_never_compared_with_all_of_it():
    # brand left out, one campaign type: an export can't rebuild the slice, so the figure can't be checked
    for text in ("Excluding brand terms, zero-conversion search terms cost $751.70.",
                 "Non-brand search terms with zero conversions cost $751.70.",
                 "## Non-brand waste\nSearch terms with zero conversions cost $751.70.",
                 "In Search campaigns, terms with zero conversions cost $751.70."):
        assert acme(text) == [("$751.70", "can't check")], text
    assert acme("You wasted $751.70 on search terms with zero conversions.") == [("$751.70", "not in data")]
    assert acme("You wasted $784.70 on search terms with zero conversions.") == [("$784.70", "traced")]


def test_magnitudes_in_words_and_ranges_with_k():
    facts = [Fact("cost of the account", 2700, "money", "cost")]
    assert verdicts_of("The account cost $2.5k to $3k.", facts) == [("$2.5k", "traced"), ("$3k", "traced")]
    assert verdicts_of("The account cost $2.7 thousand.", facts) == [("$2.7 thousand", "traced")]


def verdicts_of(text, facts):
    claims, _ = trace(text, facts)
    return [(c.written, c.verdict) for c in claims]


def test_a_one_word_name_is_a_row_only_when_the_text_points_at_it():
    # Real accounts have one-word search terms ("plumbing"); in an audit the same word is usually a theme
    facts = [Fact("cost of the account", 5146.84, "money", "cost"),
             Fact("cost of 'plumbing'", 90.0, "money", "cost", "plumbing", "row"),
             Fact("cost of 'Brand'", 2290.0, "money", "cost", "Brand", "group")]
    assert verdicts_of("Plumbing searches spent $1,523.20 in total.", facts) == [("$1,523.20", "can't check")]
    assert verdicts_of("The search term plumbing spent $90.00.", facts) == [("$90.00", "traced")]
    assert verdicts_of("“plumbing” spent $75.00 with no conversions.", facts) == [("$75.00", "not in data")]
    assert verdicts_of("- **Brand:** ₹2,290 in July.", facts) == [("₹2,290", "traced")]  # a line's label
    assert verdicts_of("The Brand campaign spent $2,290.", facts) == [("$2,290", "traced")]


def test_campaign_types_have_their_own_totals():
    # "Performance Max campaigns took $615.50": a campaign type's spend is a figure an export holds
    import datetime as dt
    from openppc.checkfacts import facts_for_report
    from openppc.ingest.google_ads_csv import Report
    rows = [{"search_term": "plumber near me", "campaign": "Core", "campaign_type": "Search", "clicks": 100,
             "impressions": 1000, "cost": 600.0, "conversions": 10},
            {"search_term": "water heater", "campaign": "PMax All", "campaign_type": "Performance Max", "clicks": 60,
             "impressions": 2000, "cost": 410.0, "conversions": 1},
            {"search_term": "drain repair", "campaign": "PMax All", "campaign_type": "Performance Max", "clicks": 30,
             "impressions": 900, "cost": 205.5, "conversions": 0},
            {"search_term": "plumber salary", "campaign": "Jobs", "campaign_type": "Search", "clicks": 8, "impressions": 90,
             "cost": 50.0, "conversions": 0}]
    report = Report(rows=rows, columns={"search_term", "campaign", "campaign_type", "clicks", "impressions", "cost",
                                        "conversions"},
                    source="t.csv", start=dt.date(2026, 7, 1), end=dt.date(2026, 7, 31), currency="USD")
    facts = facts_for_report(report)
    assert verdicts_of("Those Performance Max campaigns took $615.50 and drove only 1 lead.", facts)[0] == ("$615.50", "traced")
    claims, _ = trace("PMax took $1,000.00.", facts)
    assert claims[0].verdict == "not in data" and claims[0].detail.endswith("its cost is $615.50")
    assert verdicts_of("Search campaigns spent $700.00.", facts) == [("$700.00", "not in data")]  # really $650.00
    assert verdicts_of("PMax wasted $205.50 on terms that never converted.", facts) == [("$205.50", "traced")]  # our template's
    assert verdicts_of("PMax wasted $150.00 on terms that never converted.", facts) == [("$150.00", "can't check")]  # a slice
    assert verdicts_of("The search terms report shows $1,265.50 spent.", facts)[0][1] == "traced"  # "search" alone is no name
    # one PMax campaign: "the PMax campaign" is all of it; two Search campaigns: "the Search campaign" is one of them
    assert verdicts_of("The PMax campaign took $1,000.00.", facts) == [("$1,000.00", "not in data")]
    assert verdicts_of("The Search campaign spent $600.00.", facts) == [("$600.00", "can't check")]


def test_comparisons_reports_and_parts_are_read_for_what_they_are():
    kw = facts_for_paths([Path(__file__).parent.parent / "examples" / "keywords_acme.csv"])
    # "8% more" says how two figures compare: it is not broad match's share of anything
    assert verdicts_of("Broad clicks cost 8% more ($6.78 vs. $6.28).", kw)[:2] == [("8%", "can't check"),
                                                                                 ("$6.78", "traced")]
    assert verdicts_of("Broad clicks cost only 8% more ($6.78 vs. $6.28).", kw)[0] == ("8%", "can't check")
    # "this export" is the report itself, never the campaign named before it
    assert verdicts_of("Core spent the most.\n\nAccount totals in this export: 882 clicks.", ACME) == [("882", "not in data")]
    # "5 of them" is part of a set bigger than the two campaigns named before it
    claims, _ = trace("Core and Drains spent the most.\n\nThe model is sure about 5 of them, which wasted $999.00.", ACME)
    assert [(c.written, c.verdict) for c in claims] == [("$999.00", "not in data")]

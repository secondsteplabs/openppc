"""Brand terms, Performance Max and long-tail words: lessons from the first real export, on made-up rows."""
import datetime as dt
import json
import re

from openppc.engine.trace import trace
from openppc.ingest.google_ads_csv import Report
from openppc.templates import keyword_audit, search_term_waste
from openppc.templates._common import brand_matcher


def _row(term, cost, clicks, conversions=0, kind="Search"):
    return {"search_term": term, "match_type": "Broad match", "campaign_type": kind, "clicks": clicks,
            "impressions": clicks * 10, "cost": cost, "conversions": conversions}


ROWS = [
    _row("pipewell plumbing", 40.0, 10, 2),
    _row("pipewel plumbing", 27.40, 4, 0, "Performance Max"),
    _row("same day plumber near me", 23.40, 2),
    _row("plumbing repair", 300.0, 60, 12),
    _row("diy toilet repair", 7.0, 2),
    _row("diy drain unclog", 6.5, 1),
    _row("diy faucet fix", 7.1, 1),
    _row("riverside plumbing", 25.0, 3, 0, "Performance Max"),
]


def _run(**params):
    report = Report(rows=ROWS, columns={"search_term", "match_type", "campaign_type", "clicks", "impressions",
                                        "cost", "conversions"},
                    source="test.csv", start=dt.date(2026, 7, 1), end=dt.date(2026, 7, 30), currency="USD")
    lines, book = search_term_waste.run(report, **params)
    text = "\n".join(lines)
    claims, contradictions = trace(text, book.facts)
    untraced = [(c.written, c.verdict, c.context) for c in claims if c.verdict != "traced"]
    assert not untraced and not contradictions, untraced  # every report passes its own number check
    return text


def _section(text, title):
    return text.split(title)[1].split("\n## ")[0]


def test_brand_names_and_close_misspellings_match():
    is_brand = brand_matcher("Pipewell Plumbing")
    assert is_brand("pipewell plumbing reviews") and is_brand("pipewel plumbing") and is_brand("pipewel plumbers")
    assert not is_brand("best plumbing near me") and not is_brand("cheap plumber")
    assert not brand_matcher("")("pipewell plumbing")


def test_brand_terms_are_never_waste():
    text = _run(brand="Pipewell Plumbing")
    waste = _section(text, "## Wasted spend, ranked")
    assert "pipewel plumbing" not in waste and "same day plumber near me" in waste
    assert "Brand terms are left out of the waste list" in text


def test_performance_max_is_listed_apart_from_search():
    text = _run(brand="Pipewell Plumbing")
    assert "### In Search campaigns" in text
    assert "### In Performance Max and other automated campaigns" in text
    assert "negative keywords in the campaign (up to 10,000)" in text  # Google, answer 15726455
    assert "only block Search and Shopping ads" in text


def test_words_that_never_convert_surface_the_long_tail():
    text = _run(brand="Pipewell Plumbing")
    assert "| diy | 3 |" in _section(text, "## Words that never convert")


def test_keyword_audit_spares_brand_keywords():
    rows = [{"keyword": "pipewell plumbing", "match_type": "Exact match", "clicks": 5, "impressions": 50, "cost": 30.0,
             "conversions": 0},
            {"keyword": "plumbing repair", "match_type": "Phrase match", "clicks": 50, "impressions": 500,
             "cost": 200.0, "conversions": 10},
            {"keyword": "water heater install", "match_type": "Broad match", "clicks": 8, "impressions": 80,
             "cost": 45.0, "conversions": 0}]
    report = Report(rows=rows, columns={"keyword", "match_type", "clicks", "impressions", "cost", "conversions"},
                    source="kw.csv", currency="USD")
    lines, _ = keyword_audit.run(report, brand="Pipewell Plumbing")
    text = "\n".join(lines)
    table = _section(text, "## Keywords spending without converting")
    assert "water heater install" in table and "pipewell plumbing" not in table
    assert "1 brand keyword with zero conversions is left out" in text


def _report(rows):
    report = Report(rows=rows, columns={"search_term", "match_type", "campaign_type", "clicks", "impressions", "cost",
                                        "conversions"},
                    source="test.csv", start=dt.date(2026, 7, 1), end=dt.date(2026, 7, 30), currency="USD")
    lines, book = search_term_waste.run(report)
    text = "\n".join(lines)
    claims, contradictions = trace(text, book.facts)
    assert all(c.verdict == "traced" for c in claims) and not contradictions  # the report passes its own number check
    return text


def test_the_waste_model_says_which_terms_are_proven():
    # Terms differ a lot here; one term has 150 clicks and no conversion, the others are too new to judge.
    rows = [_row("plumbing repair", 900.0, 300, 45), _row("drain cleaning", 400.0, 100, 25), _row("pipe repair", 200.0, 50, 12),
            _row("leak detection", 300.0, 80, 2), _row("water heater install", 250.0, 60, 1),
            _row("free plumbing course", 240.0, 150, 0), _row("plumber salary", 30.0, 4, 0), _row("pvc glue", 25.0, 3, 0)]
    text = _report(rows)
    assert "The waste model is at least 90% sure about 1 of them" in text and "add it as a negative." in text
    table = _section(text, "## Wasted spend, ranked")
    assert "| free plumbing course |" in table and "Chance it's bad" in table


def test_an_account_whose_terms_convert_alike_is_told_so():
    # Every term converts at 10%: a term with no conversions is most likely unlucky, however much it cost.
    rows = [_row(f"plumbing service {i}", 50.0, 100, 10) for i in range(40)] + [_row("plumber near me", 60.0, 25, 0)]
    text = _report(rows)
    assert "convert at much the same rate" in text
    assert "None of them has enough clicks for the waste model to be 90% sure" in text
    assert "The words they share are below" not in text  # this account has no shared words to point at


def test_one_term_left_over_reads_as_one():
    # One proven waste term and one too new to judge: "the other 1 has", never "the other 1 have".
    rows = [_row("plumbing repair", 900.0, 300, 45), _row("drain cleaning", 400.0, 100, 25), _row("pipe repair", 200.0, 50, 12),
            _row("leak detection", 300.0, 80, 2), _row("water heater install", 250.0, 60, 1),
            _row("free plumbing course", 240.0, 150, 0), _row("plumber salary", 30.0, 4, 0)]
    report = Report(rows=rows, columns={"search_term", "match_type", "campaign_type", "clicks", "impressions", "cost",
                                        "conversions"},
                    source="test.csv", start=dt.date(2026, 7, 1), end=dt.date(2026, 7, 30), currency="USD")
    lines, book = search_term_waste.run(report)
    everything = "\n".join(lines) + json.dumps([book.cards, book.client])  # the report, the app's cards, the client PDF
    assert "The other 1 has too few clicks" in everything and "The other 1 is too early to judge" in everything
    assert not re.search(r"The other 1 (are|have)\b", everything)

"""Facts for `openppc check`: every figure a reasonable audit of your files could cite.

For each export we register the account totals, every row, and every campaign, ad group
and match type group: cost, clicks, impressions, conversions, CTR, CPC, cost per
conversion, conversion rate, and each one's share of the total. Then we add every number
our own templates would print. Template thresholds are left out on purpose: a threshold
we chose is not a fact about your account.
"""
from dataclasses import replace

from .engine import benchmarks
from .facts import Fact, FactBook
from .ingest import load_report
from .ingest.account import is_snapshot, read_json, snapshot
from .templates import TEMPLATES, account_read, account_structure
from .templates._common import register_group, totals

ROW_KEYS = ("search_term", "keyword", "ad_group", "campaign")
GROUP_KEYS = ("campaign", "ad_group", "match_type")


def facts_for_report(report):
    book = FactBook(report.currency)
    grand = totals(report.rows)
    register_group(book, "", grand, grand)
    if report.days:
        book.count("days in the date range", report.days, "days")
    row_key = next((k for k in ROW_KEYS if report.has(k)), None)
    never_rows, word = [], ""
    if row_key:
        rows_of = {}  # Google lists a search term once per campaign, ad group and match type
        for row in report.rows:
            if row.get(row_key):
                rows_of.setdefault(" ".join(row[row_key].lower().split()), []).append(row)
        start = len(book.facts)
        for members in rows_of.values():
            name = members[0][row_key].strip()
            register_group(book, name, totals(members), grand)  # the term's total, as our reports print it
            if len(members) > 1:
                for row in members:  # and each row, as the export shows it
                    register_group(book, name, totals([row]), grand)
        book.facts[start:] = [replace(f, level="row") for f in book.facts[start:]]
        word = {"search_term": "search terms", "keyword": "keywords"}.get(row_key, row_key.replace("_", " ") + "s")
        book.count(f"{word} in this export", len(rows_of), "terms")
        never = [members for members in rows_of.values() if totals(members).conversions == 0]
        never_rows = [r for members in never for r in members]
        if never:  # what audits usually call waste: every term that never converted, whatever it cost
            zt = totals(never_rows)
            book.count(f"{word} with no conversions", len(never), "terms")
            book.money(f"cost of all {word} with no conversions", zt.cost, "cost")
            book.count(f"clicks of all {word} with no conversions", zt.clicks, "clicks")
            if grand.cost:
                book.pct(f"cost of all {word} with no conversions as a share of total cost",
                         zt.cost / grand.cost * 100, "cost")
    for key in GROUP_KEYS:
        if key != row_key and report.has(key):
            groups = {}
            for row in report.rows:
                if row.get(key):
                    groups.setdefault(row[key], []).append(row)
            start = len(book.facts)
            for name, members in groups.items():
                register_group(book, name, totals(members), grand)
                if key == "match_type" and row_key and never_rows:  # "broad match was 62% of the waste"
                    waste = totals(never_rows).cost
                    mine = totals([r for r in never_rows if r.get(key) == name]).cost
                    if waste:
                        book.pct(f"'{name}' share of the cost of {word} with no conversions", mine / waste * 100,
                                 "cost", name)
            book.facts[start:] = [replace(f, level="group") for f in book.facts[start:]]
    for template in TEMPLATES.values():
        if template.INPUT_KIND == "report" and template.accepts(report):
            _, template_book = template.run(report)
            book.facts.extend(template_book.facts)
    return [f for f in book.facts if f.metric != "rule"]


def facts_for_paths(paths, industry=None):
    facts = []
    for path in paths:
        if str(path).lower().endswith(".json"):
            raw = read_json(path)
            if is_snapshot(raw):
                _, book, _ = account_structure.evaluate(snapshot(raw, source=str(path)))
            else:
                _, book = account_read.run(account_read.load_metrics(path))
            facts += [f for f in book.facts if f.metric != "rule"]
        else:
            facts += facts_for_report(load_report(path))
    if industry:
        b = benchmarks.lookup(industry)
        facts += [Fact(f"{b['name']} average CPC", b["cpc"], "money", "cpc"),
                  Fact(f"{b['name']} average CTR", b["ctr"], "pct", "ctr"),
                  Fact(f"{b['name']} average conversion rate", b["cvr"], "pct", "cvr"),
                  Fact(f"{b['name']} average cost per lead", b["cpl"], "money", "cpa")]
    return facts

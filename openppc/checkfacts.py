"""Facts for `openppc check`: every figure a reasonable audit of your files could cite.

For each export we register the account totals, every row, and every campaign, ad group,
match type and campaign type: cost, clicks, impressions, conversions, CTR, CPC, cost per
conversion, conversion rate, and each one's share of the total. Then we add every number
our own templates would print. Template thresholds are left out on purpose: a threshold
we chose is not a fact about your account.
"""
import re
from dataclasses import replace

from .engine import benchmarks
from .engine.trace import CAMPAIGN_TYPES
from .facts import Fact, FactBook
from .ingest import load_report
from .ingest.account import is_snapshot, read_json, snapshot
from .templates import TEMPLATES, account_read, account_structure
from .templates._common import register_group, totals

ROW_KEYS = ("search_term", "keyword", "ad_group", "campaign")
SETTINGS = re.compile(r"^Settings: (.+)$", re.M)


def report_settings(text):
    """The settings an OpenPPC report says it ran with ({} for any other text), so checking that report against its
    export runs the same audit: a report made with brand terms or its own threshold has different, correct figures.
    Only settings are read from the text, never results: every number is still checked against the export."""
    title = re.search(r"^# (.+)$", text, re.M)
    line = SETTINGS.search(text)
    if "_Built by OpenPPC" not in text or not title or not line:
        return {}
    name = next((n for n, t in TEMPLATES.items() if getattr(t, "TITLE", None) == title.group(1).strip()), None)
    if name is None:
        return {}
    found = {"template": name}
    m = re.search(r"waste threshold \D*?(\d[\d,]*(?:\.\d+)?)", line.group(1))
    if m:
        found["min_cost"] = float(m.group(1).replace(",", ""))
    m = re.search(r"brand terms “([^”]{1,300})”", line.group(1))
    if m:
        found["brand"] = m.group(1)
    m = re.search(r"industry averages: ([a-z][a-z-]{1,40})", line.group(1))
    if m and m.group(1) in benchmarks.TABLE:
        found["industry"] = m.group(1)
    return found
GROUP_KEYS = ("campaign", "ad_group", "match_type")



def facts_for_report(report, settings=None):
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
    if report.has("campaign_type"):
        kinds = {}
        for row in report.rows:
            kinds.setdefault((row.get("campaign_type") or "").strip().lower(), []).append(row)
        start = len(book.facts)
        for kind, members in kinds.items():
            for name in CAMPAIGN_TYPES.get(kind, ()):
                register_group(book, name, totals(members), grand)
                if report.has("campaign"):  # "the Search campaign" is one of them when there are several
                    book.count(f"campaigns in '{name}'", len({r["campaign"] for r in members if r.get("campaign")}),
                               "campaigns", name)
        book.facts[start:] = [replace(f, level="group") for f in book.facts[start:]]
    for template in TEMPLATES.values():
        if template.INPUT_KIND == "report" and template.accepts(report):
            same = settings and settings.get("template") == template.NAME  # the report's own settings
            opts = {k: settings[k] for k in ("min_cost", "brand", "industry") if same and settings.get(k) is not None}
            _, template_book = template.run(report, **opts)
            book.facts.extend(template_book.facts)
    return [f for f in book.facts if f.metric != "rule"]


def facts_for_check(text, paths, industry=None):
    """Facts to check `text` against: the exports' figures, and when the text is an OpenPPC report, the figures
    of the same audit run with that report's settings."""
    settings = report_settings(text)
    return facts_for_paths(paths, industry or settings.get("industry"), settings)


def facts_for_paths(paths, industry=None, settings=None):
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
            facts += facts_for_report(load_report(path), settings)
    if industry:
        b = benchmarks.lookup(industry)
        facts += [Fact(f"{b['name']} average CPC", b["cpc"], "money", "cpc", currency="USD"),
                  Fact(f"{b['name']} average CTR", b["ctr"], "pct", "ctr"),
                  Fact(f"{b['name']} average conversion rate", b["cvr"], "pct", "cvr"),
                  Fact(f"{b['name']} average cost per lead", b["cpl"], "money", "cpa", currency="USD")]
    return facts

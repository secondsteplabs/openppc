"""Facts for `openppc check`: every figure a reasonable audit of your files could cite.

For each export we register the account totals, every row, and every campaign, ad group,
match type and campaign type: cost, clicks, impressions, conversions, CTR, CPC, cost per
conversion, conversion rate, and each one's share of the total. Then we add every number
our own templates would print. Template thresholds are left out on purpose: a threshold
we chose is not a fact about your account.

The rows themselves are kept as plain numbers (RowFacts) and become facts only when the
checker reads them, so an export of 250,000 search terms stays small in memory.
"""
import re
from array import array
from bisect import bisect_left, bisect_right
from dataclasses import replace

from .engine import benchmarks
from .engine.trace import CAMPAIGN_TYPES
from .facts import Fact, FactBook, FactList
from .ingest import load_report
from .ingest.account import is_snapshot, read_json, snapshot
from .templates import TEMPLATES, account_read, account_structure
from .templates._common import Totals, figures, register_group, totals

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


class RowFacts:
    """An export's search terms or keywords as plain numbers. Reading it gives the facts registering every row
    would (each term's total, then each of its rows when it has several), in the same order, but a row's facts are
    only built when read. trace asks for the rows a text names and for the figures near each of its numbers, so an
    export of 250,000 search terms never becomes three million objects."""

    def __init__(self, currency, grand):
        self.currency, self.grand = currency, grand
        self.names = []                                   # each entry's name, as the export writes it
        self.sums = [array("d") for _ in Totals._fields]  # each entry's cost, clicks, impressions, conversions
        self._first = self._columns = self._starts = None

    def add(self, name, t):
        self.names.append(name)
        for column, value in zip(self.sums, t):
            column.append(value)
        self._first = self._columns = self._starts = None

    def _figures(self, e):
        return figures(Totals(*(column[e] for column in self.sums)), self.grand)

    def _fact(self, e, figure):
        pattern, value, kind, metric = figure
        name = self.names[e]
        return Fact(pattern.format(f"'{name}'"), float(value), kind, metric, name, "row",
                    self.currency if kind == "money" else "")

    def facts(self, e):
        """Entry e's facts, in order."""
        return [self._fact(e, figure) for figure in self._figures(e)]

    def _build(self):
        """Where each entry's facts start, and every figure sorted by value within its kind and metric."""
        first, count, columns = array("q"), 0, {}
        for e in range(len(self.names)):
            first.append(count)
            figs = self._figures(e)
            for j, (_, value, kind, metric) in enumerate(figs):
                if value == value:  # never NaN: it matches nothing, and would break the sort
                    column = columns.get((kind, metric)) or columns.setdefault((kind, metric), (
                        array("d"), array("q"), array("b")))
                    column[0].append(value)
                    column[1].append(e)
                    column[2].append(j)
            count += len(figs)
        self._first, self._count, self._columns = first, count, {}
        for key, (values, entries, offsets) in columns.items():
            order = sorted(range(len(values)), key=values.__getitem__)
            self._columns[key] = (array("d", (values[i] for i in order)), array("q", (entries[i] for i in order)),
                                  array("b", (offsets[i] for i in order)))

    def __len__(self):
        if self._first is None:
            self._build()
        return self._count

    def __iter__(self):
        for e in range(len(self.names)):
            yield from self.facts(e)

    def __getitem__(self, i):
        if self._first is None:
            self._build()
        i = i + self._count if i < 0 else i
        if not 0 <= i < self._count:
            raise IndexError("fact index out of range")
        e = bisect_right(self._first, i) - 1
        return self.facts(e)[i - self._first[e]]

    def lowered(self):
        """Each name in lowercase, with the first entry that has it (a term's entries sit together)."""
        if self._starts is None:
            self._starts = {}
            for e, name in enumerate(self.names):
                self._starts.setdefault(name.lower(), e)
        return self._starts

    def named(self, names):
        """(position, fact) for every fact of the entries with these lowercase names."""
        if self._first is None:
            self._build()
        starts, out = self.lowered(), []
        for name in names:
            e = starts.get(name)
            while e is not None and e < len(self.names) and self.names[e].lower() == name:
                out += [(self._first[e] + j, f) for j, f in enumerate(self.facts(e))]
                e += 1
        return out

    def near(self, value, tol, kind, taken=frozenset(), offset=0):
        """(position, fact) for the closest figure to value within tol, one per kind and metric (any kind for a plain
        number), leaving out the positions in taken (offset + position). trace only ever keeps the closest figure of a
        kind and metric, and of figures equally close the first in order, so the others never change a verdict."""
        if self._first is None:
            self._build()
        slack = 1e-9 * max(1.0, abs(value), tol)  # the window only narrows the search; the exact test below decides
        out = []
        for (k, _), (values, entries, offsets) in self._columns.items():
            if kind != "plain" and k != kind:
                continue

            def free(j):
                return offset + self._first[entries[j]] + offsets[j] not in taken

            i = bisect_left(values, value)
            hi, lo = bisect_right(values, value + tol + slack), bisect_left(values, value - tol - slack)
            up = next((j for j in range(i, hi) if free(j)), None)  # equal values sit in order
            down = next((j for j in range(i - 1, lo - 1, -1) if free(j)), None)
            if down is not None:  # the first free one among the values equal to it
                down = next(j for j in range(bisect_left(values, values[down], 0, down + 1), down + 1) if free(j))
            best = None
            for j in (up, down):
                if j is not None and abs(values[j] - value) <= tol:
                    key = (abs(values[j] - value), self._first[entries[j]] + offsets[j])
                    best = min(best, (key, j)) if best else (key, j)
            if best:
                j = best[1]
                e = entries[j]
                out.append((self._first[e] + offsets[j], self._fact(e, self._figures(e)[offsets[j]])))
        return out



def facts_for_report(report, settings=None):
    book = FactBook(report.currency)
    grand = totals(report.rows)
    register_group(book, "", grand, grand)
    if report.days:
        book.count("days in the date range", report.days, "days")
    row_key = next((k for k in ROW_KEYS if report.has(k)), None)
    never_rows, word, head, block = [], "", book.facts, None
    if row_key:
        rows_of = {}  # Google lists a search term once per campaign, ad group and match type
        for row in report.rows:
            if row.get(row_key):
                rows_of.setdefault(" ".join(row[row_key].lower().split()), []).append(row)
        block = RowFacts(report.currency, grand)
        for members in rows_of.values():
            name = members[0][row_key].strip()
            block.add(name, totals(members))  # the term's total, as our reports print it
            if len(members) > 1:
                for row in members:  # and each row, as the export shows it
                    block.add(name, totals([row]))
        book.facts = []  # what follows the rows
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
    tail = [f for f in book.facts if f.metric != "rule"]
    if block is None:  # no search term or keyword column: book.facts is still the one list
        return FactList([tail])
    return FactList([[f for f in head if f.metric != "rule"], block, tail])


def facts_for_check(text, paths, industry=None):
    """Facts to check `text` against: the exports' figures, and when the text is an OpenPPC report, the figures
    of the same audit run with that report's settings."""
    settings = report_settings(text)
    return facts_for_paths(paths, industry or settings.get("industry"), settings)


def facts_for_paths(paths, industry=None, settings=None):
    facts = FactList()
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
    facts += industry_facts(industry)
    return facts


def industry_facts(industry):
    """An industry's published averages, which an audit may quote ("the home services average CPC of $7.85")."""
    if not industry:
        return []
    b = benchmarks.lookup(industry)
    return [Fact(f"{b['name']} average CPC", b["cpc"], "money", "cpc", currency="USD"),
            Fact(f"{b['name']} average CTR", b["ctr"], "pct", "ctr"),
            Fact(f"{b['name']} average conversion rate", b["cvr"], "pct", "cvr"),
            Fact(f"{b['name']} average cost per lead", b["cpl"], "money", "cpa", currency="USD")]

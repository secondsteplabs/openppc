"""Account read: what changed between two periods, classified by explicit rules.

Input: two exports of the same Google Ads report, one per period (say the Search terms
report for June and the one for July), or a small .json file with the account's totals
for two periods:

    {"meta": {"currency": "USD", "window": "July 2026 vs June 2026",
              "business_model": "plumbing (lead-gen)"},
     "current": {"spend": 4973.64, "impressions": 9852, "clicks": 732, "conversions": 85},
     "prior":   {"spend": 5210.00, "impressions": 11890, "clicks": 760, "conversions": 71}}

With two exports, each period's totals are the sums of its rows, and the file with the later
dates is the current period. Every direction and percentage is computed in code
(engine/findings.py). Nothing here is left for a model to work out, because that is where
models go wrong.
"""
import os
from collections import namedtuple

from ..engine import benchmarks
from ..engine.findings import CPA_BAND, FLAT, THIN_DATA, build_findings
from ..facts import FactBook
from ..ingest import load_report
from ..ingest.account import read_json
from ..ingest.google_ads_csv import GOOGLE, META
from ._common import conv_dp, period, totals

NAME = "account-read"
TITLE = "Account read: period over period"
TIER = "free"
INPUT_KIND = "metrics"
INPUT = "pair of exports, one per period (.csv), or two-period totals (.json)"
SUMMARY = ("What changed between two periods, classified by explicit rules: efficiency win, "
           "over-expansion, broken tracking, and more. Every direction is computed, never guessed.")
KEYS = ("cs", "ps", "ci", "pi", "cc", "pc", "cv", "pv")
NEEDS = ("cost", "clicks", "impressions", "conversions")
ROW_KEYS = ("search_term", "keyword", "ad_group", "campaign")
# One export, as much of it as comparing two periods needs: no rows, so a pair of big files is never held at once
Period = namedtuple("Period", "source kind platform currency start end days missing notes totals result")


def accepts(data):
    return isinstance(data, dict) and "metrics" in data


def load(paths):
    """Two-period totals from a .json file, or from two exports of the same report."""
    paths = [str(p) for p in paths]
    if len(paths) == 2:
        return from_periods([period_of(load_report(p)) for p in paths])
    if len(paths) == 1 and paths[0].lower().endswith(".json"):
        return load_metrics(paths[0])
    names = " and ".join(os.path.basename(p) for p in paths)
    raise ValueError(f"{names}: account-read compares two periods. Give it two exports of the same report, one "
                     "per period, or a two-period totals .json.")


def period_of(report):
    return Period(report.source, next((k for k in ROW_KEYS if report.has(k)), report.title or "report"),
                  report.platform, report.currency, report.start, report.end, report.days,
                  [c for c in NEEDS if not report.has(c)], list(report.notes), totals(report.rows), report.result)


def pair_problem(a, b):
    """Why two exports cannot be compared as two periods, or None when they can."""
    na, nb = os.path.basename(a.source), os.path.basename(b.source)
    for p, n in ((a, na), (b, nb)):
        if p.platform == META and "conversions" in p.missing:
            return (f"{n} has no Results it can count as conversions. In Ads Manager, add the Results and Result "
                    "indicator columns, then export it again.")
        if p.missing:
            return f"{n} has no {' or '.join(p.missing)} column, which a period-over-period read needs."
        if not (p.start and p.end):
            if p.platform == META:
                return (f"{n} has no Reporting starts and Reporting ends dates, so its period is unknown. Export it "
                        "again with those columns.")
            return (f"{n} has no date range above its header, so its period is unknown. Download it again "
                    "without editing it.")
    if (a.kind, a.platform) != (b.kind, b.platform):
        return f"{na} and {nb} are different reports. Compare two exports of the same report."
    if a.currency != b.currency:
        return f"{na} is in {a.currency} and {nb} in {b.currency}. Compare two exports in the same currency."
    if a.result and b.result and a.result != b.result:
        return (f"{na} counts {a.result} as its Results and {nb} counts {b.result}, so their conversions can't be "
                "compared. Export both periods with the same result type.")
    first, second = sorted((a, b), key=lambda p: (p.end, p.start))
    if second.start <= first.end:
        return f"{na} and {nb} cover overlapping dates. Export one period per file."
    return None


def from_periods(periods):
    problem = pair_problem(*periods)
    if problem:
        raise ValueError(problem)
    prior, current = sorted(periods, key=lambda p: (p.end, p.start))
    p, c = prior.totals, current.totals
    m = {"cs": c.cost, "ps": p.cost, "ci": c.impressions, "pi": p.impressions,
         "cc": c.clicks, "pc": p.clicks, "cv": c.conversions, "pv": p.conversions}
    return {"metrics": {k: float(v) for k, v in m.items()}, "meta": {"currency": current.currency},
            "source": current.source, "prior_source": prior.source, "platform": current.platform,
            "notes": list(dict.fromkeys(n for x in (current, prior) for n in x.notes)),
            "periods": [("current", current), ("prior", prior)]}


def load_metrics(path):
    d = read_json(path)
    try:
        if "current" in d and "prior" in d:
            c, p = d["current"], d["prior"]
            m = {"cs": c["spend"], "ps": p["spend"], "ci": c["impressions"], "pi": p["impressions"],
                 "cc": c["clicks"], "pc": p["clicks"], "cv": c["conversions"], "pv": p["conversions"]}
        else:
            m = {k: d[k] for k in KEYS}
        metrics = {k: float(v) for k, v in m.items()}
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"{path}: this JSON is not an account file OpenPPC reads. It needs an account snapshot "
                         "(a list of campaigns) or two-period totals (current and prior spend, impressions, "
                         "clicks and conversions).") from None
    return {"metrics": metrics, "meta": d.get("meta", {}), "source": str(path)}


def _register(book, m):
    for key, word, metric in (("s", "spend", "cost"), ("i", "impressions", "impressions"),
                              ("c", "clicks", "clicks"), ("v", "conversions", "conversions")):
        cur, prior = m["c" + key], m["p" + key]
        if key == "s":
            book.money(f"current {word}", cur, metric)
            book.money(f"prior {word}", prior, metric)
        else:
            dp = conv_dp(cur, prior) if key == "v" else 0
            book.count(f"current {word}", cur, metric, dp=dp)
            book.count(f"prior {word}", prior, metric, dp=dp)
        if prior:
            book.pct(f"{word} change", abs(cur - prior) / prior * 100, metric)
            book.pct(f"current {word} as a share of prior", cur / prior * 100, metric)
    ratios = (("CTR", "ctr", "pct", lambda s, i, c, v: c / i * 100 if i else None),
              ("CPA", "cpa", "money", lambda s, i, c, v: s / v if v else None),
              ("conversion rate", "cvr", "pct", lambda s, i, c, v: v / c * 100 if c else None),
              ("CPC", "cpc", "money", lambda s, i, c, v: s / c if c else None))
    for name, metric, kind, fn in ratios:
        cur = fn(m["cs"], m["ci"], m["cc"], m["cv"])
        prior = fn(m["ps"], m["pi"], m["pc"], m["pv"])
        add = book.money if kind == "money" else book.pct
        if cur is not None:
            add(f"current {name}", cur, metric)
        if prior is not None:
            add(f"prior {name}", prior, metric)
        if cur is not None and prior:
            book.pct(f"{name} change", abs(cur - prior) / prior * 100, metric)
    book.pct("rule: a move smaller than this is flat", FLAT * 100, "rule")
    book.pct("rule: CPA band for 'efficiency held'", CPA_BAND * 100, "rule")
    book.count("rule: thin-data threshold (conversions per period)", THIN_DATA, "rule")


def _markdown(block):
    out = []
    for line in block.splitlines():
        if line.startswith("COMPUTED FINDINGS"):
            out += ["## Period over period", ""]
        elif line.startswith("READ: "):
            out += ["", "## Read", "", line[len("READ: "):]]
        elif line.startswith("BIGGEST MOVE: "):
            out += ["", f"**Biggest move:** {line[len('BIGGEST MOVE: '):]}"]
        elif line == "FLAGS: none":
            out += ["", "## Flags", "", "None."]
        elif line == "FLAGS:":
            out += ["", "## Flags", ""]
        elif line.strip():
            out.append(line)
    return out


def run(data, industry=None, **_):
    m, meta = data["metrics"], data.get("meta", {})
    book = FactBook((meta.get("currency") or "USD").upper())
    _register(book, m)
    source = os.path.basename(data.get("source", ""))
    pair = data.get("prior_source")
    if pair:
        bits = [f"Source: `{source}` (current) and `{os.path.basename(pair)}` (prior)"]
        if data.get("platform", GOOGLE) != GOOGLE:
            bits.append(f"{data['platform']} exports (experimental)")
        bits.append(" vs ".join(f"{period(p, compact=True)} ({book.count(f'days in the {name} period', p.days, 'days')}"
                                f" days)" for name, p in data["periods"]))
    else:
        bits = [f"Source: `{source}`"]
    if meta.get("window"):
        bits.append(meta["window"])
    bits.append(f"currency {book.currency}")
    notes = data.get("notes") or []
    read = [f"_How the files were read: {'; '.join(notes)}._", ""] if notes else []
    if pair and len({p.days for _, p in data["periods"]}) > 1:
        read += ["_Note: the two periods are different lengths, so their totals are compared as they are, not "
                 "per day._", ""]
    out = [f"# {TITLE}", "", " · ".join(bits), "", *read,
           f"_Built by OpenPPC, read-only: computed from {'these files' if pair else 'this file'} alone, with no "
           "network calls._", ""]
    search = data.get("platform", GOOGLE) != META
    out += _markdown(build_findings(m, meta, search=search))
    if industry and not search:
        out += ["", "_The industry averages are for Google Ads search campaigns, so a Meta report leaves them out._"]
    elif industry:
        out += benchmarks.section(book, industry, cost=m["cs"], clicks=m["cc"],
                                  impressions=m["ci"], conversions=m["cv"], currency=book.currency)
    out += ["", "## How this was computed", "",
            f"- Every change is current minus prior, divided by prior. A move smaller than "
            f"{FLAT * 100:.0f}% is called flat.",
            "- The read is the first rule that matches, in priority order: tracking problems, small samples, "
            "then the spend, conversion and CPA patterns. The rules live in `openppc/engine/findings.py`.",
            "- A conversion is whatever this account counts as one. Seasonal businesses should compare against "
            "the same period last year, not the previous one."]
    return out, book

"""Account read: what changed between two periods, classified by explicit rules.

Input: a small .json file with the account's totals for two periods:

    {"meta": {"currency": "USD", "window": "July 2026 vs June 2026",
              "business_model": "plumbing (lead-gen)"},
     "current": {"spend": 4973.64, "impressions": 9852, "clicks": 732, "conversions": 85},
     "prior":   {"spend": 5210.00, "impressions": 11890, "clicks": 760, "conversions": 71}}

Every direction and percentage is computed in code (engine/findings.py). Nothing here
is left for a model to work out, because that is where models go wrong.
"""
import os

from ..engine import benchmarks
from ..engine.findings import CPA_BAND, FLAT, THIN_DATA, build_findings
from ..facts import FactBook
from ..ingest.account import read_json
from ._common import conv_dp

NAME = "account-read"
TITLE = "Account read: period over period"
TIER = "free"
INPUT_KIND = "metrics"
INPUT = "two-period totals (.json)"
SUMMARY = ("What changed between two periods, classified by explicit rules: efficiency win, "
           "over-expansion, broken tracking, and more. Every direction is computed, never guessed.")
KEYS = ("cs", "ps", "ci", "pi", "cc", "pc", "cv", "pv")


def accepts(data):
    return isinstance(data, dict) and "metrics" in data


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
    bits = [f"Source: `{os.path.basename(data.get('source', ''))}`"]
    if meta.get("window"):
        bits.append(meta["window"])
    bits.append(f"currency {book.currency}")
    out = [f"# {TITLE}", "", " · ".join(bits), "",
           "_Built by OpenPPC, read-only: computed from this file alone, with no network calls._", ""]
    out += _markdown(build_findings(m, meta))
    if industry:
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

"""Keyword audit: where the budget goes by keyword and match type, and what it buys.

Input: a Keywords report. Add the Quality Score column before you export if you want
the Quality Score section. Every figure below is computed from that file alone.
"""
from ..engine import benchmarks
from ..facts import FactBook
from ._common import (brand_matcher, conv_dp, esc, header, min_cost_for, need, plural, settings_line, totals,
                      val)

NAME = "keyword-audit"
TITLE = "Keyword audit"
TIER = "free"
INPUT_KIND = "report"
INPUT = "Keywords report (.csv)"
SUMMARY = ("Keywords spending without converting, budget and results by match type, "
           "and spend on low Quality Scores.")
HOW_TO_EXPORT = ("In Google Ads: Campaigns > Audiences, keywords and content > Search keywords, pick the "
                 "date range, then Download > .csv. Add the Quality Score column first for that section.")
TOP_CONVERTERS = 5


def accepts(report):
    return report.has("keyword", "clicks", "cost", "conversions")


def run(report, min_cost=None, industry=None, low_qs=4, top=25, brand=None, **_):
    need(report, "keyword", "Keywords report", HOW_TO_EXPORT)
    book = FactBook(report.currency)
    known_default = True
    if min_cost is None:
        min_cost, known_default = min_cost_for(report.currency)
    rows = [r for r in report.rows if r.get("keyword")]
    grand = totals(rows)
    out = header(book, report, TITLE)
    total_cost = book.money("total cost", grand.cost)
    min_s = book.money("minimum cost for a no-conversion flag (rule)", min_cost, "rule")
    out[4:4] = [settings_line(min_s, brand, industry), ""]  # before the "Built by OpenPPC" line
    cpa = grand.cost / grand.conversions if grand.conversions else None
    if not known_default:
        out += [f"_OpenPPC has no default threshold for {report.currency}, so it used {min_s}. "
                "Set your own with `--min-cost`._", ""]

    clicks = book.count("total clicks", grand.clicks, "clicks")
    convs = book.count("total conversions", grand.conversions, "conversions", dp=conv_dp(grand.conversions))
    line = (f"This export covers {total_cost} of cost, {clicks} {plural(grand.clicks, 'click')} and {convs} "
            f"{plural(grand.conversions, 'conversion')}")
    if cpa:
        line += f", or {book.money('account cost per conversion', cpa, 'cpa')} per conversion"
    out += ["## Summary", "", line + "."]

    is_brand = brand_matcher(brand)
    spared = [r for r in rows if not val(r, "conversions") and val(r, "cost") >= min_cost and is_brand(r["keyword"])]
    zero = sorted((r for r in rows if not val(r, "conversions") and val(r, "cost") >= min_cost
                   and not is_brand(r["keyword"])), key=lambda r: -val(r, "cost"))
    if spared:
        sn = book.count("brand keywords left out of the zero-conversion list", len(spared), "terms")
        out += ["", f"{sn} brand {plural(len(spared), 'keyword')} with zero conversions {'is' if len(spared) == 1 else 'are'} "
                    "left out below: pausing brand keywords hands those searches to competitors."]
    if zero and grand.cost:
        zt = totals(zero)
        n = book.count("keywords flagged (zero conversions, at or above the threshold)", len(zero))
        zc = book.money("cost of flagged zero-conversion keywords", zt.cost)
        share = book.pct("flagged zero-conversion cost as a share of total cost", zt.cost / grand.cost * 100, "cost")
        out += ["", f"**{n} {plural(len(zero), 'keyword')} spent {zc} with zero conversions.** "
                    f"That is {share} of total cost.",
                "", "## Keywords spending without converting", "",
                "| Keyword | Match type | Cost | Clicks | Quality Score |", "|---|---|---|---|---|"]
        for r in zero[:top]:
            kw = r["keyword"]
            c = book.money(f"cost of '{kw}'", val(r, "cost"), "cost", kw)
            k = book.count(f"clicks of '{kw}'", val(r, "clicks"), "clicks", kw)
            qs = r.get("quality_score")
            q = book.count(f"Quality Score of '{kw}'", qs, "quality", kw) if qs is not None else "--"
            out.append(f"| {esc(kw)} | {esc(r.get('match_type', ''))} | {c} | {k} | {q} |")

    if report.has("match_type") and grand.cost:
        groups = {}
        for r in rows:
            groups.setdefault(r.get("match_type") or "unknown", []).append(r)
        out += ["", "## Budget by match type", "",
                "| Match type | Cost | Share of total cost | Conversions | Cost per conversion |",
                "|---|---|---|---|---|"]
        for mt, members in sorted(groups.items(), key=lambda kv: -totals(kv[1]).cost):
            t = totals(members)
            c = book.money(f"cost of {mt}", t.cost, "cost", mt)
            s = book.pct(f"{mt} share of total cost", t.cost / grand.cost * 100, "cost", mt)
            v = book.count(f"conversions of {mt}", t.conversions, "conversions", mt, dp=conv_dp(t.conversions))
            p = book.money(f"cost per conversion of {mt}", t.cost / t.conversions, "cpa", mt) if t.conversions else "--"
            out.append(f"| {esc(mt)} | {c} | {s} | {v} | {p} |")

    scored = [r for r in rows if r.get("quality_score") is not None]
    if scored:
        low = sorted((r for r in scored if r["quality_score"] <= low_qs), key=lambda r: -val(r, "cost"))
        out += ["", "## Quality Score", ""]
        if low and grand.cost:
            lt = totals(low)
            n = book.count("keywords at or below the Quality Score threshold", len(low))
            c = book.money("cost of low Quality Score keywords", lt.cost)
            s = book.pct("low Quality Score cost as a share of total cost", lt.cost / grand.cost * 100, "cost")
            out += [f"{n} {plural(len(low), 'keyword')} with a Quality Score of {low_qs} or lower spent {c}. "
                    f"That is {s} of total cost. "
                    "Low scores usually mean paying more for the same ad position.", "",
                    "| Keyword | Quality Score | Cost | Conversions |", "|---|---|---|---|"]
            for r in low[:top]:
                kw = r["keyword"]
                q = book.count(f"Quality Score of '{kw}'", r["quality_score"], "quality", kw)
                c = book.money(f"cost of '{kw}'", val(r, "cost"), "cost", kw)
                v = book.count(f"conversions of '{kw}'", val(r, "conversions"), "conversions", kw,
                               dp=conv_dp(val(r, "conversions")))
                out.append(f"| {esc(kw)} | {q} | {c} | {v} |")
        else:
            out.append(f"No keyword has a Quality Score of {low_qs} or lower. Nothing to fix here.")

    converters = sorted((r for r in rows if val(r, "conversions")), key=lambda r: -val(r, "conversions"))
    if converters:
        out += ["", "## Top converting keywords", "",
                "| Keyword | Match type | Conversions | Cost per conversion |", "|---|---|---|---|"]
        for r in converters[:TOP_CONVERTERS]:
            kw = r["keyword"]
            v = book.count(f"conversions of '{kw}'", val(r, "conversions"), "conversions", kw,
                           dp=conv_dp(val(r, "conversions")))
            p = book.money(f"cost per conversion of '{kw}'", val(r, "cost") / val(r, "conversions"), "cpa", kw)
            out.append(f"| {esc(kw)} | {esc(r.get('match_type', ''))} | {v} | {p} |")

    if industry:
        out += benchmarks.section(book, industry, cost=grand.cost, clicks=grand.clicks,
                                  impressions=grand.impressions, conversions=grand.conversions,
                                  currency=report.currency)

    out += ["", "## How this was computed", "",
            f"- Spending without converting: zero conversions and at least {min_s} in cost.",
            f"- Low Quality Score: {low_qs} or lower, on keywords that have a score.",
            "- Totals are recomputed from the rows. The Total lines in Google's export are ignored.",
            "- A conversion is whatever this account counts as one. If that includes small actions such as "
            "page views, zero conversions means something weaker here."]
    return out, book

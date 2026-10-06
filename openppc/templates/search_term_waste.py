"""Search-term waste: the searches you paid for that never converted.

Input: a Search terms report. Every figure below is computed from that file alone and
printed only after it is registered as a fact the checker can trace.
"""
import os
import re

from ..engine import benchmarks, waste_model
from ..facts import FactBook
from ._common import (brand_matcher, conv_dp, esc, fingerprint, header, min_cost_for, month_label, need, period,
                      plural, totals, val)

NAME = "search-term-waste"
TITLE = "Search-term waste audit"
TIER = "free"
INPUT_KIND = "report"
INPUT = "Search terms report (.csv)"
SUMMARY = ("Search terms that spent money and never converted, ranked by cost, the words behind "
           "the long tail, plus expensive converters and terms worth adding as keywords.")
HOW_TO_EXPORT = ("In Google Ads: Campaigns > Insights and reports > Search terms, pick the date range, "
                 "then Download > .csv.")
EXPENSIVE = 3          # converting, but at more than this multiple of the account's cost per conversion
HARVEST_MIN = 2        # conversions needed before a search term is worth adding as a keyword
THEME_MIN_TERMS = 3    # a word counts as a theme when it shows up in at least this many search terms
THEME_MIN_COST = 5.0   # ...and those terms cost at least this much together
THEMES_SHOWN = 10
THEME_COVER = 0.8      # a phrase that carries this share of a word's cost stands in for the word
ALIKE_CLICKS = 2_000   # needing more clicks than this to be sure means the account's terms convert alike
PMAX_NEGATIVES = 10_000  # Google's cap on negative keywords per Performance Max campaign
CLIENT_TITLE = "Search-term review"  # the branded report's default title
STEP_TAGS = {"negative": "Block", "watch": "Watch", "review": "Review", "add": "Grow"}
STEP_COUNT = {1: "One step to take.", 2: "Two steps, most useful first.", 3: "Three steps, most useful first."}
LONG_NAMES = {"CPC": "Cost per click", "CTR": "Click-through rate", "Conversion rate": "Conversion rate",
              "Cost per conversion": "Cost per conversion"}
HOW_IT_COMPARES = {"CPC": ("pays less per click", "pays more per click"),
                   "CTR": ("gets clicked less often", "gets clicked more often"),
                   "Conversion rate": ("converts less often", "converts more often"),
                   "Cost per conversion": ("pays less per conversion", "pays more per conversion")}
STOPWORDS = frozenset("a an and are at best by can do does for from get how i in is it me my near of on "
                      "or the to what where who why with you your".split())


def accepts(report):
    return report.has("search_term", "clicks", "cost", "conversions")


def _cpa(row):
    conversions = val(row, "conversions")
    return val(row, "cost") / conversions if conversions else None


def _not_yet_added(row):
    return (row.get("added_excluded") or "none").strip().lower() in ("none", "")


def _automated(row):
    """Performance Max and other automated campaigns, where negatives work differently from Search."""
    return (row.get("campaign_type") or "search").strip().lower() not in ("search", "")


def _by_term(rows):
    """One row per search term. Google's report lists a term once for each campaign, ad group and match type it
    showed in, so the rows are added up before anything is judged: a term that converts on any of its rows is
    never waste, and one whose cost is split across rows is judged on its total."""
    merged = {}
    for r in rows:
        key = " ".join(r["search_term"].lower().split())
        m = merged.get(key)
        if m is None:
            m = merged[key] = {"search_term": r["search_term"].strip(), "cost": 0.0, "clicks": 0.0, "impressions": 0.0,
                               "conversions": 0.0, "search_cost": 0.0, "automated_cost": 0.0, "search_rows": 0,
                               "automated_rows": 0, "_match": [], "_type": [], "_campaign": [], "_added": []}
        for k in ("cost", "clicks", "impressions", "conversions"):
            m[k] += val(r, k)
        side = "automated" if _automated(r) else "search"
        m[side + "_cost"] += val(r, "cost")
        m[side + "_rows"] += 1
        for field, column in (("_match", "match_type"), ("_type", "campaign_type"), ("_campaign", "campaign"),
                              ("_added", "added_excluded")):
            v = (r.get(column) or "").strip()
            if v and v not in m[field]:
                m[field].append(v)
    terms = []
    for m in merged.values():
        m["group"] = "search" if not m["automated_rows"] else "automated" if not m["search_rows"] else "both"
        m["match_type"] = ", ".join(m.pop("_match"))
        m["campaign_type"] = ", ".join(m.pop("_type"))
        campaigns = m.pop("_campaign")
        m["campaign"] = campaigns[0] if len(campaigns) == 1 else f"{len(campaigns)} campaigns" if campaigns else ""
        added = [a for a in m.pop("_added") if a.lower() != "none"]
        m["added_excluded"] = added[0] if added else "None"
        terms.append(m)
    return terms


def _themes(rows):
    """Words and two-word phrases that recur across search terms and never convert."""
    stats = {}
    for r in rows:
        words = re.findall(r"[a-z]+(?:'[a-z]+)?", r["search_term"].lower())
        grams = {w for w in words if len(w) >= 3 and w not in STOPWORDS}
        grams |= {f"{a} {b}" for a, b in zip(words, words[1:])
                  if len(a) >= 2 and len(b) >= 2 and a not in STOPWORDS and b not in STOPWORDS}
        for g in grams:
            s = stats.setdefault(g, [0, 0, 0.0, 0.0])  # search terms, clicks, cost, conversions
            s[0] += 1
            s[1] += val(r, "clicks")
            s[2] += val(r, "cost")
            s[3] += val(r, "conversions")
    found = {g: s for g, s in stats.items()
             if not s[3] and s[0] >= THEME_MIN_TERMS and s[2] >= THEME_MIN_COST}
    phrases = [g for g in found if " " in g]
    # "riverside park" says more than "riverside" or "park" alone: drop a word a phrase already covers
    kept = [g for g in found if " " in g
            or not any(g in p.split() and found[p][2] >= THEME_COVER * found[g][2] for p in phrases)]
    shown = []
    for g in sorted(kept, key=lambda g: (-found[g][2], -found[g][0], g)):
        words = g.split()
        if len(words) > 1 and any(  # a listed word already covers this phrase, or a listed phrase overlaps it
                w in shown or any(w in s.split() and found[s][2] >= THEME_COVER * found[g][2] for s in shown if " " in s)
                for w in words):
            continue
        shown.append(g)
    return shown[:THEMES_SHOWN], found


def _chance_text(book, term, p):
    if p is None:
        return "--"
    if p >= 0.995:  # never print 100%: the model is sure, not certain
        return book.pct(f"chance '{term}' is a bad search term, at least", 99, "", term, dp=0) + "+"
    return book.pct(f"chance '{term}' is a bad search term", p * 100, "", term, dp=0)


def _waste_table(book, members, grand, automated, chance):
    cols = ("| Search term | Cost | Clicks | Share of total cost | Chance it's bad | Match type |"
            + (" Campaign type |" if automated else ""))
    out = [cols, "|---|---|---|---|---|---|" + ("---|" if automated else "")]
    for r in members:
        t = r["search_term"]
        c = book.money(f"cost of '{t}'", val(r, "cost"), "cost", t)
        k = book.count(f"clicks of '{t}'", val(r, "clicks"), "clicks", t)
        s = book.pct(f"'{t}' share of total cost", val(r, "cost") / grand.cost * 100, "cost", t)
        b = _chance_text(book, t, chance.get(id(r)))
        row = f"| {esc(t)} | {c} | {k} | {s} | {b} | {esc(r.get('match_type', ''))} |"
        out.append(row + (f" {esc(r.get('campaign_type', ''))} |" if automated else ""))
    return out


def _actions(book, waste, sure, chance, prior, needed, bar, pricey, harvest, cpa_s):
    """The report's to-do list. Each step reuses numbers the report already registered, so the
    number check covers these sentences like any other."""
    out = []
    if waste and prior:
        if sure:
            m = len(sure)
            lead = max(sure, key=lambda r: val(r, "cost"))["search_term"]
            spent = book.money("cost of the waste terms the model is sure about", totals(sure).cost)
            rest = len(waste) - m
            one = m == 1
            detail = (f"The waste model is at least {bar} sure about {'it' if one else 'them'}, and {'it' if one else 'they'} "
                      f"spent {spent}. \u201c{lead}\u201d {'is the one' if one else 'leads'}.")
            if rest:
                detail += (f" The other {book.count('waste terms too early to judge', rest)} "
                           f"{'is' if rest == 1 else 'are'} too early to judge.")
            m_s = book.count("waste terms the waste model is sure about", m)
            out.append({"kind": "negative", "title": f"Add {m_s} negative {plural(m, 'keyword')}", "detail": detail})
        else:
            n = len(waste)
            n_s = book.count("search terms flagged as waste", n)
            if needed is None or needed > ALIKE_CLICKS:
                detail = ("Terms in this account convert at much the same rate, so a search term's missing conversions "
                          "are most likely bad luck.")
            else:
                best = max(waste, key=lambda r: chance.get(id(r), 0))
                t = best["search_term"]
                pct = _chance_text(book, t, chance.get(id(best)))
                clicks = book.count(f"clicks of '{t}'", val(best, "clicks"), "clicks", t)
                need_s = book.count("clicks a search term needs before the waste model is sure it is bad", needed, "clicks")
                detail = (f"None is proven bad yet. The closest, \u201c{t}\u201d, is {pct} likely bad after {clicks} clicks. "
                          f"The waste model needs about {need_s} clicks with no conversion to be {bar} sure.")
            out.append({"kind": "watch", "title": f"Give {n_s} {plural(n, 'term')} more clicks before adding negatives",
                        "detail": detail})
    if pricey:
        t = pricey[0]["search_term"]
        p = book.money(f"cost per conversion of '{t}'", _cpa(pricey[0]), "cpa", t)
        k = len(pricey)
        k_s = book.count("search terms converting at an expensive rate", k)
        why = f"it converts, but at {p} each, more than {EXPENSIVE} times the {cpa_s} average."
        out.append({"kind": "review", "title": f"Review \u201c{t}\u201d" if k == 1 else f"Review {k_s} expensive converters",
                    "detail": why[0].upper() + why[1:] if k == 1 else f"\u201c{t}\u201d leads: {why}"})
    if harvest:
        r = harvest[0]
        t = r["search_term"]
        k = len(harvest)
        k_s = book.count("search terms worth adding as keywords", k)
        v = book.count(f"conversions of '{t}'", val(r, "conversions"), "conversions", t, dp=conv_dp(val(r, "conversions")))
        p = book.money(f"cost per conversion of '{t}'", _cpa(r), "cpa", t)
        out.append({"kind": "add", "title": f"Add {k_s} converting {plural(k, 'term')} as keywords",
                    "detail": f"\u201c{t}\u201d leads with {v} conversions at {p} each."})
    return out


def _cards(book, grand, waste, sure, chance, top, wc, share, d, y, cpa_s, industry, actions, min_s=None):
    """The same results as data for the web app. Every number is a string the FactBook printed."""
    bench = benchmarks.lookup(industry) if industry else None
    dollars = (book.currency or "USD").upper() == "USD"  # the industry's cost per conversion is in US dollars
    kpis = []
    if wc:
        n = book.count("search terms flagged as waste", len(waste))
        rule = f" of {min_s}+" if min_s else ""  # the threshold, so this never reads as every zero-conversion term
        kpis.append({"label": "Wasted spend", "value": wc,
                     "note": f"{n} {plural(len(waste), 'term')}{rule}, zero conversions"})
        kpis.append({"label": "Share of total cost", "value": share, "note": f"of {book.money('total cost', grand.cost)}"})
    if y:
        kpis.append({"label": "A year at this rate", "value": y, "note": f"{d} a day"})
    if cpa_s:
        note = (f"vs {book.money(bench['name'] + ' average Cost per conversion', bench['cpl'], 'cpa')} industry"
                if bench and dollars else "account average")
        kpis.append({"label": "Cost per conversion", "value": cpa_s, "note": note})
    if grand.impressions:
        ctr = book.pct("CTR of the account", grand.clicks / grand.impressions * 100, "ctr", dp=2)
        note = f"vs {book.pct(bench['name'] + ' average CTR', bench['ctr'], 'ctr', dp=2)} industry" if bench else "account average"
        kpis.append({"label": "CTR", "value": ctr, "note": note})
    rows = []
    for r in waste[:top]:
        t = r["search_term"]
        p = chance.get(id(r))
        rows.append({"term": t, "cost": book.money(f"cost of '{t}'", val(r, "cost"), "cost", t),
                     "clicks": book.count(f"clicks of '{t}'", val(r, "clicks"), "clicks", t),
                     "share": book.pct(f"'{t}' share of total cost", val(r, "cost") / grand.cost * 100, "cost", t),
                     "chance": _chance_text(book, t, p), "p": p, "sure": any(r is x for x in sure),
                     "match_type": r.get("match_type", ""), "campaign": r.get("campaign", ""),
                     "campaign_type": r.get("campaign_type", ""), "automated": r["group"] != "search"})
    return {"template": NAME, "kpis": kpis, "actions": actions, "waste": rows, "waste_total": len(waste)}


def _and(parts):
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _client(book, report, x):
    """The branded client report: a cover headline and four sections of blocks, in the agency's voice.
    The web app lays the blocks out on pages; every number is registered, and the app checks the text
    of the finished pages against this FactBook before it lets the PDF out."""
    waste, sure, chance, prior, needed, bar = x["waste"], x["sure"], x["chance"], x["prior"], x["needed"], x["bar"]
    wc, cpa_s, min_s, top = x["wc"], x["cpa_s"], x["min_s"], x["top"]
    n = len(waste)
    n_s = book.count("search terms flagged as waste", n) if n else None

    stats = [(x["share"], "of total cost"), (x["y"], "a year at this rate"), (cpa_s, "per conversion")]
    if wc:
        headline = {"value": wc, "text": f"went to {n_s} {plural(n, 'search term')} that never converted.",
                    "stats": [{"value": v, "label": label} for v, label in stats if v]}
    else:
        headline = {"value": None, "text": f"No search term with zero conversions reached {min_s} in cost.",
                    "stats": [{"value": v, "label": label} for v, label in
                              ((x["total_cost"], "total cost"), (cpa_s, "per conversion")) if v]}

    found = []
    if wc:
        text = (f"That is {x['share']} of the {x['total_cost']} total cost in this export, and each one cost at "
                f"least {min_s}.")
        if x["d"]:
            text += f" At the same rate that is {x['d']} a day, or {x['y']} a year."
        found.append({"type": "lead", "strong": f"{n_s} {plural(n, 'search term')} spent {wc} and never converted.",
                      "text": text})
        if x["sw"] and x["aw"]:
            found.append({"type": "p", "text": f"Of that, {x['sw']} is in Search campaigns and {x['aw']} in Performance "
                                               "Max and other automated campaigns, which take negatives differently."})
        if prior:
            if needed is None or needed > ALIKE_CLICKS:
                why = ("Search terms in this account convert at much the same rate, so one term's missing "
                       "conversions are most likely bad luck.")
            elif sure:
                m_s = book.count("waste terms the waste model is sure about", len(sure))
                mc = book.money("cost of the waste terms the model is sure about", totals(sure).cost)
                why = f"We are at least {bar} sure about {m_s} of them, which spent {mc}."
                if n > len(sure):
                    rest = book.count("waste terms too early to judge", n - len(sure))
                    why += (f" The other {rest} {'has' if n - len(sure) == 1 else 'have'} too few clicks yet to tell "
                            "a bad term from bad luck.")
            else:
                why = ("None of them has had enough clicks yet to prove it is bad rather than unlucky, so these are "
                       "terms to watch, not to block yet.")
            found.append({"type": "p", "text": why})
        most = val(waste[0], "cost") or 1
        rows = []
        for r in waste[:top]:
            t = r["search_term"]
            p_bad = chance.get(id(r))
            rows.append({"label": t, "value": book.money(f"cost of '{t}'", val(r, "cost"), "cost", t),
                         "width": round(val(r, "cost") / most * 100, 1),
                         "tag": f"{_chance_text(book, t, p_bad)} likely bad" if p_bad is not None else "",
                         "strong": any(r is s for s in sure)})
        caption = "Bar length is cost."
        if bar:
            caption += (" Likely bad is the chance a term converts at under half the account's rate, given its "
                        f"clicks so far. We add a negative once a term reaches {bar}.")
        found.append({"type": "bars", "title": "Wasted spend, ranked", "cols": ["Cost", "Likely bad" if bar else ""],
                      "rows": rows, "caption": caption})
        if n > top:
            k = book.count("waste terms beyond the table", n - top)
            c = book.money("cost of waste terms beyond the table", totals(waste[top:]).cost)
            found.append({"type": "note", "text": f"Plus {k} more {plural(n - top, 'term')} that spent {c} in total."})
    else:
        found.append({"type": "lead", "strong": f"No search term with zero conversions reached {min_s} in cost.",
                      "text": "There is nothing to cut one term at a time at this threshold."})
    if x["small"]:
        st = totals(x["small"])
        k = book.count("zero-conversion terms below the threshold", len(x["small"]))
        c = book.money("cost of zero-conversion terms below the threshold", st.cost)
        found.append({"type": "note", "text": f"Below the {min_s} threshold, {k} more zero-conversion "
                                              f"{plural(len(x['small']), 'term')} spent {c} in total."})
    if x["brand_rows"]:
        bt = totals(x["brand_rows"])
        bn = book.count("search terms that match your brand", len(x["brand_rows"]), "terms")
        bc = book.money("cost of search terms that match your brand", bt.cost, "cost")
        bv = book.count("conversions of search terms that match your brand", bt.conversions, "conversions",
                        dp=conv_dp(bt.conversions))
        found.append({"type": "note", "text": f"Searches for the brand are never counted as waste: {bn} "
                                              f"{plural(len(x['brand_rows']), 'search term')} matched it, cost {bc} "
                                              f"and brought {bv} conversions."})
    if x["names"]:
        found.append({"type": "h2", "text": "Words that never convert"})
        found.append({"type": "p", "text": "These words show up across several search terms that spent money without "
                                           "a single conversion. Each is a candidate negative keyword once it is "
                                           "checked against what the business sells."})
        table = []
        for g in x["names"]:
            terms, clicks_g, cost_g, _ = x["found"][g]
            label = f'search terms containing "{g}"'
            table.append([g, book.count(f"number of {label}", terms, "terms", g),
                          book.count(f"clicks of {label}", clicks_g, "clicks", g),
                          book.money(f"cost of {label}", cost_g, "cost", g)])
        found.append({"type": "table", "cols": ["Word or phrase", "Search terms", "Clicks", "Cost"],
                      "align": ["left", "right", "right", "right"], "rows": table})
    totals_row = [{"value": x["total_cost"], "label": "cost"}, {"value": x["clicks"], "label": "clicks"},
                  {"value": x["convs"], "label": "conversions"}]
    if cpa_s:
        totals_row.append({"value": cpa_s, "label": "per conversion"})
    found.append({"type": "stats", "title": "Account totals in this export", "items": totals_row})

    steps = []
    if waste and prior:
        if sure:
            m, one = len(sure), len(sure) == 1
            lead = max(sure, key=lambda r: val(r, "cost"))["search_term"]
            spent = book.money("cost of the waste terms the model is sure about", totals(sure).cost)
            text = (f"We are at least {bar} sure {'it is' if one else 'they are'} bad, and {'it' if one else 'they'} "
                    f"spent {spent}. “{lead}” {'is the one' if one else 'leads'}.")
            if n > m:
                text += (f" The other {book.count('waste terms too early to judge', n - m)} "
                         f"{'is' if n - m == 1 else 'are'} too early to judge.")
            m_s = book.count("waste terms the waste model is sure about", m)
            steps.append({"kind": "negative", "title": f"Add {m_s} negative {plural(m, 'keyword')}", "text": text})
        else:
            title = f"Watch the {n_s} {plural(n, 'term')} before adding negatives"
            if needed is None or needed > ALIKE_CLICKS:
                text = ("Terms in this account convert at much the same rate, so a search term's missing conversions "
                        "are most likely bad luck.")
            else:
                best = max(waste, key=lambda r: chance.get(id(r), 0))
                t = best["search_term"]
                pct = _chance_text(book, t, chance.get(id(best)))
                clicks_b = book.count(f"clicks of '{t}'", val(best, "clicks"), "clicks", t)
                if n == 1:
                    text = f"\u201c{t}\u201d spent {wc} with no conversions, and it is {pct} likely bad after {clicks_b} clicks."
                else:
                    text = (f"They spent {wc} with no conversions, but none is {bar} likely bad yet. The closest, "
                            f"“{t}”, is {pct} likely bad after {clicks_b} clicks.")
                text += (f" A term needs about {x['need_s']} clicks (about {x['need_cost']}) with no conversion before "
                         f"we can be {bar} sure.")
            steps.append({"kind": "watch", "title": title, "text": text})
    if x["pricey"]:
        pricey = x["pricey"][:top]
        t = pricey[0]["search_term"]
        if len(x["pricey"]) == 1:
            r = pricey[0]
            p = book.money(f"cost per conversion of '{t}'", _cpa(r), "cpa", t)
            c = book.money(f"cost of '{t}'", val(r, "cost"), "cost", t)
            v = book.count(f"conversions of '{t}'", val(r, "conversions"), "conversions", t,
                           dp=conv_dp(val(r, "conversions")))
            steps.append({"kind": "review", "title": f"Review “{t}”",
                          "text": f"\u201c{t}\u201d converts, but at {p} each, more than {EXPENSIVE} times the account's "
                                  f"{cpa_s} per conversion. It spent {c} for {v} "
                                  f"{plural(val(r, 'conversions'), 'conversion')}."})
        else:
            k_s = book.count("search terms converting at an expensive rate", len(x["pricey"]))
            rows = []
            for r in pricey:
                rt = r["search_term"]
                rows.append([rt, book.money(f"cost of '{rt}'", val(r, "cost"), "cost", rt),
                             book.count(f"conversions of '{rt}'", val(r, "conversions"), "conversions", rt,
                                        dp=conv_dp(val(r, "conversions"))),
                             book.money(f"cost per conversion of '{rt}'", _cpa(r), "cpa", rt)])
            steps.append({"kind": "review", "title": f"Review {k_s} expensive converters",
                          "text": f"They convert, but at more than {EXPENSIVE} times the account's {cpa_s} per "
                                  "conversion.",
                          "table": {"cols": ["Search term", "Cost", "Conversions", "Cost per conversion"],
                                    "align": ["left", "right", "right", "right"], "rows": rows}})
    if x["harvest"]:
        k = len(x["harvest"])
        k_s = book.count("search terms worth adding as keywords", k)
        rows = []
        for r in x["harvest"][:top]:
            rt = r["search_term"]
            rows.append([rt, book.count(f"conversions of '{rt}'", val(r, "conversions"), "conversions", rt,
                                        dp=conv_dp(val(r, "conversions"))),
                         book.money(f"cost per conversion of '{rt}'", _cpa(r), "cpa", rt), r.get("match_type", "")])
        steps.append({"kind": "add", "title": f"Add {k_s} converting search {plural(k, 'term')} as keywords",
                      "text": f"{'It' if k == 1 else 'They'} converted at or below the account's {cpa_s} per "
                              f"conversion and {'is not a keyword' if k == 1 else 'are not keywords'} yet.",
                      "table": {"cols": ["Search term", "Conversions", "Cost per conversion", "Match type"],
                                "align": ["left", "right", "right", "left"], "rows": rows}})
    for i, step in enumerate(steps, 1):
        step.update(type="step", n=i, tag=STEP_TAGS[step["kind"]])
    recommend = ([{"type": "p", "text": STEP_COUNT.get(len(steps), f"{len(steps)} steps, most useful first.")}]
                 + steps) if steps else [{"type": "p", "text": "Nothing needs changing at this threshold."}]

    sections = [{"id": "found", "title": "What we found", "blocks": found},
                {"id": "recommend", "title": "What we recommend", "blocks": recommend}]
    grand = x["grand"]
    if x["industry"]:
        b, rows = benchmarks.compare(book, x["industry"], cost=grand.cost, clicks=grand.clicks,
                                     impressions=grand.impressions, conversions=grand.conversions,
                                     currency=report.currency)
        compare = []
        for r in rows:
            most = max(r["yours"], r["average"]) or 1
            compare.append({"type": "compare", "name": LONG_NAMES[r["name"]],
                            "read": f"{r['side'].capitalize()}, {'better' if r['better'] else 'worse'}",
                            "better": r["better"], "yours": r["yours_text"], "average": r["average_text"],
                            "yours_width": round(r["yours"] / most * 100, 1),
                            "average_width": round(r["average"] / most * 100, 1)})
        if rows:
            ways = [HOW_IT_COMPARES[r["name"]][r["side"] == "higher"] for r in rows]
            blocks = [{"type": "lead", "strong": "", "text": f"Against the {b['name']} average, the account {_and(ways)}."}]
            blocks += compare
            blocks.append({"type": "note", "text": f"Industry averages: {benchmarks.SOURCE}. A ballpark, not a target: "
                                                   "US-only, averaged over a year, and every advertiser counts "
                                                   "conversions differently. The industry figure for cost per "
                                                   "conversion is cost per lead."})
            sections.append({"id": "benchmarks", "title": "How the account compares", "blocks": blocks})

    file = os.path.basename(report.source or "")
    data = f"One export from Google Ads: `{file}`, the search terms report"
    if report.start and report.end:
        days = book.count("days in the date range", report.days, "days")
        data += f" for {period(report)} ({days} days)"
    data += f", in {report.currency}. Nothing in the Google Ads account was changed: this report only reads the export."
    rules = [f"Waste: search terms with zero conversions and at least {min_s} in cost. Each term's rows are added "
             "up first, so a term that converts anywhere in the account is never waste."]
    if x["brand"]:
        rules.append("Searches for the brand, including close misspellings, are never counted as waste.")
    if x["in_auto"]:
        rules.append("Performance Max and other automated campaigns are listed apart from Search, because negatives "
                     "there only block Search and Shopping ads.")
    if bar:
        rules.append("Likely bad: the chance a term truly converts at less than half the account's rate, learned from "
                     f"how much this account's own search terms differ. {bar} is the bar for adding a negative.")
    if x["names"]:
        rules.append(f"Words that never convert: words and two-word phrases found in at least {THEME_MIN_TERMS} search "
                     "terms that together spent money and got no conversions.")
    rules += [f"Converting, but expensive: cost per conversion above {EXPENSIVE} times the account average.",
              f"Worth adding: {HARVEST_MIN} or more conversions, cost per conversion at or below the account "
              "average, and not a keyword yet.",
              "Totals are recomputed from the rows of the export.",
              "A conversion is whatever this account counts as one."]
    method = [{"type": "h2", "text": "The data"}, {"type": "p", "text": data}]
    sha = fingerprint(report.source)
    if sha:
        method.append({"type": "fingerprint", "value": sha})
    method += [{"type": "h2", "text": "How the numbers were computed"}, {"type": "list", "items": rules},
               {"type": "check", "file": file}]
    sections.append({"id": "method", "title": "How this report was made", "blocks": method})
    return {"template": NAME, "title": CLIENT_TITLE, "period": period(report, compact=True),
            "month": month_label(report), "file": file, "headline": headline, "sections": sections}


def run(report, min_cost=None, industry=None, top=25, brand=None, **_):
    need(report, "search_term", "Search terms report", HOW_TO_EXPORT)
    book = FactBook(report.currency)
    known_default = True
    if min_cost is None:
        min_cost, known_default = min_cost_for(report.currency)
    is_brand = brand_matcher(brand)
    rows = [r for r in report.rows if r.get("search_term")]
    by_term = _by_term(rows)
    brand_rows = [t for t in by_term if is_brand(t["search_term"])]
    others = [t for t in by_term if not is_brand(t["search_term"])]
    grand = totals(rows)
    out = header(book, report, TITLE)
    total_cost = book.money("total cost", grand.cost)
    min_s = book.money("minimum cost for a waste flag (rule)", min_cost, "rule")
    cpa = grand.cost / grand.conversions if grand.conversions else None
    zero = [t for t in others if not val(t, "conversions")]  # not one conversion on any of the term's rows
    waste = sorted((t for t in zero if val(t, "cost") >= min_cost), key=lambda t: -val(t, "cost"))
    small = [t for t in zero if 0 < val(t, "cost") < min_cost]
    every_zero = [t for t in by_term if not val(t, "conversions")]  # brand terms too: what a number check counts
    wasted = totals(waste)
    in_search = [t for t in waste if t["group"] == "search"]
    names, found = _themes(others)
    prior = waste_model.fit_prior((val(r, "clicks"), val(r, "conversions")) for r in others)
    chance = {id(r): waste_model.p_bad(val(r, "clicks"), 0, prior) for r in waste} if prior else {}
    sure = [r for r in waste if chance.get(id(r), 0) >= waste_model.CONFIDENT]
    in_auto = [t for t in waste if t["group"] == "automated"]
    in_both = [t for t in waste if t["group"] == "both"]

    out += ["## Summary", ""]
    if not known_default:
        out += [f"_OpenPPC has no default waste threshold for {report.currency}, so it used {min_s}. "
                "Set your own with `--min-cost`._", ""]
    wc = share = d = y = cpa_s = bar = needed = sw = aw = need_s = need_cost = None
    pricey = harvest = []
    if waste and grand.cost:
        n = book.count("search terms flagged as waste", len(waste))
        wc = book.money("wasted cost (zero conversions, at or above the threshold)", wasted.cost)
        share = book.pct("wasted cost as a share of total cost", wasted.cost / grand.cost * 100, "cost")
        out.append(f"**{n} {plural(len(waste), 'search term')} spent {wc} and never converted.** That is "
                   f"{share} of the {total_cost} total cost in this export, and each one cost at least {min_s}.")
        if totals(every_zero).cost > wasted.cost + 0.005:  # say how this ties to the all-in figure
            az = book.count("search terms with no conversions", len(every_zero), "terms")
            ac = book.money("cost of all search terms with no conversions", totals(every_zero).cost, "cost")
            brand_too = any(is_brand(t["search_term"]) for t in every_zero)
            out[-1] += (f" All {az} search terms with no conversions, whatever they cost"
                        + (" and brand terms included" if brand_too else "") + f", spent {ac}.")
        search_cost, auto_cost = sum(t["search_cost"] for t in waste), sum(t["automated_cost"] for t in waste)
        if search_cost and auto_cost:
            sw = book.money("wasted cost in Search campaigns", search_cost, "cost")
            aw = book.money("wasted cost in Performance Max and other automated campaigns", auto_cost, "cost")
            out += ["", f"Of that, {sw} is in Search campaigns and {aw} in Performance Max and other "
                        "automated campaigns, which take negatives differently."]
        if report.days:
            per_day = wasted.cost / report.days
            d = book.money("wasted cost per day", per_day)
            y = book.money("wasted cost per year at the same daily rate", per_day * 365)
            out += ["", f"At the same rate that is {d} a day, or {y} a year."]
        if prior:
            bar = book.pct("waste model: sure enough to add a negative (rule)", waste_model.CONFIDENT * 100, "rule", dp=0)
            if sure:
                m = book.count("waste terms the waste model is sure about", len(sure))
                mc = book.money("cost of the waste terms the model is sure about", totals(sure).cost)
                doubt = round(sum(1 - chance[id(r)] for r in sure))
                maybe = (f" (about {book.count('sure waste terms that may still be fine', doubt)} of them may still turn "
                         "out fine)" if doubt else "")
                out += ["", f"The waste model is at least {bar} sure about {m} of them, which spent {mc}{maybe}: add "
                            f"{'it as a negative' if len(sure) == 1 else 'those as negatives'}. The other {book.count('waste terms too early to judge', len(waste) - len(sure))} "
                            f"{'has' if len(waste) - len(sure) == 1 else 'have'} too few clicks to tell a bad term from bad luck."]
            else:
                out += ["", f"None of them has enough clicks for the waste model to be {bar} sure it is bad rather "
                            "than unlucky, so give them more clicks before adding negatives."
                            + (" The words they share are below." if names else "")]
    else:
        out.append(f"No search term with zero conversions reached {min_s} in cost. "
                   "Nothing to cut one term at a time at this threshold.")
    clicks = book.count("total clicks", grand.clicks, "clicks")
    convs = book.count("total conversions", grand.conversions, "conversions", dp=conv_dp(grand.conversions))
    line = f"Account totals in this export: {total_cost} cost, {clicks} clicks, {convs} conversions"
    if cpa:
        cpa_s = book.money("account cost per conversion", cpa, "cpa")
        line += f", {cpa_s} per conversion"
    out += ["", line + "."]
    if brand_rows:
        bt = totals(brand_rows)
        bn = book.count("search terms that match your brand", len(brand_rows), "terms")
        bc = book.money("cost of search terms that match your brand", bt.cost, "cost")
        bv = book.count("conversions of search terms that match your brand", bt.conversions, "conversions",
                        dp=conv_dp(bt.conversions))
        verb = "matches" if len(brand_rows) == 1 else "match"
        out += ["", f"Brand terms are left out of the waste list: {bn} {plural(len(brand_rows), 'search term')} "
                    f"{verb} your brand, cost {bc} and brought {bv} conversions. Never add them as negatives."]

    todo_at = len(out)  # "What to do" goes here, once everything it sums up is computed
    if waste:
        out += ["", "## Wasted spend, ranked"]
        if not (in_auto or in_both):
            out += [""] + _waste_table(book, waste[:top], grand, False, chance)
        else:
            cap = book.count("negative keywords a Performance Max campaign can hold (Google's limit)",
                             PMAX_NEGATIVES, "rule")
            for title, members, note, auto in (
                    ("In Search campaigns", in_search, "Add these as negative keywords in their campaigns.", False),
                    ("In Performance Max and other automated campaigns", in_auto,
                     f"Performance Max takes negative keywords in the campaign (up to {cap}) or from an "
                     "account-level negative keyword list, and there they only block Search and Shopping ads, "
                     "not YouTube, Display or Gmail.", True),
                    ("In both Search and automated campaigns", in_both,
                     "These spent in both. An account-level negative keyword list blocks a term in both places; "
                     "otherwise add it in each campaign.", True)):
                if members:
                    out += ["", f"### {title}", "", note, ""] + _waste_table(book, members[:top], grand, auto, chance)
        if len(waste) > top:
            rest = totals(waste[top:])
            k = book.count("waste terms beyond the table", len(waste) - top)
            c = book.money("cost of waste terms beyond the table", rest.cost)
            out += ["", f"Plus {k} more {plural(len(waste) - top, 'term')} that spent {c} in total."]
    if small:
        st = totals(small)
        k = book.count("zero-conversion terms below the threshold", len(small))
        c = book.money("cost of zero-conversion terms below the threshold", st.cost)
        out += ["", f"Below the {min_s} threshold, {k} more zero-conversion {plural(len(small), 'term')} "
                    f"spent {c} in total." + (" The words they share are below." if names else "")]
    if prior:
        needed = waste_model.clicks_to_flag(prior)
        if needed is None or needed > ALIKE_CLICKS:
            out += ["", "Search terms in this account convert at much the same rate, so one term's missing conversions "
                        "are most likely bad luck." + (" Judge the words below, not single terms." if names else "")]
        else:
            need_s = book.count("clicks a search term needs before the waste model is sure it is bad", needed, "clicks")
            need_cost = book.money("cost of that many clicks at the account's average CPC",
                                   needed * grand.cost / grand.clicks, "cost")
            r_s = book.pct("account conversion rate", grand.conversions / grand.clicks * 100, "cvr")
            out += ["", f"At this account's {r_s} conversion rate, and given how much its search terms differ, a term "
                        f"needs about {need_s} clicks (about {need_cost}) with no conversion before the waste model is sure it is "
                        "bad." + (" Below that, judge words, not single terms." if names else "")]

    if names:
        out += ["", "## Words that never convert", "",
                "These words show up across several search terms that spent money without a single "
                "conversion. Each one is a candidate negative keyword: check it against what you sell first.",
                "", "| Word or phrase | Search terms | Clicks | Cost |", "|---|---|---|---|"]
        for g in names:
            terms, clicks_g, cost_g, _ = found[g]
            label = f'search terms containing "{g}"'  # the word is the row: its figures only count where it is named
            n = book.count(f"number of {label}", terms, "terms", g)
            k = book.count(f"clicks of {label}", clicks_g, "clicks", g)
            c = book.money(f"cost of {label}", cost_g, "cost", g)
            out.append(f"| {esc(g)} | {n} | {k} | {c} |")

    if cpa:
        pricey = sorted((r for r in by_term if val(r, "conversions") and val(r, "cost") >= min_cost
                         and _cpa(r) > EXPENSIVE * cpa), key=lambda r: -val(r, "cost"))
        if pricey:
            out += ["", "## Converting, but expensive", "",
                    f"These converted, but at more than {EXPENSIVE} times the account's {cpa_s} per conversion.",
                    "", "| Search term | Cost | Conversions | Cost per conversion |", "|---|---|---|---|"]
            for r in pricey[:top]:
                t = r["search_term"]
                c = book.money(f"cost of '{t}'", val(r, "cost"), "cost", t)
                v = book.count(f"conversions of '{t}'", val(r, "conversions"), "conversions", t,
                               dp=conv_dp(val(r, "conversions")))
                p = book.money(f"cost per conversion of '{t}'", _cpa(r), "cpa", t)
                out.append(f"| {esc(t)} | {c} | {v} | {p} |")
        harvest = sorted((r for r in by_term if val(r, "conversions") >= HARVEST_MIN and _cpa(r) <= cpa
                          and _not_yet_added(r)), key=lambda r: (-val(r, "conversions"), _cpa(r)))
        if harvest:
            out += ["", "## Worth adding as keywords", "",
                    f"These converted at or below the account's {cpa_s} per conversion and are not keywords yet.",
                    "", "| Search term | Conversions | Cost per conversion | Match type |", "|---|---|---|---|"]
            for r in harvest[:top]:
                t = r["search_term"]
                v = book.count(f"conversions of '{t}'", val(r, "conversions"), "conversions", t,
                               dp=conv_dp(val(r, "conversions")))
                p = book.money(f"cost per conversion of '{t}'", _cpa(r), "cpa", t)
                out.append(f"| {esc(t)} | {v} | {p} | {esc(r.get('match_type', ''))} |")

    actions = _actions(book, waste, sure, chance, prior, needed, bar, pricey, harvest, cpa_s)
    if actions:
        out[todo_at:todo_at] = ["", "## What to do", ""] + [
            f"{i}. **{a['title']}.** {a['detail']}" for i, a in enumerate(actions, 1)]
    book.cards = _cards(book, grand, waste, sure, chance, top, wc, share, d, y, cpa_s, industry, actions, min_s)

    if industry:
        out += benchmarks.section(book, industry, cost=grand.cost, clicks=grand.clicks,
                                  impressions=grand.impressions, conversions=grand.conversions,
                                  currency=report.currency)
    book.client = _client(book, report, {
        "waste": waste, "sure": sure, "chance": chance, "prior": prior, "needed": needed, "bar": bar, "wc": wc,
        "share": share, "d": d, "y": y, "cpa_s": cpa_s, "min_s": min_s, "total_cost": total_cost, "clicks": clicks,
        "convs": convs, "sw": sw, "aw": aw, "need_s": need_s, "need_cost": need_cost, "small": small,
        "brand_rows": brand_rows, "brand": brand, "names": names, "found": found, "pricey": pricey,
        "harvest": harvest, "in_auto": in_auto + in_both, "grand": grand, "industry": industry, "top": top})

    rule_bar = book.pct("waste model: sure enough to add a negative (rule)", waste_model.CONFIDENT * 100, "rule", dp=0)
    out += ["", "## How this was computed", "",
            f"- Waste: search terms with zero conversions and at least {min_s} in cost. "
            "Change the threshold with `--min-cost`.",
            "- Each search term's rows are added up first: Google lists a term once for every campaign, ad group "
            "and match type it showed in, and a term that converts on any of its rows is never waste.",
            "- Brand terms (from `--brand`, including close misspellings) are never counted as waste.",
            "- Performance Max and other automated campaign types are listed apart from Search, because "
            "negatives there only block Search and Shopping ads.",
            f"- Words that never convert: words and two-word phrases found in at least {THEME_MIN_TERMS} "
            "search terms that together spent money and got no conversions.",
            "- Chance it's bad: the waste model learns how much this account's search terms differ in "
            "conversion rate (a beta-binomial prior fit on your own terms), then works out for each term the chance "
            f"that it truly converts at less than half the account's rate. {rule_bar} is "
            "the bar for adding a negative; the dollar threshold only decides what is worth listing.",
            f"- Converting, but expensive: cost per conversion above {EXPENSIVE} times the account average.",
            f"- Worth adding: {HARVEST_MIN} or more conversions, cost per conversion at or below the account "
            "average, and not already added or excluded.",
            "- Totals are recomputed from the rows. The Total lines in Google's export are ignored.",
            "- A conversion is whatever this account counts as one. If that includes small actions such as "
            "page views, zero conversions means something weaker here."]
    return out, book

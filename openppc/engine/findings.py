"""Findings block: the arithmetic and the pattern read, done in code, before any model.

WHY: when we tested language models on real Google Ads accounts, they reversed spend,
reach and CPA directions and invented figures, even after fine-tuning. Those are not
language tasks. This module computes every delta, names every direction, classifies
the account pattern with explicit rules, and hands any writer a block of facts it
cannot get wrong.

The rules are a media buyer's playbook. Read them, argue with them, send a PR.

Ported from the Second Step audit engine (September 2026). Every threshold is a named
constant below, and each one has a row in rulebook/rules.csv saying where it comes from.

Usage:
    from openppc.engine.findings import build_findings
    block = build_findings(dict(cs=460, ps=1144, ci=11238, pi=38647, cc=279, pc=640,
                                cv=41, pv=50), meta=dict(currency="USD",
                                business_model="sailing club (membership lead-gen)"))
"""

FLAT = 0.03             # |change| below this is "flat"
SMALL_SAMPLE = 10       # fewer conversions than this in BOTH periods: do not trend CPA
NOISE_VOLUME = 50       # under this many conversions a period...
NOISE_MOVE = 0.10       # ...a conversion move smaller than this is one or two events: flat
HELD = 0.20             # spend cut and conversions within this of prior: they held
CPA_BAND = 0.10         # CPA within this of prior: efficiency held
DILUTION_REACH = 0.50   # impressions up at least this much...
DILUTION_CTR = 0.70     # ...while CTR fell to this share of prior or less: reach dilution
TIGHTEN_REACH = 0.30    # impressions down at least this much...
TIGHTEN_CTR = 1.30      # ...while CTR rose to this multiple of prior or more: tightening
CVR_DROP = 0.70         # conversion rate at or below this share of prior...
CVR_DROP_CLICKS = 200   # ...on at least this many clicks
MICRO_CVR = 0.25        # this share of clicks converting: engagement actions, not outcomes
THIN_DATA = 30          # conversions a period Google wants before automated bidding is judged
SEASONAL_WORDS = ("seasonal", "rafting", "ski", "charter")


def _pct(c, p):
    if not p:
        return None
    return (c - p) / p


def _dir(c, p):
    d = _pct(c, p)
    if d is None:
        return "n/a"
    if abs(d) < FLAT:
        return "flat"
    return "up" if d > 0 else "down"


def _fmt(v, dp=0):
    if v is None:
        return "n/a"
    return f"{v:,.{dp}f}"


def _pc(c, p):
    d = _pct(c, p)
    if d is None:
        return ""
    if abs(d) < FLAT:
        return " (flat)"
    return f" ({'+' if d > 0 else '-'}{abs(d) * 100:.0f}%)"


def _line(name, c, p, dp=0, unit="", lower_is_better=False):
    """'Spend: 460, from 1,144. DOWN 60%.'  Direction word is explicit and upper-case."""
    d = _dir(c, p)
    word = {"up": "UP", "down": "DOWN", "flat": "FLAT", "n/a": "no prior base"}[d]
    tail = "" if d in ("flat", "n/a") else f" {abs(_pct(c, p)) * 100:.0f}%"
    verdict = ""
    if lower_is_better and d in ("up", "down"):
        verdict = " (improved)" if d == "down" else " (worse)"
    return f"- {name}: {_fmt(c, dp)}{unit}, from {_fmt(p, dp)}{unit}. {word}{tail}{verdict}."


def classify(m):
    """Return (primary_read, flags[]) from the eight raw metrics. Rules in priority order."""
    cs, ps, ci, pi, cc, pc, cv, pv = (m[k] for k in ("cs", "ps", "ci", "pi", "cc", "pc", "cv", "pv"))
    cpa_c = cs / cv if cv else None
    cpa_p = ps / pv if pv else None
    ctr_c = cc / ci if ci else 0
    ctr_p = pc / pi if pi else 0
    cvr_c = cv / cc if cc else 0
    cvr_p = pv / pc if pc else 0
    sp = _dir(cs, ps)
    cv_d = _dir(cv, pv)
    if max(cv, pv) < NOISE_VOLUME and _pct(cv, pv) is not None and abs(_pct(cv, pv)) < NOISE_MOVE:
        cv_d = "flat"
    cpa_d = _dir(cpa_c, cpa_p) if (cpa_c and cpa_p) else "n/a"
    flags = []

    # ---- primary read: first matching rule wins ------------------------------------
    if cv == 0 and pv == 0:
        read = ("NO TRACKED CONVERSIONS IN EITHER PERIOD. Verify tracking before reading "
                "performance. Every cost figure here is meaningless until it fires.")
    elif cv == 0:
        read = (f"CONVERSIONS WENT TO ZERO, from {_fmt(pv, 1)}, on {sp} spend. Tracking is "
                "the first suspect, before any performance conclusion.")
    elif pv == 0:
        read = (f"CONVERSIONS APPEARED FROM ZERO ({_fmt(cv, 1)}). Either tracking started "
                "working or the account did. Confirm which before crediting the account.")
    elif max(cv, pv) < SMALL_SAMPLE:
        read = (f"SAMPLE TOO SMALL: {_fmt(cv, 1)} vs {_fmt(pv, 1)} conversions. Direction is "
                "noise at this volume. Do not read CPA movement as a trend or act on it.")
    elif sp == "down" and -HELD <= _pct(cv, pv) <= FLAT and cpa_d == "down":
        read = (f"EFFICIENCY WIN. Spend cut {abs(_pct(cs, ps)) * 100:.0f}%, conversions held at "
                f"{cv / pv * 100:.0f}% of prior, CPA improved {abs(_pct(cpa_c, cpa_p)) * 100:.0f}%. "
                "Volume is the constraint, not efficiency. Falling conversions here are a GOOD outcome.")
    elif sp == "down" and _pct(cv, pv) < -HELD and cpa_d == "down":
        read = (f"EFFICIENT CONTRACTION. Spend cut {abs(_pct(cs, ps)) * 100:.0f}% and conversions fell "
                f"{abs(_pct(cv, pv)) * 100:.0f}%, less than spend, so CPA improved "
                f"{abs(_pct(cpa_c, cpa_p)) * 100:.0f}%. The cut removed waste first. Volume is now the constraint; "
                "the falling conversion count is the price of the efficiency, not a failure.")
    elif sp == "down" and cv_d == "down" and (cpa_d in ("flat", "n/a") or
            (cpa_c and cpa_p and abs(_pct(cpa_c, cpa_p)) <= CPA_BAND)):
        read = ("BUDGET REDUCTION, EFFICIENCY HELD. Spend, clicks and conversions fell together; "
                f"CPA moved within {CPA_BAND * 100:.0f}%. Volume fell because spend fell, not because performance broke.")
    elif sp == "down" and cv_d == "down" and cpa_d == "up":
        read = (f"CONTRACTION WITH WORSENING EFFICIENCY. Spend down {abs(_pct(cs, ps)) * 100:.0f}% "
                f"but conversions fell faster ({abs(_pct(cv, pv)) * 100:.0f}%), so CPA rose "
                f"{abs(_pct(cpa_c, cpa_p)) * 100:.0f}%. The cut removed converting volume, not just waste.")
    elif sp in ("up", "flat") and cv_d == "down" and cpa_d == "up":
        if sp == "up":
            read = (f"OVER-EXPANSION. Spend up {abs(_pct(cs, ps)) * 100:.0f}% while conversions fell "
                    f"{abs(_pct(cv, pv)) * 100:.0f}%; CPA up {abs(_pct(cpa_c, cpa_p)) * 100:.0f}%. "
                    "More money bought worse traffic, or the funnel broke after the click. This is the worst pattern.")
        else:
            read = (f"DETERIORATION AFTER THE CLICK. Spend flat, conversions down "
                    f"{abs(_pct(cv, pv)) * 100:.0f}%, CPA up {abs(_pct(cpa_c, cpa_p)) * 100:.0f}%. "
                    "Traffic volume is similar; what changed is landing page, form, offer or tracking, not targeting.")
    elif cv_d == "up" and cpa_d == "down":
        read = (f"EFFICIENCY GAIN. Conversions up {abs(_pct(cv, pv)) * 100:.0f}% and CPA down "
                f"{abs(_pct(cpa_c, cpa_p)) * 100:.0f}% on {sp} spend. More output at lower cost.")
    elif cv_d == "up" and sp == "up" and cpa_d == "up":
        read = (f"GROWTH AT A WORSENING RATE. Conversions up {abs(_pct(cv, pv)) * 100:.0f}% but spend up "
                f"{abs(_pct(cs, ps)) * 100:.0f}% and CPA up {abs(_pct(cpa_c, cpa_p)) * 100:.0f}%. "
                "The marginal conversion costs far more than the average. Growth is real; efficiency is degrading.")
    elif cv_d == "up" and cpa_d in ("flat", "n/a"):
        read = (f"CLEAN SCALE. Conversions up {abs(_pct(cv, pv)) * 100:.0f}% with CPA flat. "
                "Spend and output grew together at stable efficiency.")
    elif cv_d == "flat" and cpa_d == "up":
        read = (f"PAYING MORE FOR THE SAME. Conversions flat, CPA up {abs(_pct(cpa_c, cpa_p)) * 100:.0f}%. "
                "Extra spend or reach returned nothing.")
    elif cv_d == "flat" and cpa_d == "down":
        read = (f"SAME OUTPUT, CHEAPER. Conversions flat, CPA down {abs(_pct(cpa_c, cpa_p)) * 100:.0f}%. "
                "Efficiency improved without volume changing.")
    else:
        read = "MIXED OR FLAT. No single dominant pattern; read the metric lines individually."

    # ---- secondary flags: independent of the primary read ---------------------------
    if _pct(ci, pi) is not None and _pct(ci, pi) >= DILUTION_REACH and ctr_p and ctr_c / ctr_p <= DILUTION_CTR:
        flags.append(f"REACH DILUTION: impressions up {_pct(ci, pi) * 100:.0f}% while CTR fell from "
                     f"{ctr_p * 100:.2f}% to {ctr_c * 100:.2f}%. Broad matching or audience expansion is buying low-intent reach.")
    if _pct(ci, pi) is not None and _pct(ci, pi) <= -TIGHTEN_REACH and ctr_p and ctr_c / ctr_p >= TIGHTEN_CTR:
        flags.append(f"TIGHTENING: reach cut {abs(_pct(ci, pi)) * 100:.0f}% while CTR rose from "
                     f"{ctr_p * 100:.2f}% to {ctr_c * 100:.2f}%. Targeting narrowed and relevance improved.")
    if cvr_p and cvr_c / cvr_p <= CVR_DROP and cc >= CVR_DROP_CLICKS:
        flags.append(f"CONVERSION RATE fell from {cvr_p * 100:.2f}% to {cvr_c * 100:.2f}%. "
                     "Clicks are converting worse; suspect landing page, offer, tracking, or click quality.")
    if cvr_c >= MICRO_CVR:
        flags.append(f"MICRO-CONVERSIONS LIKELY: {cvr_c * 100:.0f}% of clicks convert. These are engagement "
                     "actions, not outcomes. Do not read CPA as cost per lead or booking.")
    if 0 < max(cv, pv) < THIN_DATA:
        flags.append(f"THIN DATA: under {THIN_DATA} conversions a period is too few to judge automated bidding on.")
    return read, flags


def biggest_move(m):
    """Which metric moved most, dollar-weighted: CPA and conversions outrank reach."""
    cs, ps, cv, pv = m["cs"], m["ps"], m["cv"], m["pv"]
    cpa_c = cs / cv if cv else None
    cpa_p = ps / pv if pv else None
    cands = []
    if cpa_c and cpa_p:
        cands.append(("CPA", _pct(cpa_c, cpa_p)))
    if pv:
        cands.append(("conversions", _pct(cv, pv)))
    if ps:
        cands.append(("spend", _pct(cs, ps)))
    if not cands:
        return "not computable"
    name, d = max(cands, key=lambda x: abs(x[1]))
    return f"{name} {'up' if d > 0 else 'down'} {abs(d) * 100:.0f}%"


def build_findings(m, meta=None):
    meta = meta or {}
    cs, ps, ci, pi, cc, pc, cv, pv = (m[k] for k in ("cs", "ps", "ci", "pi", "cc", "pc", "cv", "pv"))
    cpa_c = cs / cv if cv else None
    cpa_p = ps / pv if pv else None
    ctr_c = cc / ci * 100 if ci else 0
    ctr_p = pc / pi * 100 if pi else 0
    read, flags = classify(m)
    bm = (meta.get("business_model") or "").lower()
    if any(w in bm for w in SEASONAL_WORDS):
        flags.append("SEASONAL BUSINESS: period-over-period is the wrong lens. Most of any change is the "
                     "calendar. Compare against the same period last year before crediting the account.")
    cur = meta.get("currency", "USD")
    if cur and cur.upper() != "USD":
        flags.append(f"CURRENCY IS {cur.upper()}: do not compare these figures to USD accounts.")

    lines = [
        "COMPUTED FINDINGS (facts, already calculated; restate them, never recompute or reverse them):",
        _line("Spend", cs, ps),
        _line("Impressions", ci, pi),
        _line("Clicks", cc, pc),
        f"- CTR: {ctr_c:.2f}%, from {ctr_p:.2f}%. {_dir(ctr_c, ctr_p).upper()}.",
        _line("Conversions", cv, pv, dp=1 if (cv % 1 or pv % 1) else 0),
        (_line("CPA", cpa_c, cpa_p, dp=2, lower_is_better=True)
         if (cpa_c and cpa_p) else f"- CPA: {_fmt(cpa_c, 2)}, from {_fmt(cpa_p, 2)}."),
        "",
        f"READ: {read}",
        f"BIGGEST MOVE: {biggest_move(m)}",
    ]
    if flags:
        lines.append("FLAGS:")
        lines += [f"- {f}" for f in flags]
    else:
        lines.append("FLAGS: none")
    return "\n".join(lines)

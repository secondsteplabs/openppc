"""Account structure audit: how the account is built, not how it performed.

Reads an account snapshot (openppc/ingest/account.py). Every check is a row in
rulebook/rules.csv, and where Google and practitioners disagree the report shows both sides
instead of picking one. Only live Search is judged: a keyword or ad counts when it, its ad
group and its campaign are all enabled.
"""
import os
from collections import Counter, defaultdict, namedtuple
from datetime import date

from ..facts import FactBook
from ..ingest.account import load_snapshot, words
from ._common import brand_matcher, esc, plural

NAME = "account-structure"
TITLE = "Account structure audit"
TIER = "free"
INPUT_KIND = "account"
INPUT = "Account snapshot (.json)"
SUMMARY = ("How the account is built: broad match without Smart Bidding, brand mixed with non-brand, "
           "duplicate keywords, negatives that block your own keywords, thin or pinned ads, missing "
           "sitelinks, retired bidding and more.")

SMART_BIDDING = frozenset({"TARGET_CPA", "TARGET_ROAS", "MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE"})
CLICK_BIDDING = frozenset({"MANUAL_CPC", "TARGET_SPEND", "ENHANCED_CPC"})
RSA_MAX_HEADLINES = 15      # Google: a responsive search ad holds up to 15 headlines; fill them...
RSA_MAX_DESCRIPTIONS = 4    # ...and all 4 descriptions
RSA_FEW_HEADLINES = 8       # Optmyzr's audit fails ads with fewer headlines than this
MIN_RSAS_PER_AD_GROUP = 2   # Google: at least 2 responsive search ads in every ad group
MIN_SITELINKS = 4           # Google and Optmyzr: at least 4 sitelinks
MIN_CALLOUTS = 4            # Optmyzr: at least 4 callouts...
MIN_SNIPPETS = 1            # ...and 1 structured snippet per Search campaign
NICE = {"TARGET_SPEND": "Maximize clicks", "MANUAL_CPC": "Manual CPC", "ENHANCED_CPC": "Enhanced CPC",
        "TARGET_CPA": "Target CPA", "TARGET_ROAS": "Target ROAS", "PRESENCE_OR_INTEREST": "Presence or interest"}

Check = namedtuple("Check", "title rule status summary lines")  # status: found, passed, info, missing, needs brand


def accepts(data):
    return isinstance(data, dict) and data.get("campaigns") is not None


def load(path):
    return load_snapshot(path)


def nice(value):
    return NICE.get(value, (value or "unknown").replace("_", " ").capitalize())


def blocks(negative, match_type, keyword):
    """Would this negative stop this keyword's own searches? Exact: the same words. Phrase: the
    words together and in order. Broad, or match type unknown: every word, in any order."""
    n, k = words(negative), words(keyword)
    if not n:
        return False
    if match_type == "EXACT":
        return n == k
    if match_type == "PHRASE":
        return any(k[i:i + len(n)] == n for i in range(len(k) - len(n) + 1))
    return set(n) <= set(k)


def _live(data):
    camps = {c["id"]: c for c in data["campaigns"] if c["status"] == "ENABLED" and c["channel"] in (None, "SEARCH")}
    groups = {g["id"]: g for g in data["ad_groups"] or [] if g["status"] == "ENABLED" and g["campaign_id"] in camps}
    kws = [dict(k, campaign_id=groups[k["ad_group_id"]]["campaign_id"]) for k in data["keywords"] or []
           if k["status"] == "ENABLED" and k["ad_group_id"] in groups]
    ads = [a for a in data["ads"] or []
           if a["status"] == "ENABLED" and a["ad_group_id"] in groups and a["type"] == "RESPONSIVE_SEARCH_AD"]
    return camps, groups, kws, ads


def _named(book, *names):
    """Register names a table prints, so digits inside them ("40 gallon water heater") read as part of the
    name, not as claims the checker has to trace."""
    for n in names:
        book.add("name printed in this report", 0, "count", "", n)


def _missing(title, rule, what):
    return Check(title, rule, "missing", f"Not in this file ({what})", [])


def _broad(book, camps, kws, top):
    title, rule = "Broad match without Smart Bidding", "search-broad-match-needs-smart-bidding"
    if not kws or all(c["bidding"] is None for c in camps.values()):
        return _missing(title, rule, "keywords and bid strategies")
    rows = []
    for c in camps.values():
        n = sum(1 for k in kws if k["campaign_id"] == c["id"] and k["match_type"] == "BROAD")
        if c["bidding"] and c["bidding"] not in SMART_BIDDING and n:
            rows.append((c, n))
    if not rows:
        return Check(title, rule, "passed", "Passed", [])
    total = sum(n for _, n in rows)
    t = book.count("broad match keywords in campaigns without Smart Bidding", total, "")
    k = book.count("campaigns running broad match without Smart Bidding", len(rows))
    lines = ["Google: broad match keywords should only run in campaigns that use Smart Bidding (Target CPA, "
             "Target ROAS, Maximize conversions or Maximize conversion value). On any other strategy, broad "
             "match buys loosely related searches with nothing steering it toward conversions.", "",
             "| Campaign | Bidding | Broad keywords |", "|---|---|---|"]
    for c, n in sorted(rows, key=lambda x: -x[1])[:top]:
        v = book.count(f"broad match keywords in {c['name']}", n, "", c["name"])
        lines.append(f"| {esc(c['name'])} | {nice(c['bidding'])} | {v} |")
    return Check(title, rule, "found", f"{t} {plural(total, 'keyword')} in {k} {plural(len(rows), 'campaign')}", lines)


def _brand_mix(book, camps, kws, brand, top):
    title, rule = "Brand and non-brand in one campaign", "struct-brand-nonbrand"
    if not brand:
        return Check(title, rule, "needs brand", "Add --brand to check", [])
    if not kws:
        return _missing(title, rule, "keywords")
    is_brand = brand_matcher(brand)
    rows = []
    for c in camps.values():
        texts = [k["text"] for k in kws if k["campaign_id"] == c["id"]]
        b = sum(1 for t in texts if is_brand(t))
        if b and len(texts) - b:
            rows.append((c, b, len(texts) - b))
    if not rows:
        return Check(title, rule, "passed", "Passed", [])
    k = book.count("campaigns mixing brand and non-brand keywords", len(rows))
    lines = ["Practitioners keep brand keywords in their own campaigns. Brand searches convert cheaply, so "
             "mixed in they hide how the other keywords really perform, and the two need different budgets "
             "and bids.", "", "| Campaign | Brand keywords | Other keywords |", "|---|---|---|"]
    for c, b, other in rows[:top]:
        bs = book.count(f"brand keywords in {c['name']}", b, "", c["name"])
        os_ = book.count(f"non-brand keywords in {c['name']}", other, "", c["name"])
        lines.append(f"| {esc(c['name'])} | {bs} | {os_} |")
    return Check(title, rule, "found", f"{k} {plural(len(rows), 'campaign')}", lines)


def _duplicates(book, groups, kws, top):
    title, rule = "Duplicate keywords", "kw-duplicates"
    if not kws:
        return _missing(title, rule, "keywords")
    where = defaultdict(set)
    for k in kws:
        where[(" ".join(words(k["text"])), k["match_type"])].add(k["ad_group_id"])
    dups = sorted(((text, mt, ags) for (text, mt), ags in where.items() if len(ags) >= 2), key=lambda d: -len(d[2]))
    if not dups:
        return Check(title, rule, "passed", "Passed", [])
    n = book.count("keywords live in more than one ad group", len(dups), "")
    lines = ["The same keyword and match type is live in more than one ad group, so your own ad groups compete "
             "for the same searches. Keep the one in the best-fitting ad group and pause the others. Google's "
             "structure guide says the same; practitioners add: don't let Google's auto-applied \"remove "
             "redundant keywords\" pick for you.", "", "| Keyword | Match type | Ad groups |", "|---|---|---|"]
    for text, mt, ags in dups[:top]:
        names = [groups[a]["name"] for a in sorted(ags)]
        _named(book, text, *names)
        lines.append(f"| {esc(text)} | {nice(mt)} | {', '.join(esc(g) for g in names)} |")
    return Check(title, rule, "found", f"{n} {plural(len(dups), 'keyword')}", lines)


def _conflicts(book, camps, groups, kws, negatives, top):
    title, rule = "Negatives that block your own keywords", "neg-conflicts"
    if negatives is None or not kws:
        return _missing(title, rule, "negative keywords")
    scoped = [n for n in negatives if n["status"] in (None, "ENABLED") and n["level"] in ("AD_GROUP", "CAMPAIGN")]
    found = [(n, k) for k in kws for n in scoped
             if n["owner_id"] == (k["ad_group_id"] if n["level"] == "AD_GROUP" else k["campaign_id"])
             and blocks(n["text"], n["match_type"], k["text"])]
    lists = sum(1 for n in negatives if n["level"] == "LIST")
    note = " (shared lists not checked)" if lists else ""
    if not found:
        return Check(title, rule, "passed", "Passed" + note, [])
    n = book.count("negative keywords that block a live keyword", len(found), "")
    lines = ["A negative keyword that matches one of your own keywords stops that keyword from serving. Remove "
             "the negative, or narrow it to exact match.", "",
             "| Negative | Level | Blocks keyword | Ad group |", "|---|---|---|---|"]
    for neg, k in found[:top]:
        mt = nice(neg["match_type"]) if neg["match_type"] else "match type unknown"
        _named(book, neg["text"], k["text"], groups[k["ad_group_id"]]["name"])
        lines.append(f"| -{esc(neg['text'])} ({mt}) | {nice(neg['level'])} | {esc(k['text'])} | "
                     f"{esc(groups[k['ad_group_id']]['name'])} |")
    if any(neg["match_type"] is None for neg, _ in found):
        lines += ["", "Where the file does not give a negative's match type, it is read as broad, the widest "
                      "reading, so check those by hand."]
    if lists:
        lines += ["", "Negatives in shared lists are not checked yet: this file does not say which campaigns use "
                      "each list."]
    return Check(title, rule, "found", f"{n} {plural(len(found), 'conflict')}{note}", lines)


def _rsa_assets(book, groups, ads, top):
    title, rule = "Headlines and descriptions", "search-rsa-asset-count"
    if ads is None:
        return _missing(title, rule, "ads")
    if not ads:
        return Check(title, rule, "passed", "No live responsive search ads", [])
    short = [a for a in ads if len(a["headlines"]) < RSA_MAX_HEADLINES or len(a["descriptions"]) < RSA_MAX_DESCRIPTIONS]
    few = sum(1 for a in ads if len(a["headlines"]) < RSA_FEW_HEADLINES)
    if not short:
        return Check(title, rule, "passed", "Passed", [])
    s = book.count("live responsive search ads with empty headline or description slots", len(short))
    total = book.count("live responsive search ads", len(ads))
    slots = book.count("headline slots in a responsive search ad (Google)", RSA_MAX_HEADLINES, "rule")
    lines = [f"Google: a responsive search ad holds up to {slots} headlines and {RSA_MAX_DESCRIPTIONS} descriptions, "
             "and filling them gives the system more combinations to test. Optmyzr's open audit fails ads with "
             f"fewer than {RSA_FEW_HEADLINES} headlines; here {book.count('live ads under that line', few)} "
             f"{plural(few, 'ad is', 'ads are')} under it. Adalysis warns that a full ad makes more combinations "
             "than a small account can test, so fill slots with genuinely different messages.", "",
             "| Ad group | Headlines | Descriptions |", "|---|---|---|"]
    for a in sorted(short, key=lambda a: len(a["headlines"]))[:top]:
        g = groups[a["ad_group_id"]]["name"]
        h = book.count(f"headlines in an ad in {g}", len(a["headlines"]), "", g)
        d = book.count(f"descriptions in an ad in {g}", len(a["descriptions"]), "", g)
        lines.append(f"| {esc(g)} | {h} | {d} |")
    return Check(title, rule, "found", f"{s} of {total} ads", lines)


def _rsa_per_group(book, groups, ads, top):
    title, rule = "Ads per ad group", "search-rsa-per-ad-group"
    if ads is None:
        return _missing(title, rule, "ads")
    per = Counter(a["ad_group_id"] for a in ads)
    thin = [g for g in groups.values() if per[g["id"]] < MIN_RSAS_PER_AD_GROUP]
    if not thin:
        return Check(title, rule, "passed", "Passed", [])
    n = book.count("live ad groups with fewer than 2 responsive search ads", len(thin))
    lines = [f"Google: run at least {MIN_RSAS_PER_AD_GROUP} responsive search ads rated Good or Excellent in every "
             "ad group (3 at most), so the system can compare them.", "",
             "| Ad group | Live responsive search ads |", "|---|---|"]
    for g in sorted(thin, key=lambda g: per[g["id"]])[:top]:
        v = book.count(f"live responsive search ads in {g['name']}", per[g["id"]], "", g["name"])
        lines.append(f"| {esc(g['name'])} | {v} |")
    return Check(title, rule, "found", f"{n} {plural(len(thin), 'ad group')}", lines)


def _pinning(book, ads):
    title, rule = "Pinning", "search-rsa-pinning"
    if ads is None:
        return _missing(title, rule, "ads")
    lone = full = 0
    for a in ads:
        pins = Counter(h["pin"] for h in a["headlines"] if h["pin"])
        lone += any(v == 1 for v in pins.values())
        full += bool(a["headlines"]) and all(h["pin"] for h in a["headlines"])
    if not lone and not full:
        return Check(title, rule, "passed", "Passed", [])
    ln = book.count("ads with a position pinned to a single headline", lone)
    fn = book.count("ads with every headline pinned", full)
    lines = [f"{ln} {plural(lone, 'ad pins', 'ads pin')} a position to a single headline, and {fn} "
             f"{plural(full, 'ad pins', 'ads pin')} every headline. Google: pin only when you must, and then pin "
             "2 or 3 headlines to the same position so the system still has a choice. Optmyzr's data found fully "
             "pinned ads had the worst cost per conversion. Both sides are under \"Where Google and "
             "practitioners disagree\"."]
    return Check(title, rule, "found", f"{ln} with a lone pin, {fn} fully pinned", lines)


def _singles(book, groups, kws, top):
    title, rule = "Single-keyword ad groups", "search-structure-themed-ad-groups"
    if not kws:
        return _missing(title, rule, "keywords")
    per = Counter(k["ad_group_id"] for k in kws)
    singles = [g for g in groups.values() if per[g["id"]] == 1]
    if not singles:
        return Check(title, rule, "passed", "Passed", [])
    n = book.count("live ad groups with a single keyword", len(singles))
    lines = ["Google: group keywords into tightly themed ad groups, and fold single-keyword ad groups into "
             "themed ones so Smart Bidding learns from pooled data. Restructure deliberately: moving keywords "
             "resets their history.", "", "| Ad group | Live keywords |", "|---|---|"]
    for g in singles[:top]:
        v = book.count(f"live keywords in {g['name']}", 1, "", g["name"])
        lines.append(f"| {esc(g['name'])} | {v} |")
    return Check(title, rule, "found", f"{n} {plural(len(singles), 'ad group')}", lines)


def _rarely_served(book, groups, kws, top):
    title, rule = "Keywords that rarely serve", "search-structure-cleanup"
    if not kws or all(k["serving"] is None for k in kws):
        return _missing(title, rule, "keyword serving status")
    rare = [k for k in kws if k["serving"] == "RARELY_SERVED"]
    if not rare:
        return Check(title, rule, "passed", "Passed", [])
    n = book.count("live keywords Google marks as rarely served", len(rare), "")
    share = book.pct("share of live keywords that rarely serve", len(rare) / len(kws) * 100, "")
    one = len(rare) == 1
    lines = [f"{n} of {book.count('live keywords', len(kws), '')} live keywords ({share}) "
             f"{'is' if one else 'are'} marked low search volume, so {'it almost never shows' if one else 'they almost never show'}. "
             "Google's structure guide says to clean up non-serving keywords; many practitioners keep them only "
             "when they are the exact wording customers use.", "",
             "| Keyword | Match type | Ad group |", "|---|---|---|"]
    for k in rare[:top]:
        _named(book, k["text"], groups[k["ad_group_id"]]["name"])
        lines.append(f"| {esc(k['text'])} | {nice(k['match_type'])} | {esc(groups[k['ad_group_id']]['name'])} |")
    return Check(title, rule, "found", f"{n} {plural(len(rare), 'keyword')} ({share})", lines)


def _quality_parts(book, groups, kws, top):
    title, rule = "Quality Score parts below average", "search-quality-score-diagnostic"
    parts = (("expected_ctr", "Expected CTR"), ("ad_relevance", "Ad relevance"), ("landing_page", "Landing page"))
    if not kws or all(k[p] is None for k in kws for p, _ in parts):
        return _missing(title, rule, "Quality Score parts")
    weak = [k for k in kws if any(k[p] == "BELOW_AVERAGE" for p, _ in parts)]
    if not weak:
        return Check(title, rule, "passed", "Passed", [])
    n = book.count("live keywords with a Quality Score part below average", len(weak), "")
    below = [(label[0].lower() + label[1:], sum(k[p] == "BELOW_AVERAGE" for k in kws)) for p, label in parts]
    counts = ", ".join(f"{label} {book.count('keywords below average on ' + label, v)}" for label, v in below)
    lines = ["Google: use Quality Score's three parts as a diagnostic to find the weak link, not as a number to "
             f"average. Below average here: {counts}. Expected CTR and ad relevance point at the ad copy; "
             "landing page points at the page.", "",
             "| Keyword | Expected CTR | Ad relevance | Landing page |", "|---|---|---|---|"]
    for k in weak[:top]:
        _named(book, k["text"])
        lines.append(f"| {esc(k['text'])} | " + " | ".join(nice(k[p]) for p, _ in parts) + " |")
    return Check(title, rule, "found", f"{n} {plural(len(weak), 'keyword')}", lines)


def _bidding(book, camps, kws):
    title, rule = "Bidding for clicks, not conversions", "bidding-ecpc-deprecated"
    if all(c["bidding"] is None for c in camps.values()):
        return _missing(title, rule, "bid strategies")
    ecpc = [c for c in camps.values() if c["bidding"] == "ENHANCED_CPC" or (c["bidding"] == "MANUAL_CPC" and c["enhanced_cpc"])]
    clicks = [c for c in camps.values() if c["bidding"] in CLICK_BIDDING and c not in ecpc]
    if not ecpc and not clicks:
        return Check(title, rule, "passed", "Passed", [])
    n = book.count("live Search campaigns bidding for clicks", len(ecpc) + len(clicks))
    lines = ["Google stopped Enhanced CPC for Search in March 2025, so those campaigns now run on plain Manual CPC. "
             "Manual CPC and Maximize clicks bid for clicks, not conversions; Google suggests Maximize "
             "conversions or Target CPA once conversion tracking works.", "",
             "| Campaign | Bidding | Live keywords |", "|---|---|---|"]
    for c in ecpc + clicks:
        label = "Enhanced CPC (retired, now Manual CPC)" if c in ecpc else nice(c["bidding"])
        v = book.count(f"live keywords in {c['name']}", sum(k["campaign_id"] == c["id"] for k in kws), "", c["name"])
        lines.append(f"| {esc(c['name'])} | {label} | {v} |")
    return Check(title, rule, "found", f"{n} {plural(len(ecpc) + len(clicks), 'campaign')}", lines)


def _display(book, camps, kws):
    title, rule = "Search campaigns on the Display Network", "struct-settings-consistency"
    if all(c["display_network"] is None for c in camps.values()):
        return _missing(title, rule, "network settings")
    on = [c for c in camps.values() if c["display_network"]]
    if not on:
        return Check(title, rule, "passed", "Passed", [])
    n = book.count("live Search campaigns also showing on the Display Network", len(on))
    lines = ["Practitioners keep Search campaigns off the Display Network: Display clicks are cheaper, convert "
             "differently, and blur the Search numbers. Run Display in its own campaign.", "",
             "| Campaign | Live keywords |", "|---|---|"]
    for c in on:
        v = book.count(f"live keywords in {c['name']}", sum(k["campaign_id"] == c["id"] for k in kws), "", c["name"])
        lines.append(f"| {esc(c['name'])} | {v} |")
    return Check(title, rule, "found", f"{n} {plural(len(on), 'campaign')}", lines)


def _assets(book, camps, assets, top):
    title, rule = "Sitelinks, callouts and snippets", "assets-coverage"
    if assets is None:
        return _missing(title, rule, "assets")
    live = [a for a in assets if a["status"] in (None, "ENABLED")]
    base = Counter(a["type"] for a in live if a["level"] == "ACCOUNT")
    short = []
    for c in camps.values():
        have = base + Counter(a["type"] for a in live if a["level"] == "CAMPAIGN" and a["owner_id"] == c["id"])
        s, co, sn = have["SITELINK"], have["CALLOUT"], have["STRUCTURED_SNIPPET"]
        if s < MIN_SITELINKS or co < MIN_CALLOUTS or sn < MIN_SNIPPETS:
            short.append((c, s, co, sn))
    if not short:
        return Check(title, rule, "passed", "Passed", [])
    n = book.count("live Search campaigns short of sitelinks, callouts or snippets", len(short))
    lines = [f"Google asks for at least {MIN_SITELINKS} sitelinks (6 for busy campaigns); Optmyzr's audit also wants "
             f"{MIN_CALLOUTS} callouts and {MIN_SNIPPETS} structured snippet per Search campaign. Account-level assets "
             "count for every campaign.", "",
             "| Campaign | Sitelinks | Callouts | Structured snippets |", "|---|---|---|---|"]
    for c, s, co, sn in short[:top]:
        cells = [book.count(f"{kind} available to {c['name']}", v, "", c["name"])
                 for kind, v in (("sitelinks", s), ("callouts", co), ("structured snippets", sn))]
        lines.append(f"| {esc(c['name'])} | " + " | ".join(cells) + " |")
    return Check(title, rule, "found", f"{n} {plural(len(short), 'campaign')}", lines)


def _location(book, camps):
    title, rule = "Location option", "set-location-presence"
    kinds = Counter(c["geo_target_type"] for c in camps.values() if c["geo_target_type"])
    if not kinds:
        return _missing(title, rule, "location settings")
    parts = ", ".join(f"{nice(k)} {book.count(f'live Search campaigns set to {nice(k)}', v)}" for k, v in kinds.most_common())
    return Check(title, rule, "info", f"{parts} (see below)", [])


def _disagreements(book, ads, camps, kws):
    out = []
    if ads:
        strength = Counter(a["strength"] for a in ads if a["strength"])
        mix = ", ".join(f"{nice(s)} {book.count(f'live ads rated {nice(s)}', v)}" for s, v in strength.most_common())
        out.append(f"- **Ad Strength.** Google says moving an ad from Poor to Excellent brings more conversions. "
                   f"Optmyzr's study of thousands of accounts found Excellent ads had the worst cost per conversion "
                   f"and Average ones the best. Judge ads on cost per conversion and conversions per impression. "
                   + (f"Your live ads: {mix}." if mix else "This file has no Ad Strength ratings."))
        out.append("- **Pinning.** Google says most advertisers should not pin. Optmyzr found partial pinning had the "
                   "best cost per conversion and full pinning the worst.")
    kinds = Counter(c["geo_target_type"] for c in camps.values() if c["geo_target_type"])
    if kinds:
        mix = ", ".join(f"{nice(k)} {book.count(f'live Search campaigns set to {nice(k)}', v)}" for k, v in kinds.most_common())
        out.append("- **Location.** Google's default and recommendation is Presence or interest, which also reaches "
                   "people who only searched about your area. Optmyzr's audit fails accounts that mostly use it and "
                   f"wants Presence: people in or regularly in the area. Your live Search campaigns: {mix}.")
    types = Counter(k["match_type"] for k in kws if k["match_type"])
    if types:
        mix = ", ".join(f"{nice(t)} {book.count(f'live keywords in {nice(t)} match', v, '')}" for t, v in types.most_common())
        out.append("- **Match types.** Google suggests simplifying to broad match under Smart Bidding. Optmyzr's study "
                   "of tens of thousands of accounts found exact match the most efficient, phrase the workhorse, and "
                   f"broad best for finding new searches. Your live keywords: {mix}.")
    return ["", "## Where Google and practitioners disagree", ""] + out if out else []


def _header(book, data):
    meta = data.get("meta", {})
    bits = [f"Source: `{os.path.basename(data.get('source', ''))}`"]
    if meta.get("account"):
        _named(book, meta["account"])
        bits.append(esc(meta["account"]))
    try:
        d = date.fromisoformat(str(meta.get("captured", "")))
        bits.append(f"captured {d:%B} {d.day}, {d.year}")
    except ValueError:
        pass
    bits.append(f"currency {book.currency}")
    return [f"# {TITLE}", "", " · ".join(bits), "",
            "_Built by OpenPPC, read-only: computed from this file alone, with no network calls._", ""]


def evaluate(data, brand=None, top=25):
    """Run every check. Returns (checks, book, live), where live counts what was judged."""
    book = FactBook((data.get("meta", {}).get("currency") or "USD").upper())
    camps, groups, kws, ads_ = _live(data)
    ads = None if data["ads"] is None else ads_
    checks = [_broad(book, camps, kws, top), _brand_mix(book, camps, kws, brand, top), _duplicates(book, groups, kws, top),
              _conflicts(book, camps, groups, kws, data["negatives"], top), _rsa_assets(book, groups, ads, top),
              _rsa_per_group(book, groups, ads, top), _pinning(book, ads), _singles(book, groups, kws, top),
              _rarely_served(book, groups, kws, top), _quality_parts(book, groups, kws, top),
              _bidding(book, camps, kws), _display(book, camps, kws), _assets(book, camps, data["assets"], top),
              _location(book, camps)]
    return checks, book, (camps, groups, kws, ads)


def run(data, brand=None, top=25, **_):
    checks, book, (camps, groups, kws, ads) = evaluate(data, brand, top)
    judged = [c for c in checks if c.status in ("found", "passed")]
    found = [c for c in judged if c.status == "found"]
    out = _header(book, data)
    counts = [book.count("live Search campaigns", len(camps)), book.count("live ad groups", len(groups)),
              book.count("live keywords", len(kws), ""), book.count("live responsive search ads", len(ads or []))]
    out += ["## Summary", "",
            f"Live Search: {counts[0]} {plural(len(camps), 'campaign')}, {counts[1]} {plural(len(groups), 'ad group')}, "
            f"{counts[2]} {plural(len(kws), 'keyword')} and {counts[3]} responsive search {plural(len(ads or []), 'ad')}.", "",
            f"**{book.count('checks that found something', len(found))} of {book.count('checks run', len(judged))} "
            f"checks found something.**", "", "| Check | Result | Rule |", "|---|---|---|"]
    out += [f"| {c.title} | {c.summary} | `{c.rule}` |" for c in checks]
    for c in found:
        out += ["", f"### {c.title}", ""] + c.lines
    out += _disagreements(book, ads, camps, kws)
    out += ["", "## How this was computed", "",
            "- Live means the keyword or ad, its ad group and its campaign are all enabled. Only Search campaigns "
            "are judged; Performance Max and other campaign types are left out.",
            "- Every check is a row in OpenPPC's rulebook (`rulebook/rules.csv`); the Rule column is its id, with "
            "the source and the exact threshold.",
            "- Negatives are compared with your keyword text: an exact negative must match the whole keyword, a "
            "phrase negative its words in order, a broad negative every word in any order.",
            "- A check marked \"not in this file\" was not run: the file lacks what it needs. It is not a pass."]
    return out, book

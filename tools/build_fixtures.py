"""Build tests/fixtures/: one small export per real-world variant the readers must handle, and
examples/editor_acme.csv, the sample account snapshot as Google Ads Editor would export it.

Run it after changing a recipe here:

    python tools/build_fixtures.py

tests/test_fixtures.py fails when a file on disk differs from its recipe. Every account,
search term and figure is invented (CONTRIBUTING: never commit real client data), but each
file is shaped like the real thing: title and date lines above the header, the account's
number format, the encoding Google or Excel writes, and the Total rows at the bottom.
"""
import csv
import io
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures"
EXAMPLES = ROOT / "examples"

HEADER = ["Search term", "Match type", "Added/Excluded", "Campaign", "Ad group", "Clicks", "Impr.", "Currency code",
          "Cost", "Conversions"]
SEARCH, WATER = "Birch Lane | Search", "Birch Lane | Water heaters"
# search term, match type, added/excluded, campaign, ad group, clicks, impressions, cost, conversions
BASE = [
    ("emergency plumber", "Exact match", "Added", SEARCH, "Core", 184, 2105, 1254.4, 27),
    ("plumber near me", "Phrase match", "Added", SEARCH, "Core", 151, 2390, 1006.5, 19),
    ("water heater repair", "Phrase match", "Added", WATER, "Repair", 66, 905, 512.25, 9),
    ("tankless water heater install", "Broad match", "None", WATER, "Install", 23, 340, 287.5, 3),
    ("burst pipe repair", "Broad match", "None", SEARCH, "Core", 37, 488, 251.6, 5),
    ("free plumbing quote", "Broad match", "None", SEARCH, "Core", 44, 610, 331.0, 0),
    ("plumbing apprenticeship", "Broad match", "None", SEARCH, "Core", 26, 395, 174.2, 0),
    ("diy drain unblocker", "Broad match", "None", SEARCH, "Drains", 21, 450, 117.6, 0),
    ("water heater parts", "Broad match", "None", WATER, "Repair", 12, 260, 78.0, 0),
    ("drain camera rental", "Broad match", "None", SEARCH, "Drains", 8, 140, 41.6, 0),
    ("gas leak plumber", "Phrase match", "None", SEARCH, "Core", 19, 230, 163.4, 4),
    ("toilet installation", "Broad match", "None", SEARCH, "Core", 14, 205, 92.4, 2),
    ("plumber salary", "Broad match", "None", SEARCH, "Core", 6, 120, 25.2, 0),
    ("copper pipe price", "Broad match", "None", SEARCH, "Core", 4, 95, 11.6, 0),
]
JUNE, JULY = ("June 1, 2026", "June 30, 2026"), ("July 1, 2026", "July 31, 2026")


def _grouped(whole, sep, indian):
    digits = str(whole)
    if not indian or len(digits) <= 3:
        return f"{whole:,}".replace(",", sep)
    head, groups = digits[:-3], [digits[-3:]]
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return sep.join(([head] if head else []) + groups)


def number(value, dp, thousands=",", decimal=".", indian=False):
    """value as an account in that locale prints it: number(1234.5, 2, '.', ',') -> '1.234,50'."""
    whole, _, frac = f"{abs(value):.{dp}f}".partition(".")
    text = _grouped(int(whole), thousands, indian) + (decimal + frac if dp else "")
    return ("-" if value < 0 else "") + text


EN = {"thousands": ",", "decimal": "."}
LOCALES = {
    "en-US": EN,
    "de-DE": {"thousands": ".", "decimal": ","},
    "fr-FR": {"thousands": "\u202f", "decimal": ","},   # Google prints a narrow no-break space
    "en-IN": {"thousands": ",", "decimal": ".", "indian": True},
}


def search_terms(rows, locale="en-US", delimiter=",", period=JULY, currency="USD", money=("", ""),
                 header=HEADER, conv_dp=2, extra=None):
    """A Search terms report as text. rows are BASE-shaped; extra adds columns: {name: [value per row]}."""
    fmt = LOCALES[locale]
    head = list(header) + list(extra or {})
    buf = io.StringIO()
    out = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    buf.write(f"Search terms report\n{period[0]} - {period[1]}\n")
    out.writerow(head)
    def cash(v):
        return f"{money[0]}{number(v, 2, **fmt)}{money[1]}"
    for i, (term, mt, added, camp, group, clicks, impr, cost, conv) in enumerate(rows):
        out.writerow([term, mt, added, camp, group, number(clicks, 0, **fmt), number(impr, 0, **fmt), currency,
                      cash(cost), number(conv, conv_dp, **fmt)] + [v[i] for v in (extra or {}).values()])
    clicks, impr = sum(r[5] for r in rows), sum(r[6] for r in rows)
    cost, conv = sum(r[7] for r in rows), sum(r[8] for r in rows)
    total = ["Total: Search terms", "", "", "", "", number(clicks, 0, **fmt), number(impr, 0, **fmt), currency,
             cash(cost), number(conv, conv_dp, **fmt)] + ["" for _ in (extra or {})]
    out.writerow(total)
    return buf.getvalue()


def _scaled(rows, factor):
    return [(t, m, a, c, g, round(cl * factor), round(im * factor), round(co * factor, 2), round(cv * factor))
            for t, m, a, c, g, cl, im, co, cv in rows]


def _fractional():
    rng = random.Random(20260701)
    rows = []
    for i in range(120):
        clicks = rng.randint(1, 60)
        conv = round(rng.choice([0, 0, 0, 0.33, 0.5, 1, 1.67, 2.25, 3.5]) * (1 + clicks // 30), 2)
        rows.append((f"plumbing term {i:03d}", rng.choice(["Broad match", "Phrase match", "Exact match"]), "None",
                     rng.choice([SEARCH, WATER]), "Core", clicks, clicks * rng.randint(8, 20),
                     round(clicks * rng.uniform(2.5, 9.5), 2), conv))
    return rows


MS_HEADER = ["Account name", "Campaign name", "Campaign type", "Ad group", "Search term", "Delivered match type",
             "Impr.", "Clicks", "Spend", "Conv.", "Currency code"]


def microsoft_search_terms(rows):
    """A Microsoft Advertising search terms report, laid out as its downloads are documented: report lines above the
    header, a Total row and a copyright line under the table. Not copied from a real file."""
    buf = io.StringIO()
    out = csv.writer(buf, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    for line in ("Report Name: Search terms report", "Report Time: 7/1/2026,7/31/2026",
                 "Time Zone: (GMT-05:00) Eastern Time (US & Canada)", "Report Aggregation: Summary",
                 "Report Filter: ", "Potential Incomplete Data: false", f"Rows: {len(rows)}"):
        out.writerow([line])
    buf.write("\r\n")
    out.writerow(MS_HEADER)
    for term, mt, _, camp, group, clicks, impr, cost, conv in rows:
        kind = "Search & content" if camp == WATER else "Search"
        out.writerow(["Birch Lane", camp, kind, group, term, mt.replace(" match", ""), impr, clicks, f"{cost:.2f}",
                      conv, "USD"])
    out.writerow(["Total", "", "", "", "", "", sum(r[6] for r in rows), sum(r[5] for r in rows),
                  f"{sum(r[7] for r in rows):.2f}", sum(r[8] for r in rows), ""])
    buf.write("\r\n")
    out.writerow(["©2026 Microsoft Corporation. All rights reserved. "])
    return buf.getvalue()


META_HEADER = ["Reporting starts", "Reporting ends", "Campaign name", "Ad set name", "Ad set delivery",
               "Attribution setting", "Results", "Result indicator", "Reach", "Impressions", "Cost per result",
               "Amount spent (EUR)", "Link clicks"]
LEAD = "actions:offsite_conversion.fb_pixel_lead"
LEADS, RETARGET = "Birch Lane | Leads", "Birch Lane | Retargeting"
# campaign, ad set, reach, impressions, amount spent, link clicks, results (None: Meta leaves the cell blank)
META_BASE = [
    (LEADS, "Homeowners 30-65", 18250, 41200, 812.4, 655, 31),
    (LEADS, "Lookalike 1%", 22410, 52880, 934.15, 702, 27),
    (LEADS, "Advantage+ audience", 30120, 77650, 1105.6, 811, 22),
    (RETARGET, "Site visitors 30d", 4120, 15400, 286.9, 240, 14),
    (RETARGET, "Video viewers", 2050, 6100, 74.35, None, None),
]


def meta_ads(rows, start, end, indicators=None):
    """A Meta Ads Manager export of ad sets, as Ads Reporting writes it: one header row, a summary row for the
    whole file first, ISO dates on every row, blank cells for none. indicators: each row's Result indicator."""
    buf = io.StringIO()
    out = csv.writer(buf, lineterminator="\n")
    out.writerow(META_HEADER)
    spent = round(sum(r[4] for r in rows), 2)
    results = sum(r[6] or 0 for r in rows)
    out.writerow([start, end, "", "", "", "7-day click or 1-day view", "" if indicators else results, "",
                  "", sum(r[3] for r in rows), "", f"{spent:.2f}", sum(r[5] or 0 for r in rows)])
    for i, (camp, adset, reach, impr, cost, clicks, res) in enumerate(rows):
        out.writerow([start, end, camp, adset, "active", "7-day click or 1-day view", "" if res is None else res,
                      (indicators or {}).get(i, LEAD), reach, impr, f"{cost / res:.2f}" if res else "", f"{cost:.2f}",
                      "" if clicks is None else clicks])
    return buf.getvalue()


def _meta_scaled(rows, factor):
    return [(c, a, round(r * factor), round(i * factor), round(s * factor, 2), cl and round(cl * factor),
             res and round(res * factor)) for c, a, r, i, s, cl, res in rows]


EDITOR_HEADER = ["Campaign", "Campaign Type", "Networks", "Bid Strategy Type", "Enhanced CPC", "Targeting method",
                 "Campaign Status", "Ad Group", "Ad Group Status", "Keyword", "Criterion Type", "Status",
                 "Quality score", "Expected CTR", "Ad relevance", "Landing page experience", "Ad type",
                 "Headline 1", "Headline 1 position", "Headline 2", "Headline 3", "Description 1", "Description 2",
                 "Ad strength", "Link Text", "Callout text"]
BRAND = "Birch Lane | Brand"


def editor_export():
    """A Google Ads Editor whole-account export: UTF-16, tab separated, one row per item."""
    rows = [
        {"Campaign": SEARCH, "Campaign Type": "Search", "Networks": "Google search;Search Partners;Display Network",
         "Bid Strategy Type": "Manual CPC", "Enhanced CPC": "Disabled",
         "Targeting method": "People in or regularly in your included locations", "Campaign Status": "Enabled"},
        {"Campaign": BRAND, "Campaign Type": "Search", "Networks": "Google search",
         "Bid Strategy Type": "Maximize conversions",
         "Targeting method": "Presence or interest: People in, regularly in, or who've shown interest in your "
                             "included locations", "Campaign Status": "Enabled"},
        {"Campaign": SEARCH, "Ad Group": "Core", "Ad Group Status": "Enabled"},
        {"Campaign": SEARCH, "Ad Group": "Drains", "Ad Group Status": "Enabled"},
        {"Campaign": SEARCH, "Ad Group": "Old offers", "Ad Group Status": "Paused"},
        {"Campaign": BRAND, "Ad Group": "Brand", "Ad Group Status": "Enabled"},
        {"Campaign": SEARCH, "Ad Group": "Core", "Keyword": "emergency plumber", "Criterion Type": "Exact",
         "Status": "Enabled", "Quality score": "7", "Expected CTR": "Above average", "Ad relevance": "Average",
         "Landing page experience": "Average"},
        {"Campaign": SEARCH, "Ad Group": "Core", "Keyword": "plumber near me", "Criterion Type": "Broad",
         "Status": "Enabled", "Quality score": "4", "Expected CTR": "Below average", "Ad relevance": "Average",
         "Landing page experience": "Below average"},
        {"Campaign": SEARCH, "Ad Group": "Core", "Keyword": "drain cleaning", "Criterion Type": "Phrase",
         "Status": "Enabled"},
        {"Campaign": SEARCH, "Ad Group": "Drains", "Keyword": "\"drain cleaning\"", "Status": "Enabled"},
        {"Campaign": SEARCH, "Ad Group": "Drains", "Keyword": "[blocked drain]", "Status": "Low search volume"},
        {"Campaign": SEARCH, "Ad Group": "Old offers", "Keyword": "spring plumbing deal", "Criterion Type": "Broad",
         "Status": "Enabled"},
        {"Campaign": BRAND, "Ad Group": "Brand", "Keyword": "birch lane plumbing", "Criterion Type": "Exact",
         "Status": "Enabled"},
        {"Campaign": SEARCH, "Keyword": "jobs", "Criterion Type": "Campaign Negative Broad", "Status": "Enabled"},
        {"Campaign": SEARCH, "Ad Group": "Drains", "Keyword": "plumber", "Criterion Type": "Negative Phrase",
         "Status": "Enabled"},
        {"Campaign": SEARCH, "Ad Group": "Core", "Ad type": "Responsive search ad", "Status": "Enabled",
         "Headline 1": "Emergency Plumber 24/7", "Headline 1 position": "1", "Headline 2": "Licensed & Insured",
         "Headline 3": "Book Online Today", "Description 1": "Fast local plumbers, upfront prices.",
         "Description 2": "Call now for same-day service.", "Ad strength": "Poor"},
        {"Campaign": SEARCH, "Ad Group": "Drains", "Ad type": "Responsive search ad", "Status": "Enabled",
         "Headline 1": "Blocked Drain?", "Headline 2": "Drain Cleaning Experts", "Headline 3": "Same-Day Service",
         "Description 1": "Drains cleared fast.", "Ad strength": "Average"},
        {"Campaign": SEARCH, "Link Text": "Water heaters", "Status": "Enabled"},
        {"Campaign": SEARCH, "Link Text": "Book a visit", "Status": "Enabled"},
        {"Campaign": SEARCH, "Callout text": "Licensed & insured", "Status": "Enabled"},
        {"Campaign": SEARCH, "Callout text": "No call-out fee", "Status": "Enabled"},
    ]
    buf = io.StringIO()
    out = csv.writer(buf, delimiter="\t", lineterminator="\r\n")
    out.writerow(EDITOR_HEADER)
    for r in rows:
        out.writerow([r.get(c, "") for c in EDITOR_HEADER])
    return buf.getvalue()


SNAPSHOT_HEADER = (["Campaign", "Campaign Type", "Networks", "Bid Strategy Type", "Enhanced CPC", "Targeting method",
                    "Budget", "Budget type", "Campaign Status", "Ad Group", "Ad Group Status", "Keyword",
                    "Criterion Type", "Status", "Approval Status", "Quality score", "Expected CTR", "Ad relevance",
                    "Landing page experience", "Ad type"]
                   + [f"Headline {i}{p}" for i in range(1, 16) for p in ("", " position")]
                   + [f"Description {i}{p}" for i in range(1, 5) for p in ("", " position")]
                   + ["Ad strength", "Link Text", "Callout text", "Header"])
TARGETING = {"PRESENCE": "People in or regularly in your included locations",
             "PRESENCE_OR_INTEREST": "People in, regularly in, or who've shown interest in your included locations"}
WORDS = {"APPROVED_LIMITED": "Approved (limited)", "PERFORMANCE_MAX": "Performance Max",
         "MANUAL_CPC": "Manual CPC"}
ASSET_CELL = {"SITELINK": ("Link Text", "Sitelink"), "CALLOUT": ("Callout text", "Callout"),
              "STRUCTURED_SNIPPET": ("Header", "Services")}


def _word(value):
    """'MAXIMIZE_CONVERSIONS' -> 'Maximize conversions', as Editor writes it."""
    return WORDS.get(value, str(value).replace("_", " ").capitalize()) if value else ""


def _pin(pin):
    return pin.rsplit("_", 1)[-1] if pin else ""


def editor_from_snapshot(snap):
    """The Google Ads Editor export of an account snapshot: UTF-16, tab separated, names instead of ids. Shared
    negative lists are left out, as Editor exports them on their own."""
    camps = {c["id"]: c for c in snap["campaigns"]}
    groups = {g["id"]: g for g in snap["ad_groups"]}
    rows = []
    for c in snap["campaigns"]:
        display = c.get("display_network")
        rows.append({"Campaign": c["name"], "Campaign Type": _word(c["channel"]),
                     "Networks": "" if display is None else "Google search;Search Partners"
                     + (";Display Network" if display else ""),
                     "Bid Strategy Type": _word(c["bidding"]),
                     "Enhanced CPC": "Enabled" if c.get("enhanced_cpc") else "Disabled",
                     "Targeting method": TARGETING.get(c["geo_target_type"], c["geo_target_type"]),
                     "Budget": f"{c['budget']:,.2f}" if c.get("budget") else "",
                     "Budget type": "Daily" if c.get("budget") else "", "Campaign Status": _word(c["status"])})
    for g in snap["ad_groups"]:
        rows.append({"Campaign": camps[g["campaign_id"]]["name"], "Ad Group": g["name"],
                     "Ad Group Status": _word(g["status"])})

    def where(group_id):
        g = groups[group_id]
        return {"Campaign": camps[g["campaign_id"]]["name"], "Ad Group": g["name"]}

    for k in snap["keywords"]:
        rows.append({**where(k["ad_group_id"]), "Keyword": k["text"], "Criterion Type": _word(k["match_type"]),
                     "Status": "Low search volume" if k.get("serving") == "RARELY_SERVED" else _word(k["status"]),
                     "Approval Status": _word(k.get("approval")), "Quality score": k.get("quality_score") or "",
                     "Expected CTR": _word(k.get("expected_ctr")), "Ad relevance": _word(k.get("ad_relevance")),
                     "Landing page experience": _word(k.get("landing_page"))})
    for n in snap["negatives"]:
        match = _word(n["match_type"])
        if n["level"] == "CAMPAIGN":
            rows.append({"Campaign": camps[n["owner_id"]]["name"], "Keyword": n["text"],
                         "Criterion Type": f"Campaign Negative {match}".strip(), "Status": "Enabled"})
        elif n["level"] == "AD_GROUP":
            rows.append({**where(n["owner_id"]), "Keyword": n["text"], "Criterion Type": f"Negative {match}".strip(),
                         "Status": "Enabled"})
    for a in snap["ads"]:
        row = {**where(a["ad_group_id"]), "Ad type": _word(a["type"]), "Status": _word(a["status"]),
               "Approval Status": _word(a.get("approval")), "Ad strength": _word(a.get("strength"))}
        for kind, items in (("Headline", a["headlines"]), ("Description", a["descriptions"])):
            for i, item in enumerate(items, 1):
                row[f"{kind} {i}"], row[f"{kind} {i} position"] = item["text"], _pin(item["pin"])
        rows.append(row)
    seen = {}
    for s in snap["assets"]:
        column, text = ASSET_CELL[s["type"]]
        seen[column] = seen.get(column, 0) + 1
        owner = camps[s["owner_id"]]["name"] if s["level"] == "CAMPAIGN" else ""
        rows.append({"Campaign": owner, column: f"{text} {seen[column]}", "Status": _word(s["status"])})
    buf = io.StringIO()
    out = csv.writer(buf, delimiter="\t", lineterminator="\r\n")
    out.writerow(SNAPSHOT_HEADER)
    for r in rows:
        out.writerow([r.get(c, "") for c in SNAPSHOT_HEADER])
    return buf.getvalue()


def examples():
    """{file name: bytes} for examples/: the samples made from another sample."""
    snap = json.loads((EXAMPLES / "account_structure_acme.json").read_text(encoding="utf-8"))
    return {"editor_acme.csv": editor_from_snapshot(snap).encode("utf-16")}


def fixtures():
    """{file name: bytes}."""
    de = search_terms(BASE, "de-DE", ";", currency="EUR")
    fr = search_terms(BASE, "fr-FR", ";", currency="EUR", money=("", "\u00a0€"))
    rupees = [(t, m, a, c, g, cl, im, round(co * 95, 2), cv) for t, m, a, c, g, cl, im, co, cv in BASE]
    india = search_terms(rupees, "en-IN", currency="INR", money=("₹", ""))
    cafe = [("plombier café montréal", "Broad match", "None", SEARCH, "Core", 31, 400, 154.0, 0)] + BASE[:5]
    renamed = ["Search term", "Search term match type", "Added/Excluded", "Campaign", "Ad group", "Clicks",
               "Impressions", "Currency", "Cost", "Conversions"]
    pmax = [(t, "--", "None", "Birch Lane | PMax", "--", cl, im, co, cv) for t, _, _, _, _, cl, im, co, cv in BASE]
    dupes = BASE[:4] + [("leaking tap repair", "Broad match", "None", SEARCH, g, 3, 40, 15.0, 0)
                        for g in ("Core", "Drains", "Taps")]
    zero = [(t, m, a, c, g, cl, im, 0.0, 0) for t, m, a, c, g, cl, im, _, _ in BASE[:6]]
    no_waste = [r for r in BASE if r[8] > 0]
    german = ("Suchbegriffbericht\n1. Juli 2026 - 31. Juli 2026\n"
              "Suchbegriff;Keyword-Option;Kampagne;Anzeigengruppe;Klicks;Impr.;Kosten;Conversions\n"
              "notdienst klempner;Exakt;Birch Lane | Search;Core;184;2.105;1.254,40;27,00\n")
    mixed = search_terms(BASE[:3]).replace("1,254.40", "1254,40")  # one cell re-typed in a German spreadsheet
    return {
        "search_terms_de.csv": de.encode("utf-8"),
        "search_terms_fr.csv": fr.encode("utf-8"),
        "search_terms_en_in.csv": india.encode("utf-8"),
        "search_terms_utf16.csv": search_terms(BASE, delimiter="\t").encode("utf-16"),
        "search_terms_cp1252.csv": search_terms(cafe).encode("cp1252"),
        "search_terms_renamed.csv": search_terms(BASE, header=renamed).encode("utf-8"),
        "search_terms_pmax.csv": search_terms(pmax, extra={"Campaign type": ["Performance Max"] * len(pmax)})
        .encode("utf-8"),
        "search_terms_fractional.csv": search_terms(_fractional()).encode("utf-8"),
        "search_terms_duplicates.csv": search_terms(dupes).encode("utf-8"),
        "search_terms_zero_cost.csv": search_terms(zero).encode("utf-8"),
        "search_terms_no_waste.csv": search_terms(no_waste).encode("utf-8"),
        "search_terms_june.csv": search_terms(_scaled(BASE, 0.8), period=JUNE).encode("utf-8"),
        "search_terms_july.csv": search_terms(BASE, period=JULY).encode("utf-8"),
        "search_terms_german_headers.csv": german.encode("utf-8"),
        "search_terms_mixed_formats.csv": mixed.encode("utf-8"),
        "editor_export.csv": editor_export().encode("utf-16"),
        "search_terms_microsoft.csv": microsoft_search_terms(BASE).encode("utf-8-sig"),
        "meta_june.csv": meta_ads(_meta_scaled(META_BASE, 0.85), "2026-06-01", "2026-06-30").encode("utf-8"),
        "meta_july.csv": meta_ads(META_BASE, "2026-07-01", "2026-07-31").encode("utf-8"),
        "meta_mixed_results.csv": meta_ads(META_BASE, "2026-07-01", "2026-07-31",
                                           {3: "actions:link_click", 4: "video_thruplay_watched_actions"})
        .encode("utf-8"),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in fixtures().items():
        (OUT / name).write_bytes(data)
    for name, data in examples().items():
        (EXAMPLES / name).write_bytes(data)
    print(f"wrote {len(fixtures())} files to {OUT.relative_to(ROOT)} and {len(examples())} to "
          f"{EXAMPLES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate the example exports. Every name and number here is invented.

    python examples/make_samples.py

The files mimic real Google Ads UI downloads: a title line, a date-range line, the
header, the rows, and Google's own Total lines at the bottom (which OpenPPC ignores).
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).parent
PERIOD = "July 1, 2026 - July 31, 2026"

# search term, match type, added/excluded, campaign, ad group, clicks, impressions, cost, conversions
SEARCH_TERMS = [
    ("plumber near me", "Exact match", "Added", "Search - Plumbing", "Core", 212, 2150, 1361.04, 31),
    ("plumbing services", "Phrase match", "Added", "Search - Plumbing", "Core", 168, 2402, 1008.00, 22),
    ("same day water heater install", "Broad match", "None", "Search - Water Heaters", "Water heaters", 18, 240, 206.00, 5),
    ("drain cleaning near me", "Broad match", "None", "Search - Plumbing", "Drains", 12, 150, 174.00, 3),
    ("leak detection service", "Phrase match", "None", "Search - Plumbing", "Core", 45, 610, 283.50, 6),
    ("toilet repair near me", "Broad match", "None", "Search - Plumbing", "Core", 31, 420, 170.50, 4),
    ("free plumbing estimate", "Broad match", "None", "Search - Plumbing", "Core", 41, 530, 312.00, 0),
    ("plumber jobs hiring", "Broad match", "None", "Search - Plumbing", "Core", 22, 300, 188.00, 0),
    ("how to unclog a drain yourself", "Broad match", "None", "Search - Plumbing", "Core", 19, 410, 121.00, 0),
    ("cheap water heater", "Broad match", "None", "Search - Water Heaters", "Water heaters", 14, 220, 96.00, 1),
    ("water heater replacement cost", "Broad match", "None", "Search - Water Heaters", "Water heaters", 38, 610, 402.80, 2),
    ("plumbing franchise cost", "Broad match", "None", "Search - Plumbing", "Core", 9, 160, 64.80, 0),
    ("sump pump installation", "Phrase match", "None", "Search - Plumbing", "Core", 16, 190, 104.00, 3),
    ("water heater prices", "Phrase match", "Added", "Search - Water Heaters", "Water heaters", 58, 880, 330.60, 7),
    ("sewer line camera inspection", "Broad match", "None", "Search - Plumbing", "Drains", 7, 95, 52.50, 1),
    ("plumbing supply store", "Broad match", "None", "Search - Plumbing", "Core", 11, 260, 48.40, 0),
    ("plumber reviews", "Broad match", "None", "Search - Plumbing", "Core", 6, 85, 33.00, 0),
    ("pvc pipe bulk", "Broad match", "None", "Search - Plumbing", "Core", 5, 140, 17.50, 0),
]

# keyword, match type, campaign, ad group, clicks, impressions, cost, conversions, quality score
KEYWORDS = [
    ("plumber near me", "Exact match", "Search - Plumbing", "Core", 212, 2150, 1361.04, 31, 8),
    ("plumbing services", "Phrase match", "Search - Plumbing", "Core", 168, 2402, 1008.00, 22, 7),
    ("plumbing services", "Broad match", "Search - Plumbing", "Core", 140, 2980, 942.10, 6, 5),
    ("water heater", "Broad match", "Search - Water Heaters", "Water heaters", 96, 1720, 618.40, 5, 4),
    ("water heater prices", "Phrase match", "Search - Water Heaters", "Water heaters", 58, 880, 330.60, 7, 6),
    ("drain cleaning", "Exact match", "Search - Plumbing", "Drains", 24, 260, 190.80, 4, 7),
    ("pipe repair", "Broad match", "Search - Plumbing", "Core", 38, 910, 296.40, 0, 3),
    ("plumbing repair", "Broad match", "Search - Plumbing", "Core", 29, 640, 201.55, 1, 4),
    ("leak detection", "Phrase match", "Search - Plumbing", "Core", 45, 610, 283.50, 6, 6),
    ("pipe replacement", "Broad match", "Search - Plumbing", "Core", 17, 520, 119.00, 0, 2),
    ("faucet installation", "Broad match", "Search - Plumbing", "Core", 8, 150, 44.80, 0, None),
]


def derived(clicks, impressions, cost, conversions):
    ctr = f"{clicks / impressions * 100:.2f}%" if impressions else "--"
    cpc = f"{cost / clicks:.2f}" if clicks else "--"
    cvr = f"{conversions / clicks * 100:.2f}%" if clicks else "--"
    cpa = f"{cost / conversions:.2f}" if conversions else "--"
    return ctr, cpc, cvr, cpa


def total_row(label, rows, clicks_i, impr_i, cost_i, conv_i, width, positions):
    c = sum(r[clicks_i] for r in rows)
    i = sum(r[impr_i] for r in rows)
    s = sum(r[cost_i] for r in rows)
    v = sum(r[conv_i] for r in rows)
    ctr, cpc, cvr, cpa = derived(c, i, s, v)
    out = [""] * width
    out[0] = label
    for key, value in (("clicks", c), ("impr", f"{i:,}"), ("ctr", ctr), ("currency", "USD"), ("cpc", cpc),
                       ("cost", f"{s:,.2f}"), ("cvr", cvr), ("conv", f"{v:.2f}"), ("cpa", cpa)):
        out[positions[key]] = value
    return out


def write_search_terms(path):
    header = ["Search term", "Match type", "Added/Excluded", "Campaign", "Ad group", "Clicks", "Impr.", "CTR",
              "Currency code", "Avg. CPC", "Cost", "Conv. rate", "Conversions", "Cost / conv."]
    pos = {"clicks": 5, "impr": 6, "ctr": 7, "currency": 8, "cpc": 9, "cost": 10, "cvr": 11, "conv": 12, "cpa": 13}
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write("Search terms report\n" + PERIOD + "\n")
        w = csv.writer(f)
        w.writerow(header)
        for term, mt, ae, camp, ag, clicks, impr, cost, conv in SEARCH_TERMS:
            ctr, cpc, cvr, cpa = derived(clicks, impr, cost, conv)
            w.writerow([term, mt, ae, camp, ag, clicks, f"{impr:,}", ctr, "USD", cpc, f"{cost:,.2f}", cvr,
                        f"{conv:.2f}", cpa])
        for label in ("Total: Search terms", "Total: Account"):
            w.writerow(total_row(label, SEARCH_TERMS, 5, 6, 7, 8, len(header), pos))


def write_keywords(path):
    header = ["Keyword status", "Keyword", "Match type", "Campaign", "Ad group", "Clicks", "Impr.", "CTR",
              "Currency code", "Avg. CPC", "Cost", "Conv. rate", "Conversions", "Cost / conv.", "Quality Score"]
    pos = {"clicks": 5, "impr": 6, "ctr": 7, "currency": 8, "cpc": 9, "cost": 10, "cvr": 11, "conv": 12, "cpa": 13}
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write("Search keyword report\n" + PERIOD + "\n")
        w = csv.writer(f)
        w.writerow(header)
        for kw, mt, camp, ag, clicks, impr, cost, conv, qs in KEYWORDS:
            ctr, cpc, cvr, cpa = derived(clicks, impr, cost, conv)
            w.writerow(["Eligible", kw, mt, camp, ag, clicks, f"{impr:,}", ctr, "USD", cpc, f"{cost:,.2f}", cvr,
                        f"{conv:.2f}", cpa, "--" if qs is None else qs])
        w.writerow(total_row("Total: Keywords", [r[4:8] for r in KEYWORDS], 0, 1, 2, 3, len(header), pos))


def write_account(path):
    cur = {"spend": round(sum(r[7] for r in SEARCH_TERMS), 2), "impressions": sum(r[6] for r in SEARCH_TERMS),
           "clicks": sum(r[5] for r in SEARCH_TERMS), "conversions": sum(r[8] for r in SEARCH_TERMS)}
    data = {"meta": {"currency": "USD", "window": "July 2026 vs June 2026",
                     "business_model": "plumbing (lead-gen)"},
            "current": cur,
            "prior": {"spend": 5210.00, "impressions": 11890, "clicks": 760, "conversions": 71}}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_search_terms(HERE / "search_terms_acme.csv")
    write_keywords(HERE / "keywords_acme.csv")
    write_account(HERE / "account_acme.json")
    print("wrote search_terms_acme.csv, keywords_acme.csv, account_acme.json")

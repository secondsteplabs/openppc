"""Industry benchmarks: the public baseline an audit is compared against.

Published averages from WordStream / LocaliQ, "Google Ads Benchmarks 2026": US search
campaigns on Google Ads and Microsoft Ads, April 2025 to March 2026. Use them as a
ballpark, never a target: they are US-only, annual averages that blend both platforms,
and every advertiser defines a conversion differently.
"""

SOURCE = "WordStream / LocaliQ Google Ads Benchmarks 2026, US search, Apr 2025 to Mar 2026"

# key: (display name, CPC, CTR %, conversion rate %, cost per lead)
TABLE = {
    "all": ("All industries", 5.42, 6.64, 8.18, 66.69),
    "animals-pets": ("Animals & Pets", 4.06, 7.49, 16.22, 31.50),
    "apparel": ("Apparel, Fashion & Jewelry", 4.44, 6.64, 4.50, 97.51),
    "arts-entertainment": ("Arts & Entertainment", 1.63, 12.75, 5.91, 26.84),
    "legal": ("Attorneys & Legal Services", 9.87, 5.87, 5.55, 131.63),
    "auto-sales": ("Automotive, For Sale", 2.27, 8.28, 6.01, 44.26),
    "auto-repair": ("Automotive, Repair, Service & Parts", 4.35, 5.56, 15.51, 29.96),
    "beauty": ("Beauty & Personal Care", 4.62, 6.75, 10.35, 39.25),
    "business-services": ("Business Services", 5.87, 6.10, 4.85, 93.69),
    "career": ("Career & Employment", 5.81, 5.88, 3.05, 67.36),
    "dental": ("Dentists & Dental Services", 8.00, 5.66, 10.67, 72.97),
    "education": ("Education & Instruction", 4.81, 7.56, 13.14, 77.48),
    "finance": ("Finance & Insurance", 3.39, 9.83, 2.64, 74.44),
    "furniture": ("Furniture", 3.97, 6.57, 2.99, 106.70),
    "health-fitness": ("Health & Fitness", 6.17, 5.81, 6.94, 67.36),
    "home-services": ("Home & Home Improvement", 8.33, 6.47, 8.05, 90.92),
    "industrial": ("Industrial & Commercial", 5.87, 6.57, 8.20, 75.19),
    "personal-services": ("Personal Services", 7.17, 7.16, 12.34, 54.60),
    "physicians": ("Physicians & Surgeons", 4.76, 6.61, 12.43, 40.04),
    "real-estate": ("Real Estate", 3.22, 7.61, 3.70, 102.51),
    "restaurants": ("Restaurants & Food", 2.05, 6.83, 8.05, 30.57),
    "shopping": ("Shopping, Collectibles & Gifts", 4.14, 8.28, 4.01, 49.40),
    "sports-recreation": ("Sports & Recreation", 2.77, 8.75, 7.69, 44.26),
    "travel": ("Travel", 2.14, 9.32, 5.83, 44.70),
}


def lookup(industry):
    key = (industry or "").strip().lower()
    for k, (name, cpc, ctr, cvr, cpl) in TABLE.items():
        if key in (k, name.lower()):
            return {"key": k, "name": name, "cpc": cpc, "ctr": ctr, "cvr": cvr, "cpl": cpl}
    raise ValueError(f"unknown industry '{industry}'. Try one of: {', '.join(TABLE)}")


def compare(book, industry, cost, clicks, impressions, conversions, currency="USD"):
    """The account's ratios next to the industry's averages, every figure registered in the FactBook.
    Returns the industry row and one dict per metric the data allows. The averages are in US dollars, so an
    account in another currency is compared on rates only (CTR, conversion rate), never on costs."""
    b = lookup(industry)
    dollars = (currency or "USD").upper() == "USD"
    metrics = []
    if clicks and dollars:
        metrics.append(("CPC", cost / clicks, b["cpc"], "money", "cpc", True))
    if impressions:
        metrics.append(("CTR", clicks / impressions * 100, b["ctr"], "pct", "ctr", False))
    if clicks:
        metrics.append(("Conversion rate", conversions / clicks * 100, b["cvr"], "pct", "cvr", False))
    if conversions and dollars:
        metrics.append(("Cost per conversion", cost / conversions, b["cpl"], "money", "cpa", True))
    rows = []
    for name, yours, avg, kind, metric, lower_is_better in metrics:
        if kind == "money":
            y = book.money(f"your {name}", yours, metric)
            a = book.money(f"{b['name']} average {name}", avg, metric)
        else:
            y = book.pct(f"your {name}", yours, metric, dp=2)
            a = book.pct(f"{b['name']} average {name}", avg, metric, dp=2)
        rows.append({"name": name, "yours": yours, "average": avg, "yours_text": y, "average_text": a,
                     "side": "lower" if yours < avg else "higher",
                     "better": (yours < avg) if lower_is_better else (yours > avg)})
    return b, rows


def section(book, industry, cost, clicks, impressions, conversions, currency="USD"):
    """Markdown lines comparing account ratios with the industry averages.
    Every figure is registered in the FactBook, so the checker can trace it."""
    b, rows = compare(book, industry, cost, clicks, impressions, conversions, currency)
    lines = ["", f"## Against the {b['name']} average", "",
             f"_Source: {SOURCE}. A ballpark, not a target: US-only, averaged over a year, and "
             "every advertiser counts conversions differently. The industry figure for cost per "
             "conversion is cost per lead._", ""]
    if (currency or "USD").upper() != "USD":
        lines += [f"_This account is in {currency.upper()} and the averages are in US dollars, so cost per click "
                  "and cost per conversion are left out._", ""]
    if not rows:
        return lines
    lines += ["| Metric | Yours | Industry average | Read |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['name']} | {r['yours_text']} | {r['average_text']} | "
                     f"{r['side']} ({'better' if r['better'] else 'worse'}) |")
    return lines

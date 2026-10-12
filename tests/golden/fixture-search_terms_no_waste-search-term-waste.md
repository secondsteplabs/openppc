<!-- passed: True -->
# Search-term waste audit

Source: `search_terms_no_waste.csv` · July 1, 2026 to July 31, 2026 (31 days) · currency USD

Settings: waste threshold $20.00

_Built by OpenPPC, read-only: computed from this file alone, with no network calls._

## Summary

No search term with zero conversions reached $20.00 in cost. Nothing to cut one term at a time at this threshold.

Account totals in this export: $3,568.05 cost, 494 clicks, 69 conversions, $51.71 per conversion.

## What to do

1. **Add 3 converting terms as keywords.** “burst pipe repair” leads with 5 conversions at $50.32 each.

Search terms in this account convert at much the same rate, so one term's missing conversions are most likely bad luck.

## Worth adding as keywords

These converted at or below the account's $51.71 per conversion and are not keywords yet.

| Search term | Conversions | Cost per conversion | Match type |
|---|---|---|---|
| burst pipe repair | 5 | $50.32 | Broad match |
| gas leak plumber | 4 | $40.85 | Phrase match |
| toilet installation | 2 | $46.20 | Broad match |

## How this was computed

- Waste: search terms with zero conversions and at least $20.00 in cost. Change the threshold with `--min-cost`.
- Each search term's rows are added up first: Google lists a term once for every campaign, ad group and match type it showed in, and a term that converts on any of its rows is never waste.
- Brand terms (from `--brand`, including close misspellings) are never counted as waste.
- Performance Max and other automated campaign types are listed apart from Search, because negatives there only block Search and Shopping ads.
- Words that never convert: words and two-word phrases found in at least 3 search terms that together spent money and got no conversions.
- Chance it's bad: the waste model learns how much this account's search terms differ in conversion rate (a beta-binomial prior fit on your own terms), then works out for each term the chance that it truly converts at less than half the account's rate. 90% is the bar for adding a negative; the dollar threshold only decides what is worth listing.
- Converting, but expensive: cost per conversion above 3 times the account average.
- Worth adding: 2 or more conversions, cost per conversion at or below the account average, and not already added or excluded.
- Totals are recomputed from the rows. The Total lines in Google's export are ignored.
- A conversion is whatever this account counts as one. If that includes small actions such as page views, zero conversions means something weaker here.

---

Number check: every number in this report traces back to your data.

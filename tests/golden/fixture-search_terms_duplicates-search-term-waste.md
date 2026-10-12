<!-- passed: True -->
# Search-term waste audit

Source: `search_terms_duplicates.csv` · July 1, 2026 to July 31, 2026 (31 days) · currency USD

Settings: waste threshold $20.00

_Built by OpenPPC, read-only: computed from this file alone, with no network calls._

## Summary

**1 search term spent $45.00 and never converted.** That is 1.4% of the $3,105.65 total cost in this export, and each one cost at least $20.00.

At the same rate that is $1.45 a day, or $529.84 a year.

None of them has enough clicks for the waste model to be 90% sure it is bad rather than unlucky, so give them more clicks before adding negatives.

Account totals in this export: $3,105.65 cost, 433 clicks, 58 conversions, $53.55 per conversion.

## What to do

1. **Give 1 term more clicks before adding negatives.** Terms in this account convert at much the same rate, so a search term's missing conversions are most likely bad luck.

## Wasted spend, ranked

| Search term | Cost | Clicks | Share of total cost | Chance it's bad | Match type |
|---|---|---|---|---|---|
| leaking tap repair | $45.00 | 9 | 1.4% | 0% | Broad match |

Search terms in this account convert at much the same rate, so one term's missing conversions are most likely bad luck.

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

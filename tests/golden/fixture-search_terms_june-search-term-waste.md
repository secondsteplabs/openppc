<!-- passed: True -->
# Search-term waste audit

Source: `search_terms_june.csv` · June 1, 2026 to June 30, 2026 (30 days) · currency USD

Settings: waste threshold $20.00

_Built by OpenPPC, read-only: computed from this file alone, with no network calls._

## Summary

**6 search terms spent $614.08 and never converted.** That is 17.7% of the $3,477.80 total cost in this export, and each one cost at least $20.00. All 7 search terms with no conversions, whatever they cost, spent $623.36.

At the same rate that is $20.47 a day, or $7,471.31 a year.

None of them has enough clicks for the waste model to be 90% sure it is bad rather than unlucky, so give them more clicks before adding negatives.

Account totals in this export: $3,477.80 cost, 492 clicks, 55 conversions, $63.23 per conversion.

## What to do

1. **Give 6 terms more clicks before adding negatives.** None is proven bad yet. The closest, “free plumbing quote”, is 54% likely bad after 35 clicks. The waste model needs about 85 clicks with no conversion to be 90% sure.
2. **Add 3 converting terms as keywords.** “burst pipe repair” leads with 4 conversions at $50.32 each.

## Wasted spend, ranked

| Search term | Cost | Clicks | Share of total cost | Chance it's bad | Match type |
|---|---|---|---|---|---|
| free plumbing quote | $264.80 | 35 | 7.6% | 54% | Broad match |
| plumbing apprenticeship | $139.36 | 21 | 4.0% | 37% | Broad match |
| diy drain unblocker | $94.08 | 17 | 2.7% | 32% | Broad match |
| water heater parts | $62.40 | 10 | 1.8% | 23% | Broad match |
| drain camera rental | $33.28 | 6 | 1.0% | 19% | Broad match |
| plumber salary | $20.16 | 5 | 0.6% | 17% | Broad match |

Below the $20.00 threshold, 1 more zero-conversion term spent $9.28 in total.

At this account's 11.2% conversion rate, and given how much its search terms differ, a term needs about 85 clicks (about $600.84) with no conversion before the waste model is sure it is bad.

## Worth adding as keywords

These converted at or below the account's $63.23 per conversion and are not keywords yet.

| Search term | Conversions | Cost per conversion | Match type |
|---|---|---|---|
| burst pipe repair | 4 | $50.32 | Broad match |
| gas leak plumber | 3 | $43.57 | Phrase match |
| toilet installation | 2 | $36.96 | Broad match |

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

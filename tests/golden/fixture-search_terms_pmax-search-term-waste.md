<!-- passed: True -->
# Search-term waste audit

Source: `search_terms_pmax.csv` · July 1, 2026 to July 31, 2026 (31 days) · currency USD

Settings: waste threshold $20.00

_Built by OpenPPC, read-only: computed from this file alone, with no network calls._

## Summary

**6 search terms spent $767.60 and never converted.** That is 17.7% of the $4,347.25 total cost in this export, and each one cost at least $20.00. All 7 search terms with no conversions, whatever they cost, spent $779.20.

At the same rate that is $24.76 a day, or $9,037.87 a year.

The waste model is at least 90% sure about 1 of them, which spent $331.00: add it as a negative. The other 5 have too few clicks to tell a bad term from bad luck.

Account totals in this export: $4,347.25 cost, 615 clicks, 69 conversions, $63.00 per conversion.

## What to do

1. **Add 1 negative keyword.** The waste model is at least 90% sure about it, and it spent $331.00. “free plumbing quote” is the one. The other 5 are too early to judge.
2. **Add 6 converting terms as keywords.** “emergency plumber” leads with 27 conversions at $46.46 each.

## Wasted spend, ranked

### In Performance Max and other automated campaigns

Performance Max takes negative keywords in the campaign (up to 10,000) or from an account-level negative keyword list, and there they only block Search and Shopping ads, not YouTube, Display or Gmail.

| Search term | Cost | Clicks | Share of total cost | Chance it's bad | Match type | Campaign type |
|---|---|---|---|---|---|---|
| free plumbing quote | $331.00 | 44 | 7.6% | 91% | -- | Performance Max |
| plumbing apprenticeship | $174.20 | 26 | 4.0% | 78% | -- | Performance Max |
| diy drain unblocker | $117.60 | 21 | 2.7% | 73% | -- | Performance Max |
| water heater parts | $78.00 | 12 | 1.8% | 58% | -- | Performance Max |
| drain camera rental | $41.60 | 8 | 1.0% | 50% | -- | Performance Max |
| plumber salary | $25.20 | 6 | 0.6% | 45% | -- | Performance Max |

Below the $20.00 threshold, 1 more zero-conversion term spent $11.60 in total.

At this account's 11.2% conversion rate, and given how much its search terms differ, a term needs about 42 clicks (about $296.89) with no conversion before the waste model is sure it is bad.

## Worth adding as keywords

These converted at or below the account's $63.00 per conversion and are not keywords yet.

| Search term | Conversions | Cost per conversion | Match type |
|---|---|---|---|
| emergency plumber | 27 | $46.46 | -- |
| plumber near me | 19 | $52.97 | -- |
| water heater repair | 9 | $56.92 | -- |
| burst pipe repair | 5 | $50.32 | -- |
| gas leak plumber | 4 | $40.85 | -- |
| toilet installation | 2 | $46.20 | -- |

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

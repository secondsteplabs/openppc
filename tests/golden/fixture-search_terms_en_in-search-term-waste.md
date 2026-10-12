<!-- passed: True -->
# Search-term waste audit

Source: `search_terms_en_in.csv` · July 1, 2026 to July 31, 2026 (31 days) · currency INR

Settings: waste threshold ₹1,500.00

_Built by OpenPPC, read-only: computed from this file alone, with no network calls._

## Summary

**6 search terms spent ₹72,922.00 and never converted.** That is 17.7% of the ₹412,988.75 total cost in this export, and each one cost at least ₹1,500.00. All 7 search terms with no conversions, whatever they cost, spent ₹74,024.00.

At the same rate that is ₹2,352.32 a day, or ₹858,597.74 a year.

The waste model is at least 90% sure about 1 of them, which spent ₹31,445.00: add it as a negative. The other 5 have too few clicks to tell a bad term from bad luck.

Account totals in this export: ₹412,988.75 cost, 615 clicks, 69 conversions, ₹5,985.34 per conversion.

## What to do

1. **Add 1 negative keyword.** The waste model is at least 90% sure about it, and it spent ₹31,445.00. “free plumbing quote” is the one. The other 5 are too early to judge.
2. **Add 3 converting terms as keywords.** “burst pipe repair” leads with 5 conversions at ₹4,780.40 each.

## Wasted spend, ranked

| Search term | Cost | Clicks | Share of total cost | Chance it's bad | Match type |
|---|---|---|---|---|---|
| free plumbing quote | ₹31,445.00 | 44 | 7.6% | 91% | Broad match |
| plumbing apprenticeship | ₹16,549.00 | 26 | 4.0% | 78% | Broad match |
| diy drain unblocker | ₹11,172.00 | 21 | 2.7% | 73% | Broad match |
| water heater parts | ₹7,410.00 | 12 | 1.8% | 58% | Broad match |
| drain camera rental | ₹3,952.00 | 8 | 1.0% | 50% | Broad match |
| plumber salary | ₹2,394.00 | 6 | 0.6% | 45% | Broad match |

Below the ₹1,500.00 threshold, 1 more zero-conversion term spent ₹1,102.00 in total.

At this account's 11.2% conversion rate, and given how much its search terms differ, a term needs about 42 clicks (about ₹28,204.11) with no conversion before the waste model is sure it is bad.

## Worth adding as keywords

These converted at or below the account's ₹5,985.34 per conversion and are not keywords yet.

| Search term | Conversions | Cost per conversion | Match type |
|---|---|---|---|
| burst pipe repair | 5 | ₹4,780.40 | Broad match |
| gas leak plumber | 4 | ₹3,880.75 | Phrase match |
| toilet installation | 2 | ₹4,389.00 | Broad match |

## How this was computed

- Waste: search terms with zero conversions and at least ₹1,500.00 in cost. Change the threshold with `--min-cost`.
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

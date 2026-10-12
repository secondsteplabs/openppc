<!-- passed: True -->
# Search-term waste audit

Source: `search_terms_acme.csv` · July 1, 2026 to July 31, 2026 (31 days) · currency USD

Settings: waste threshold $20.00 · industry averages: home-services

_Built by OpenPPC, read-only: computed from this file alone, with no network calls._

## Summary

**6 search terms spent $767.20 and never converted.** That is 15.4% of the $4,973.64 total cost in this export, and each one cost at least $20.00. All 7 search terms with no conversions, whatever they cost, spent $784.70.

At the same rate that is $24.75 a day, or $9,033.16 a year.

None of them has enough clicks for the waste model to be 90% sure it is bad rather than unlucky, so give them more clicks before adding negatives.

Account totals in this export: $4,973.64 cost, 732 clicks, 85 conversions, $58.51 per conversion.

## What to do

1. **Give 6 terms more clicks before adding negatives.** None is proven bad yet. The closest, “free plumbing estimate”, is 79% likely bad after 41 clicks. The waste model needs about 59 clicks with no conversion to be 90% sure.
2. **Review “water heater replacement cost”.** It converts, but at $201.40 each, more than 3 times the $58.51 average.
3. **Add 5 converting terms as keywords.** “leak detection service” leads with 6 conversions at $47.25 each.

## Wasted spend, ranked

| Search term | Cost | Clicks | Share of total cost | Chance it's bad | Match type |
|---|---|---|---|---|---|
| free plumbing estimate | $312.00 | 41 | 6.3% | 79% | Broad match |
| plumber jobs hiring | $188.00 | 22 | 3.8% | 57% | Broad match |
| how to unclog a drain yourself | $121.00 | 19 | 2.4% | 53% | Broad match |
| plumbing franchise cost | $64.80 | 9 | 1.3% | 36% | Broad match |
| plumbing supply store | $48.40 | 11 | 1.0% | 39% | Broad match |
| plumber reviews | $33.00 | 6 | 0.7% | 30% | Broad match |

Below the $20.00 threshold, 1 more zero-conversion term spent $17.50 in total.

At this account's 11.6% conversion rate, and given how much its search terms differ, a term needs about 59 clicks (about $400.88) with no conversion before the waste model is sure it is bad.

## Converting, but expensive

These converted, but at more than 3 times the account's $58.51 per conversion.

| Search term | Cost | Conversions | Cost per conversion |
|---|---|---|---|
| water heater replacement cost | $402.80 | 2 | $201.40 |

## Worth adding as keywords

These converted at or below the account's $58.51 per conversion and are not keywords yet.

| Search term | Conversions | Cost per conversion | Match type |
|---|---|---|---|
| leak detection service | 6 | $47.25 | Phrase match |
| same day water heater install | 5 | $41.20 | Broad match |
| toilet repair near me | 4 | $42.62 | Broad match |
| sump pump installation | 3 | $34.67 | Phrase match |
| drain cleaning near me | 3 | $58.00 | Broad match |

## Against the Home & Home Improvement average

_Source: WordStream / LocaliQ Google Ads Benchmarks 2026, US search, Apr 2025 to Mar 2026. A ballpark, not a target: US-only, averaged over a year, and every advertiser counts conversions differently. The industry figure for cost per conversion is cost per lead._

| Metric | Yours | Industry average | Read |
|---|---|---|---|
| CPC | $6.79 | $8.33 | lower (better) |
| CTR | 7.43% | 6.47% | higher (better) |
| Conversion rate | 11.61% | 8.05% | higher (better) |
| Cost per conversion | $58.51 | $90.92 | lower (better) |

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

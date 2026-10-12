# Account read: period over period

Source: `account_acme.json` · July 2026 vs June 2026 · currency USD

_Built by OpenPPC, read-only: computed from this file alone, with no network calls._

## Period over period

- Spend: 4,974, from 5,210. DOWN 5%.
- Impressions: 9,852, from 11,890. DOWN 17%.
- Clicks: 732, from 760. DOWN 4%.
- CTR: 7.43%, from 6.39%. UP.
- Conversions: 85, from 71. UP 20%.
- CPA: 58.51, from 73.38. DOWN 20% (improved).

## Read

EFFICIENCY GAIN. Conversions up 20% and CPA down 20% on down spend. More output at lower cost.

**Biggest move:** CPA down 20%

## Flags

None.

## Against the Home & Home Improvement average

_Source: WordStream / LocaliQ Google Ads Benchmarks 2026, US search, Apr 2025 to Mar 2026. A ballpark, not a target: US-only, averaged over a year, and every advertiser counts conversions differently. The industry figure for cost per conversion is cost per lead._

| Metric | Yours | Industry average | Read |
|---|---|---|---|
| CPC | $6.79 | $8.33 | lower (better) |
| CTR | 7.43% | 6.47% | higher (better) |
| Conversion rate | 11.61% | 8.05% | higher (better) |
| Cost per conversion | $58.51 | $90.92 | lower (better) |

## How this was computed

- Every change is current minus prior, divided by prior. A move smaller than 3% is called flat.
- The read is the first rule that matches, in priority order: tracking problems, small samples, then the spend, conversion and CPA patterns. The rules live in `openppc/engine/findings.py`.
- A conversion is whatever this account counts as one. Seasonal businesses should compare against the same period last year, not the previous one.

---

Number check: every number in this report traces back to your data.

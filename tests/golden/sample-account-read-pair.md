<!-- passed: True -->
# Account read: period over period

Source: `search_terms_acme.csv` (current) and `search_terms_acme_june.csv` (prior) · July 1 to July 31, 2026 (31 days) vs June 1 to June 30, 2026 (30 days) · currency USD

_Note: the two periods are different lengths, so their totals are compared as they are, not per day._

_Built by OpenPPC, read-only: computed from these files alone, with no network calls._

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

## How this was computed

- Every change is current minus prior, divided by prior. A move smaller than 3% is called flat.
- The read is the first rule that matches, in priority order: tracking problems, small samples, then the spend, conversion and CPA patterns. The rules live in `openppc/engine/findings.py`.
- A conversion is whatever this account counts as one. Seasonal businesses should compare against the same period last year, not the previous one.

---

Number check: every number in this report traces back to your data.

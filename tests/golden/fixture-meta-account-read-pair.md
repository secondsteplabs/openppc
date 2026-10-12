<!-- passed: True -->
# Account read: period over period

Source: `meta_july.csv` (current) and `meta_june.csv` (prior) · Meta Ads Manager exports (experimental) · July 1 to July 31, 2026 (31 days) vs June 1 to June 30, 2026 (30 days) · currency EUR

_How the files were read: Meta's link clicks counted as clicks and its Results as conversions._

_Note: the two periods are different lengths, so their totals are compared as they are, not per day._

_Built by OpenPPC, read-only: computed from these files alone, with no network calls._

## Period over period

- Spend: 3,213, from 2,731. UP 18%.
- Impressions: 193,230, from 164,245. UP 18%.
- Clicks: 2,408, from 2,047. UP 18%.
- CTR: 1.25%, from 1.25%. FLAT.
- Conversions: 94, from 80. UP 18%.
- CPA: 34.19, from 34.14. FLAT.

## Read

CLEAN SCALE. Conversions up 18% with CPA flat. Spend and output grew together at stable efficiency.

**Biggest move:** spend up 18%

## Flags

- CURRENCY IS EUR: do not compare these figures to USD accounts.

_The industry averages are for Google Ads search campaigns, so a Meta report leaves them out._

## How this was computed

- Every change is current minus prior, divided by prior. A move smaller than 3% is called flat.
- The read is the first rule that matches, in priority order: tracking problems, small samples, then the spend, conversion and CPA patterns. The rules live in `openppc/engine/findings.py`.
- A conversion is whatever this account counts as one. Seasonal businesses should compare against the same period last year, not the previous one.

---

Number check: every number in this report traces back to your data.

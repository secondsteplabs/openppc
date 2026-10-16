---
id: kw-zero-conversion
template: keyword-audit
finding: Keywords spending without converting
rules: kw-zero-conv, kw-brand-spared
sources: src-openppc
fills: n_keywords, cost, examples, period
---
# Keywords spending without converting

**What the audit found:** {n_keywords} keywords spent {cost} in {period} without a single conversion. The biggest: {examples}.

## Why it matters
A keyword with spend and no conversions is either the wrong search, the wrong ad, or the wrong landing page. Finding out which tells you whether to cut it or fix it.

## How to fix it in Google Ads
1. Open each keyword's search terms. If the searches it matched are irrelevant, add those as negatives and, if the keyword itself is off-target, pause it.
2. If the searches are relevant, the problem is after the search: check the ad speaks to that search and the landing page answers it.
3. If the keyword is relevant but too expensive, lower its bid on manual bidding, or let Smart Bidding work with a cost per conversion target.

## Check before you change anything
- Brand keywords are never on this list: pausing them hands those searches to competitors.
- A keyword with few clicks may not have had a fair chance. Compare its clicks with the account's usual clicks per conversion before pausing it. [Shiv]

## How to tell it worked
Next month's keyword audit should show these keywords either converting or gone, and less spend without conversions.

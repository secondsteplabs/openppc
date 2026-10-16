---
id: as-broad-without-smart-bidding
template: account-structure
finding: Broad match without Smart Bidding
rules: search-broad-match-needs-smart-bidding
sources: src-google-7478529, src-optmyzr-audit-skill
fills: n_keywords, campaigns
---
# Broad match without Smart Bidding

**What the audit found:** {n_keywords} broad match keywords run in campaigns that don't use Smart Bidding: {campaigns}.

## Why it matters
Broad match matches a wide range of searches. Google's guidance is to pair it with Smart Bidding, which judges each search by how likely it is to convert. On manual or click bidding, broad match pays the same for a poor search as for a good one.

## How to fix it in Google Ads
Pick one of these for each campaign:
1. Move the campaign to Maximize conversions or Target CPA, if conversion tracking works and the campaign has enough conversions to learn from. Google judges Smart Bidding on at least 30 conversions over 30 days.
2. Or change the broad match keywords to phrase or exact match and keep your current bidding.

## Check before you change anything
Switching bidding resets how the campaign learns. Expect a week or two of uneven results, and don't make other big changes at the same time.

## How to tell it worked
The next account structure audit should show no broad match keywords outside Smart Bidding.

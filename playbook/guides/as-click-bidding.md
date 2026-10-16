---
id: as-click-bidding
template: account-structure
finding: Bidding for clicks, not conversions
rules: bid-conversion-based, bidding-ecpc-deprecated
sources: src-google-2464964
fills: n_campaigns, campaigns, strategies
---
# Bidding for clicks, not conversions

**What the audit found:** {n_campaigns} campaigns bid for clicks rather than conversions: {campaigns} ({strategies}).

## Why it matters
Manual CPC and Maximize clicks buy as many clicks as the budget allows, whether or not they convert. Enhanced CPC stopped working for Search and Display campaigns in the week of 31 March 2025, so any campaign still set to it now runs on plain Manual CPC.

## How to fix it in Google Ads
1. Check conversion tracking works and counts real leads or sales.
2. Move the campaign to Maximize conversions. Once it has a steady record of conversions, add a Target CPA. For campaigns that track sales value, use Maximize conversion value or Target ROAS.
3. Change one campaign at a time and give it two weeks before judging.

## Check before you change anything
If tracking counts page views or clicks as conversions, Smart Bidding will chase those. Fix tracking first: see the tracking guide.

## How to tell it worked
The next audit shows these campaigns on conversion-based bidding, and their cost per conversion is stable or lower after the learning period.

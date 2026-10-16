---
id: stw-pmax-waste
template: search-term-waste
finding: Wasted spend, ranked
rules: stw-automated-apart
sources: src-google-15726455, src-google-11396330, src-google-6372658
fills: n_terms, cost, campaigns
---
# Waste in Performance Max and other automated campaigns

**What the audit found:** {n_terms} wasted search terms came from automated campaigns ({campaigns}), costing {cost}. They are listed apart from Search because they are fixed differently.

## Why it matters
Performance Max chooses its own searches. Without negatives, it can keep spending on searches you would never bid on in a Search campaign.

## How to fix it in Google Ads
1. Add the terms as negative keywords on the Performance Max campaign itself. Google allows up to 10,000 per campaign.
2. Or add them to an account-level negative keyword list, which applies across the account's Search, Shopping and Performance Max traffic.
3. Use exact match for single terms and phrase match for words you never want, as in the Search guides.

## Check before you change anything
- Negatives in Performance Max only stop its Search and Shopping ads. They don't affect where its other ads show.
- An account-level negative also blocks your Search campaigns. Make sure none of these terms is one a Search campaign should keep.

## How to tell it worked
Next month's audit should show these terms gone from the automated campaigns' list.

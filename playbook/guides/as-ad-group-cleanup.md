---
id: as-ad-group-cleanup
template: account-structure
finding: Single-keyword ad groups; Keywords that rarely serve
rules: search-structure-themed-ad-groups, search-structure-cleanup
sources: src-google-14752782
fills: single_keyword_groups, rarely_served
---
# Single-keyword ad groups and keywords that rarely serve

**What the audit found:** {single_keyword_groups} ad groups hold just one keyword, and {rarely_served} keywords rarely or never serve.

## Why it matters
Google's guidance is to group keywords into tightly themed ad groups, so Smart Bidding learns from pooled data instead of many thin slices. Keywords that never serve add clutter and hide the ones that matter.

## How to fix it in Google Ads
1. Fold single-keyword ad groups that share a theme into one ad group, with ads written for that theme.
2. Remove keywords with no impressions over the period, or marked Low search volume.

## Check before you change anything
Reorganizing ad groups resets their history. Make these changes deliberately, a few at a time, rather than rebuilding the account at once.

## How to tell it worked
The next audit shows fewer single-keyword ad groups and no keywords that never serve.

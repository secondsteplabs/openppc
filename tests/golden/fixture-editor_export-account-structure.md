<!-- passed: True -->
# Account structure audit

Source: `editor_export.csv`

_Built by OpenPPC, read-only: computed from this file alone, with no network calls._

## Summary

Live Search: 2 campaigns, 3 ad groups, 6 keywords and 2 responsive search ads.

**11 of 12 checks found something.**

| Check | Result | Rule |
|---|---|---|
| Ads and keywords held back by policy | Not in this file (approval status) | `policy-disapproved` |
| Broad match without Smart Bidding | 1 keyword in 1 campaign | `search-broad-match-needs-smart-bidding` |
| Brand and non-brand in one campaign | Add --brand to check | `struct-brand-nonbrand` |
| Duplicate keywords | 1 keyword | `kw-duplicates` |
| Negatives that block your own keywords | Passed | `neg-conflicts` |
| Headlines and descriptions | 2 of 2 ads | `search-rsa-asset-count` |
| Ads per ad group | 3 ad groups | `search-rsa-per-ad-group` |
| Pinning | 1 with a lone pin, 0 fully pinned | `search-rsa-pinning` |
| Single-keyword ad groups | 1 ad group | `search-structure-themed-ad-groups` |
| Keywords that rarely serve | 1 keyword (16.7%) | `search-structure-cleanup` |
| Quality Score parts below average | 1 keyword | `search-quality-score-diagnostic` |
| Bidding for clicks, not conversions | 1 campaign | `bidding-ecpc-deprecated` |
| Search campaigns on the Display Network | 1 campaign | `struct-settings-consistency` |
| Sitelinks, callouts and snippets | 2 campaigns | `assets-coverage` |
| Budget caps | Not in this file (daily budgets) | `all-budget-spend-caps` |
| Location option | Presence 1, Presence or interest 1 (see below) | `set-location-presence` |

### Broad match without Smart Bidding

Google: broad match keywords should only run in campaigns that use Smart Bidding (Target CPA, Target ROAS, Maximize conversions or Maximize conversion value). On any other strategy, broad match buys loosely related searches with nothing steering it toward conversions.

| Campaign | Bidding | Broad keywords |
|---|---|---|
| Birch Lane \| Search | Manual CPC | 1 |

### Duplicate keywords

The same keyword and match type is live in more than one ad group, so your own ad groups compete for the same searches. Keep the one in the best-fitting ad group and pause the others. Google's structure guide says the same; practitioners add: don't let Google's auto-applied "remove redundant keywords" pick for you.

| Keyword | Match type | Ad groups |
|---|---|---|
| drain cleaning | Phrase | Core, Drains |

### Headlines and descriptions

Google: a responsive search ad holds up to 15 headlines and 4 descriptions, and filling them gives the system more combinations to test. Optmyzr's open audit fails ads with fewer than 8 headlines; here 2 ads are under it. Adalysis warns that a full ad makes more combinations than a small account can test, so fill slots with genuinely different messages.

| Ad group | Headlines | Descriptions |
|---|---|---|
| Core | 3 | 2 |
| Drains | 3 | 1 |

### Ads per ad group

Google: run at least 2 responsive search ads rated Good or Excellent in every ad group (3 at most), so the system can compare them.

| Ad group | Live responsive search ads |
|---|---|
| Brand | 0 |
| Core | 1 |
| Drains | 1 |

### Pinning

1 ad pins a position to a single headline, and 0 ads pin every headline. Google: pin only when you must, and then pin 2 or 3 headlines to the same position so the system still has a choice. Optmyzr's data found fully pinned ads had the worst cost per conversion. Both sides are under "Where Google and practitioners disagree".

### Single-keyword ad groups

Google: group keywords into tightly themed ad groups, and fold single-keyword ad groups into themed ones so Smart Bidding learns from pooled data. Restructure deliberately: moving keywords resets their history.

| Ad group | Live keywords |
|---|---|
| Brand | 1 |

### Keywords that rarely serve

1 of 6 live keywords (16.7%) is marked low search volume, so it almost never shows. Google's structure guide says to clean up non-serving keywords; many practitioners keep them only when they are the exact wording customers use.

| Keyword | Match type | Ad group |
|---|---|---|
| blocked drain | Exact | Drains |

### Quality Score parts below average

Google: use Quality Score's three parts as a diagnostic to find the weak link, not as a number to average. Below average here: expected CTR 1, ad relevance 0, landing page 1. Expected CTR and ad relevance point at the ad copy; landing page points at the page.

| Keyword | Expected CTR | Ad relevance | Landing page |
|---|---|---|---|
| plumber near me | Below average | Average | Below average |

### Bidding for clicks, not conversions

Google stopped Enhanced CPC for Search in March 2025, so those campaigns now run on plain Manual CPC. Manual CPC and Maximize clicks bid for clicks, not conversions; Google suggests Maximize conversions or Target CPA once conversion tracking works.

| Campaign | Bidding | Live keywords |
|---|---|---|
| Birch Lane \| Search | Manual CPC | 5 |

### Search campaigns on the Display Network

Practitioners keep Search campaigns off the Display Network: Display clicks are cheaper, convert differently, and blur the Search numbers. Run Display in its own campaign.

| Campaign | Live keywords |
|---|---|
| Birch Lane \| Search | 5 |

### Sitelinks, callouts and snippets

Google asks for at least 4 sitelinks (6 for busy campaigns); Optmyzr's audit also wants 4 callouts and 1 structured snippet per Search campaign. Account-level assets count for every campaign.

| Campaign | Sitelinks | Callouts | Structured snippets |
|---|---|---|---|
| Birch Lane \| Search | 2 | 2 | 0 |
| Birch Lane \| Brand | 0 | 0 | 0 |

## Where Google and practitioners disagree

- **Ad Strength.** Google says moving an ad from Poor to Excellent brings more conversions. Optmyzr's study of thousands of accounts found Excellent ads had the worst cost per conversion and Average ones the best. Judge ads on cost per conversion and conversions per impression. Your live ads: Poor 1, Average 1.
- **Pinning.** Google says most advertisers should not pin. Optmyzr found partial pinning had the best cost per conversion and full pinning the worst.
- **Location.** Google's default and recommendation is Presence or interest, which also reaches people who only searched about your area. Optmyzr's audit fails accounts that mostly use it and wants Presence: people in or regularly in the area. Your live Search campaigns: Presence 1, Presence or interest 1.
- **Match types.** Google suggests simplifying to broad match under Smart Bidding. Optmyzr's study of tens of thousands of accounts found exact match the most efficient, phrase the workhorse, and broad best for finding new searches. Your live keywords: Exact 3, Phrase 2, Broad 1.

## How this was computed

- Live means the keyword or ad, its ad group and its campaign are all enabled. Only Search campaigns are judged; Performance Max and other campaign types are left out, except by the policy check, which covers every campaign type.
- Every check is a row in OpenPPC's rulebook (`rulebook/rules.csv`); the Rule column is its id, with the source and the exact threshold.
- Negatives are compared with your keyword text: an exact negative must match the whole keyword, a phrase negative its words in order, a broad negative every word in any order.
- A check marked "not in this file" was not run: the file lacks what it needs. It is not a pass.

---

Number check: every number in this report traces back to your data.

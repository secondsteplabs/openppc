<!-- passed: True -->
# Account structure audit

Source: `account_structure_acme.json` · Acme Plumbing (synthetic) · captured September 28, 2026 · currency USD

_Built by OpenPPC, read-only: computed from this file alone, with no network calls._

## Summary

Live Search: 3 campaigns, 5 ad groups, 15 keywords and 7 responsive search ads.

**14 of 14 checks found something.**

| Check | Result | Rule |
|---|---|---|
| Ads and keywords held back by policy | 1 disapproved, 1 limited | `policy-disapproved` |
| Broad match without Smart Bidding | 3 keywords in 2 campaigns | `search-broad-match-needs-smart-bidding` |
| Brand and non-brand in one campaign | Add --brand to check | `struct-brand-nonbrand` |
| Duplicate keywords | 1 keyword | `kw-duplicates` |
| Negatives that block your own keywords | 3 conflicts (shared lists not checked) | `neg-conflicts` |
| Headlines and descriptions | 3 of 7 ads | `search-rsa-asset-count` |
| Ads per ad group | 3 ad groups | `search-rsa-per-ad-group` |
| Pinning | 1 with a lone pin, 1 fully pinned | `search-rsa-pinning` |
| Single-keyword ad groups | 1 ad group | `search-structure-themed-ad-groups` |
| Keywords that rarely serve | 1 keyword (6.7%) | `search-structure-cleanup` |
| Quality Score parts below average | 2 keywords | `search-quality-score-diagnostic` |
| Bidding for clicks, not conversions | 2 campaigns | `bidding-ecpc-deprecated` |
| Search campaigns on the Display Network | 1 campaign | `struct-settings-consistency` |
| Sitelinks, callouts and snippets | 2 campaigns | `assets-coverage` |
| Budget caps | 1 campaign limited by budget | `all-budget-spend-caps` |
| Location option | Presence or interest 2, Presence 1 (see below) | `set-location-presence` |

### Ads and keywords held back by policy

Google reviews every ad and keyword against its ad policies. A disapproved ad or keyword doesn't run at all, though it shows as enabled; an ad approved with limits runs only where its policy allows. Fix what the reason names (the text, the landing page, a certification) and the edit goes back to review, or appeal if the decision is wrong.

| Campaign | Ad group | Ad or keyword | Approval | Reasons |
|---|---|---|---|---|
| Acme \| Search \| Plumbing | Plumbing repair | Acme headline A (ad) | Disapproved | Destination not working |
| Acme \| Brand | Brand | Acme headline A (ad) | Approved limited | Trademarks in ad text |

### Broad match without Smart Bidding

Google: broad match keywords should only run in campaigns that use Smart Bidding (Target CPA, Target ROAS, Maximize conversions or Maximize conversion value). On any other strategy, broad match buys loosely related searches with nothing steering it toward conversions.

| Campaign | Bidding | Broad keywords |
|---|---|---|
| Acme \| Search \| Plumbing | Manual CPC | 2 |
| Acme \| Water Heaters 2024 | Maximize clicks | 1 |

### Duplicate keywords

The same keyword and match type is live in more than one ad group, so your own ad groups compete for the same searches. Keep the one in the best-fitting ad group and pause the others. Google's structure guide says the same; practitioners add: don't let Google's auto-applied "remove redundant keywords" pick for you.

| Keyword | Match type | Ad groups |
|---|---|---|
| plumbing repair | Phrase | Plumbing repair, Drain cleaning |

### Negatives that block your own keywords

A negative keyword that matches one of your own keywords stops that keyword from serving. Remove the negative, or narrow it to exact match.

| Negative | Level | Blocks keyword | Ad group |
|---|---|---|---|
| -free (Broad) | Campaign | free plumbing estimate | Plumbing repair |
| -plumbing repair (Phrase) | Ad group | plumbing repair | Drain cleaning |
| -repair (match type unknown) | Campaign | water heater repair | Water heaters |

Where the file does not give a negative's match type, it is read as broad, the widest reading, so check those by hand.

Negatives in shared lists are not checked yet: this file does not say which campaigns use each list.

### Headlines and descriptions

Google: a responsive search ad holds up to 15 headlines and 4 descriptions, and filling them gives the system more combinations to test. Optmyzr's open audit fails ads with fewer than 8 headlines; here 1 ad is under it. Adalysis warns that a full ad makes more combinations than a small account can test, so fill slots with genuinely different messages.

| Ad group | Headlines | Descriptions |
|---|---|---|
| Drain cleaning | 6 | 2 |
| Sump pumps | 10 | 3 |
| Water heaters | 12 | 3 |

### Ads per ad group

Google: run at least 2 responsive search ads rated Good or Excellent in every ad group (3 at most), so the system can compare them.

| Ad group | Live responsive search ads |
|---|---|
| Drain cleaning | 1 |
| Sump pumps | 1 |
| Water heaters | 1 |

### Pinning

1 ad pins a position to a single headline, and 1 ad pins every headline. Google: pin only when you must, and then pin 2 or 3 headlines to the same position so the system still has a choice. Optmyzr's data found fully pinned ads had the worst cost per conversion. Both sides are under "Where Google and practitioners disagree".

### Single-keyword ad groups

Google: group keywords into tightly themed ad groups, and fold single-keyword ad groups into themed ones so Smart Bidding learns from pooled data. Restructure deliberately: moving keywords resets their history.

| Ad group | Live keywords |
|---|---|
| Sump pumps | 1 |

### Keywords that rarely serve

1 of 15 live keywords (6.7%) is marked low search volume, so it almost never shows. Google's structure guide says to clean up non-serving keywords; many practitioners keep them only when they are the exact wording customers use.

| Keyword | Match type | Ad group |
|---|---|---|
| 40 gallon water heater | Phrase | Water heaters |

### Quality Score parts below average

Google: use Quality Score's three parts as a diagnostic to find the weak link, not as a number to average. Below average here: expected CTR 1, ad relevance 1, landing page 1. Expected CTR and ad relevance point at the ad copy; landing page points at the page.

| Keyword | Expected CTR | Ad relevance | Landing page |
|---|---|---|---|
| pipe repair | Average | Average | Below average |
| water heater replacement | Below average | Below average | Average |

### Bidding for clicks, not conversions

Google stopped Enhanced CPC for Search in March 2025, so those campaigns now run on plain Manual CPC. Manual CPC and Maximize clicks bid for clicks, not conversions; Google suggests Maximize conversions or Target CPA once conversion tracking works.

| Campaign | Bidding | Live keywords |
|---|---|---|
| Acme \| Search \| Plumbing | Enhanced CPC (retired, now Manual CPC) | 8 |
| Acme \| Water Heaters 2024 | Maximize clicks | 4 |

### Search campaigns on the Display Network

Practitioners keep Search campaigns off the Display Network: Display clicks are cheaper, convert differently, and blur the Search numbers. Run Display in its own campaign.

| Campaign | Live keywords |
|---|---|
| Acme \| Search \| Plumbing | 8 |

### Sitelinks, callouts and snippets

Google asks for at least 4 sitelinks (6 for busy campaigns); Optmyzr's audit also wants 4 callouts and 1 structured snippet per Search campaign. Account-level assets count for every campaign.

| Campaign | Sitelinks | Callouts | Structured snippets |
|---|---|---|---|
| Acme \| Search \| Plumbing | 2 | 1 | 0 |
| Acme \| Water Heaters 2024 | 4 | 1 | 0 |

### Budget caps

Google: a campaign can spend up to 2x its average daily budget on a busy day, but is never charged more than 30.4x it in a month, so a single expensive day is not overspend. A campaign limited by budget stops showing before the day ends: raise the budget if it meets its cost per conversion target, otherwise tighten keywords or bids first.

| Campaign | Daily budget | Most in one day | Monthly cap |
|---|---|---|---|
| Acme \| Search \| Plumbing | $120.00 | $240.00 | $3,648.00 |

## Where Google and practitioners disagree

- **Ad Strength.** Google says moving an ad from Poor to Excellent brings more conversions. Optmyzr's study of thousands of accounts found Excellent ads had the worst cost per conversion and Average ones the best. Judge ads on cost per conversion and conversions per impression. Your live ads: Excellent 3, Good 2, Poor 1, Average 1.
- **Pinning.** Google says most advertisers should not pin. Optmyzr found partial pinning had the best cost per conversion and full pinning the worst.
- **Location.** Google's default and recommendation is Presence or interest, which also reaches people who only searched about your area. Optmyzr's audit fails accounts that mostly use it and wants Presence: people in or regularly in the area. Your live Search campaigns: Presence or interest 2, Presence 1.
- **Match types.** Google suggests simplifying to broad match under Smart Bidding. Optmyzr's study of tens of thousands of accounts found exact match the most efficient, phrase the workhorse, and broad best for finding new searches. Your live keywords: Phrase 9, Broad 3, Exact 3.

## How this was computed

- Live means the keyword or ad, its ad group and its campaign are all enabled. Only Search campaigns are judged; Performance Max and other campaign types are left out, except by the policy check, which covers every campaign type.
- Every check is a row in OpenPPC's rulebook (`rulebook/rules.csv`); the Rule column is its id, with the source and the exact threshold.
- Negatives are compared with your keyword text: an exact negative must match the whole keyword, a phrase negative its words in order, a broad negative every word in any order.
- A check marked "not in this file" was not run: the file lacks what it needs. It is not a pass.

---

Number check: every number in this report traces back to your data.

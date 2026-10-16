---
id: stw-waste-themes
template: search-term-waste
finding: What to do
rules: stw-themes
sources: src-adalysis-ngrams, src-openppc
fills: n_themes, themes, cost
---
# Words that keep wasting money

**What the audit found:** {n_themes} words or two-word phrases appear across many search terms that never converted: {themes}. Together those terms cost {cost}.

## Why it matters
Each search term on its own may be too small to judge, but the same word across dozens of terms tells a clear story. Blocking the word catches every future search that contains it, including ones that haven't appeared yet.

## How to fix it in Google Ads
1. For each word, look at the search terms that contain it in the audit, and make sure none of them is a search you want.
2. Add the word as a phrase match negative, written in quotes, for example "jobs". It blocks any search that contains the word.
3. Put it in a shared negative keyword list and apply the list to every campaign it affects.

## Check before you change anything
- A phrase negative blocks more than an exact one. Read the matching terms before you add it: a word like "repair" can be waste in one account and the core service in another.
- Never add your brand or your main service words as negatives.

## How to tell it worked
Next month's audit should show no new terms containing these words, and less spend on terms that never converted.

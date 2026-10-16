# OpenPPC Playbook

The Playbook turns each finding in an OpenPPC audit into the steps to fix it. It is a separate app in this
repository: it reads an audit's results and never changes how the engine computes them.

## The rules every guide follows

1. **No numbers of its own.** Every figure in a guide comes from the audit it is attached to, through `{found}`: the sentence the audit itself printed.
   A guide never promises an outcome ("cuts cost 20%"). Limits from Google's documentation (15 headlines,
   4 descriptions) are allowed because they are facts about the product, not predictions.
2. **Every piece of advice names its source.** The `rules` line links each guide to rows in
   `rulebook/rules.csv`, and `sources` to `rulebook/sources.csv` (Google's help pages, named practitioners, or
   OpenPPC's own reasoning).
3. **Read-only.** A guide tells you what to change in Google Ads. OpenPPC never changes anything.
4. **Our own words.** No text is copied from third-party skills or courses. Related reading is linked, not copied.

## Guide format

```
---
id: short-id
template: the audit template whose finding this guide fixes
finding: the section of that audit's report
rules: rulebook rule ids
sources: rulebook source ids
fills: found
---
# Title

**What the audit found:** {found}

## Why it matters
## How to fix it in Google Ads
## Check before you change anything
## How to tell it worked
```

`{found}` is replaced by the sentence the audit printed for that finding, so the guide repeats only numbers the report already checked. A guide whose finding is absent from an audit is not shown.

## Status

Approved by Shiv 2026-10-17, including four house views (adding clearly irrelevant terms early, expensive converters,
clicks before pausing a keyword, and location targeting by business type).

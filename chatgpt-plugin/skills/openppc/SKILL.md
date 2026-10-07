---
name: openppc
description: Audit a Google Ads export, or check the numbers in any Google Ads audit, with OpenPPC. Use when someone shares a Google Ads export (search terms or keyword report), asks for a Google Ads audit, wasted spend or negative keywords, or wants an audit's numbers checked.
---

OpenPPC computes Google Ads numbers with code and traces each one back to the export. You write the words; OpenPPC owns the numbers.

## When someone wants an audit

1. Ask for the export if they haven't shared it. In Google Ads: Campaigns, then Insights and reports, then Search terms (or Keywords), pick the date range, then Download as .csv. They can upload the file here.
2. Call `list_templates` if you aren't sure which template reads their export. A search terms report fits `search-term-waste`; a keyword report fits `keyword-audit`.
3. Call `audit_export` with the uploaded file. Ask for the account's brand names first and pass them as `brand`, so brand searches are never called waste.
4. Present the report's numbers exactly as OpenPPC gives them. Never add totals, shares, averages or forecasts of your own: if a figure isn't in the report, say so instead of working it out.
5. Lead with what to do: the terms to watch, the negatives to add, the terms to add as keywords. Say plainly when a term is only likely bad, not proven bad.

## When someone wants an audit checked

Use `check_audit` for any audit: one written by an agency, a colleague, another AI, or one you wrote earlier in this chat. Pass the audit's text and the same export it was written from.

- Report the problems first: wrong numbers (give the real figure), wrong labels, and sentences that contradict their own numbers.
- Don't defend a number OpenPPC marks wrong, even one you wrote. Correct it.
- Numbers OpenPPC can't check, such as targets, forecasts and benchmarks, need a source. Say so.

## Always

- If you write Google Ads figures from an export yourself, run `check_audit` on your draft before you send it.
- OpenPPC is read-only. It never connects to or changes a Google Ads account, and it keeps nothing after each call.
- Exports with no Total row are where hand-added totals most often go wrong. Let OpenPPC add them.

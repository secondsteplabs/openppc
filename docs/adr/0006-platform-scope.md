# ADR-6: Platform scope

Status: accepted, October 2026

## Context

OpenPPC is positioned as read-only Google Ads audits. The fork adds readers for Microsoft Advertising and Meta Ads
Manager exports.

## Decision

Google Ads stays the headline. Microsoft Advertising (Phase 3) and Meta Ads Manager (Phase 5) are export readers
labelled experimental. They are named in the docs, the FAQ and the changelog only, never in the hero, titles or
meta descriptions, and every report says which platform it read.

## Consequences

The promise and SEO pins in `tests/test_fitness.py` and `tests/golden/site-seo.txt` keep the existing wording,
titles and descriptions unchanged as these readers land.

# ADR-1: Port features from the fork; don't merge it

Status: accepted, October 2026

## Context

`openppc-2-test` is a fork of OpenPPC 0.1.4 with about 300 files of new work: new readers, outputs, an extension, a
crawler and API downloads. Since 0.1.4, this repository has moved on to 0.1.10, and its checker, tracer and waste
template are newer than the fork's. The two histories share no recent commits.

## Decision

Each feature is re-implemented on the current code, in the phase that needs it. Each fork test file is adapted, kept
or dropped on its own, never copied in bulk. Fork fixtures and generators that are plain data (for example
`tools/build_fixtures.py`) may be ported as they are.

## Consequences

- Nothing in the fork can quietly undo a fix made since 0.1.4.
- Porting costs more than merging would. That cost is planned per phase in `SCOPE_WIDENING_PLAN.md`.
- A fork test that asserts the fork's older behaviour is rewritten to assert what the current code does, after
  checking which behaviour is right.

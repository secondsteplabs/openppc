# ADR-4: Negative inputs stay refused

Status: accepted, October 2026

## Context

Google Ads never exports a negative cost, click count or impression count, so one means the file was edited or is
damaged. OpenPPC refuses such a file (`openppc/ingest/google_ads_csv.py`). The fork turns a negative cost into a
warning and reads on.

## Decision

Keep the refusal. A report computed from a damaged file would carry wrong numbers, and a warning above a report is
easy to miss.

A negative amount written in an audit, such as `-$50.00` for a change between periods, is a different matter: the
tracer should read it (Phase 1).

## Consequences

The refusal is listed in `docs/compatibility.md`, and its message tells the user to download the export again.

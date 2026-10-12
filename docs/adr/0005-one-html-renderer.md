# ADR-5: One HTML renderer

Status: accepted, October 2026

## Context

The fork renders HTML reports twice: once in Python for the CLI, and again in JavaScript for the app. Two renderers
can drift, so the same audit could show different text in each.

## Decision

`--format html` and the app's .html download both render the traced markdown with one deterministic converter,
written in Python. The app calls it through the worker.

## Consequences

Tests check that:

- the numbers in the HTML text equal the numbers in the markdown
- the output has no `<script>` and no external URL, so it opens offline under any CSP

The branded PDF stays a separate, browser-only layout, which already re-checks its own pages.

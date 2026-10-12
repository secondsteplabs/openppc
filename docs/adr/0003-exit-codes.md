# ADR-3: Exit codes

Status: accepted, October 2026; step 1 done in 0.1.12, step 2 in 0.2.0

## Context

`openppc` returns 0 (clean), 1 (bad input), 2 (the check found problems) and 3 (OpenPPC's own report failed its
number check). Two gaps remain: an unexpected exception prints a traceback, and argparse exits 2 on a usage error,
so a script cannot tell a typo from an audit with wrong numbers.

## Decision

Two changes, in two releases:

1. **0.1.12, additive:** an unexpected exception exits 3 with a one-line message, and `--debug` prints the
   traceback. A crash is already non-zero today, so no script that works now breaks.
2. **0.2.0, breaking:** argparse usage errors exit 1, so 2 always means "the check found problems". Scripts that
   treat a usage error as 2 would break, so this waits for a minor release and gets a **Breaking** changelog entry.

## Consequences

`docs/compatibility.md` records the codes, and changes with each step.

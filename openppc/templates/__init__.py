"""Audit templates. Each one is a recipe: which export it reads, what it computes, how it reports.

A template is a module that provides what Template lists. run_template, Template, FactBook, trace and load_report
are the stable engine API (ADR-2): typed, checked by mypy, and a change that breaks them is listed under Breaking
in the changelog.
"""
import os
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from ..engine.trace import trace
from ..facts import Fact, FactBook
from ..ingest import load_report
from . import account_read, account_structure, keyword_audit, search_term_waste

Paths = str | os.PathLike[str] | Sequence[str | os.PathLike[str]]


class Template(Protocol):
    """What a template module provides. mypy checks each module in TEMPLATES against it."""
    NAME: str        # the id on the command line: "search-term-waste"
    TITLE: str       # the report's heading
    TIER: str        # "free"
    INPUT: str       # the file it reads, in words: "Search terms report (.csv)"
    SUMMARY: str     # one sentence for the template lists
    INPUT_KIND: str  # "report" (one export), "metrics" (two periods) or "account" (a snapshot or Editor file)
    accepts: Callable[[Any], bool]  # whether the data it was given is something it can audit
    run: Callable[..., tuple[list[str], FactBook]]  # run(data, **params) -> (markdown lines, FactBook)


_ALL: tuple[Template, ...] = (search_term_waste, keyword_audit, account_structure, account_read)
TEMPLATES: dict[str, Template] = {t.NAME: t for t in _ALL}


def load_input(template: Template, path: Paths) -> Any:
    """path: one file, or for account-read a list of two, one export per period."""
    paths = [str(p) for p in path] if isinstance(path, (list, tuple)) else [str(path)]
    if template.INPUT_KIND == "metrics":
        return account_read.load(paths)
    if len(paths) != 1:
        raise ValueError(f"{template.NAME} reads one file. To compare two periods, use account-read.")
    if template.INPUT_KIND == "account":
        return account_structure.load(paths[0])
    return load_report(paths[0])


def run_template(name: str, path: Paths, **params: Any) -> tuple[str, list[Fact], bool]:
    """Run a template on a file. Returns (markdown, facts, number_check_passed)."""
    markdown, book, passed = run_template_book(name, path, **params)
    return markdown, book.facts, passed


def run_template_book(name: str, path: Paths, data: Any = None, progress: Callable[[str], object] | None = None,
                      **params: Any) -> tuple[str, FactBook, bool]:
    """Same as run_template, but hands back the whole FactBook, cards included. data: the file, already read.
    progress(step) is told as the run moves from one step to the next, for a long run's "working" line."""
    if name not in TEMPLATES:
        raise ValueError(f"unknown template '{name}'. Available: {', '.join(TEMPLATES)}")
    template = TEMPLATES[name]
    step = progress or (lambda _: None)
    if data is None:
        step("Reading the file")
        data = load_input(template, path)
    step("Running the audit")
    lines, book = template.run(data, **params)
    markdown = "\n".join(lines)
    step("Checking every number in the report")
    claims, contradictions = trace(markdown, book.facts)
    passed = all(c.verdict == "traced" for c in claims) and not contradictions
    markdown += "\n\n---\n\n" + (
        "Number check: every number in this report traces back to your data."
        if passed else
        "Number check FAILED: this report contains a number the checker could not trace. "
        "That is a bug in OpenPPC, please report it.")
    return markdown, book, passed

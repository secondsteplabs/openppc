"""Audit templates. Each one is a recipe: which export it reads, what it computes, how it reports.

A template module defines NAME, TITLE, TIER, INPUT, SUMMARY, INPUT_KIND ("report" or
"metrics" or "account"), accepts(data) and run(data, **params) -> (markdown lines, FactBook).
"""
from ..engine.trace import trace
from ..ingest import load_report
from . import account_read, account_structure, keyword_audit, search_term_waste

TEMPLATES = {t.NAME: t for t in (search_term_waste, keyword_audit, account_structure, account_read)}


def load_input(template, path):
    if template.INPUT_KIND == "metrics":
        return account_read.load_metrics(path)
    if template.INPUT_KIND == "account":
        return account_structure.load(path)
    return load_report(path)


def run_template(name, path, **params):
    """Run a template on a file. Returns (markdown, facts, number_check_passed)."""
    markdown, book, passed = run_template_book(name, path, **params)
    return markdown, book.facts, passed


def run_template_book(name, path, data=None, **params):
    """Same as run_template, but hands back the whole FactBook, cards included. data: the file, already read."""
    if name not in TEMPLATES:
        raise ValueError(f"unknown template '{name}'. Available: {', '.join(TEMPLATES)}")
    template = TEMPLATES[name]
    lines, book = template.run(load_input(template, path) if data is None else data, **params)
    markdown = "\n".join(lines)
    claims, contradictions = trace(markdown, book.facts)
    passed = all(c.verdict == "traced" for c in claims) and not contradictions
    markdown += "\n\n---\n\n" + (
        "Number check: every number in this report traces back to your data."
        if passed else
        "Number check FAILED: this report contains a number the checker could not trace. "
        "That is a bug in OpenPPC, please report it.")
    return markdown, book, passed

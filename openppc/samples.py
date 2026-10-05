"""The made-up Acme Plumbing sample: one export per template, and an AI-written audit to check.

It ships inside the package (pyproject.toml copies these files from examples/ into openppc/samples/), so after
a plain `pip install openppc` the command line can try any template with --sample. In a clone of the repo the
files are read straight from examples/.
"""
import errno
from pathlib import Path

EXPORTS = {
    "search-term-waste": "search_terms_acme.csv",
    "keyword-audit": "keywords_acme.csv",
    "account-structure": "account_structure_acme.json",
    "account-read": "account_acme.json",
}
AUDIT = "ai_audit_sample.md"
AUDIT_DATA = "search_terms_acme.csv"  # the export the sample audit was written from
INDUSTRY = "home-services"            # a plumbing company


def path(name):
    """Where a sample file is: inside the installed package, or in examples/ in a clone."""
    here = Path(__file__).resolve().parent
    for folder in (here / "samples", here.parent / "examples"):
        if (folder / name).is_file():
            return folder / name
    raise FileNotFoundError(errno.ENOENT, "a sample file is missing from this install", name)

"""A 20,000-row export, audited and checked within a generous budget.

The budgets are several times what a laptop needs (0.1.11 on a Windows laptop: about 1.4 s to audit and 2–5 s to
check), so slow CI machines pass, but a return to scanning every fact for every number fails. The browser runs the
same code a few times slower, in a worker.
"""
import time

from openppc.checkfacts import facts_for_paths
from openppc.engine.trace import trace
from openppc.templates import run_template

ROWS = 20_000
AUDIT_BUDGET = 20.0   # seconds, including the report's own number check
CHECK_BUDGET = 20.0


def _export(path):
    lines = ["Search terms report", "July 1, 2026 - July 31, 2026",
             "Search term,Match type,Added/Excluded,Campaign,Ad group,Clicks,Impr.,Currency code,Cost,Conversions"]
    for i in range(ROWS):
        clicks = 1 + i % 97
        cost = clicks * (1.5 + (i * 7919) % 900 / 100)
        conv = (i % 13 == 0) * (1 + i % 4)
        lines.append(f"search term {i:05d},Broad match,None,Campaign {i % 40},Group {i % 400},{clicks},"
                     f"{clicks * 12},USD,{cost:.2f},{conv}.00")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_a_large_export_is_audited_and_checked_in_time(tmp_path):
    path = tmp_path / "large.csv"
    _export(path)
    start = time.perf_counter()
    markdown, _, passed = run_template("search-term-waste", path)
    audited = time.perf_counter() - start
    assert passed
    start = time.perf_counter()
    claims, _ = trace(markdown, facts_for_paths([path]))
    checked = time.perf_counter() - start
    print(f"{ROWS:,} rows: audit {audited:.2f} s, check {checked:.2f} s, {len(claims)} numbers")
    assert audited < AUDIT_BUDGET, f"audit took {audited:.1f} s"
    assert checked < CHECK_BUDGET, f"check took {checked:.1f} s"

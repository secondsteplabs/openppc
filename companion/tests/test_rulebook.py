"""The site check's rulebook, kept apart from the core's so the core's tests never import the companion: every
threshold the code uses has a row, every rule a row and every row a rule."""
import csv
import importlib
import inspect
from pathlib import Path

from openppc_online.siteaudit import checks

BOOK = Path(__file__).resolve().parent.parent / "rulebook"


def rows(name):
    with open(BOOK / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def resolve(ref):
    """'package.module:NAME' is a constant, 'package.module:func.arg' is a default argument."""
    module, _, name = ref.partition(":")
    head, _, arg = name.partition(".")
    obj = getattr(importlib.import_module(module), head)
    return inspect.signature(obj).parameters[arg].default if arg else obj


def same(code, written):
    if isinstance(code, (tuple, list, set, frozenset)):
        return set(code) == set(written.split("|"))
    return float(code) == float(written)


def test_every_threshold_in_the_code_matches_its_row():
    for r in rows("rules.csv"):
        refs = [x for x in r["code_ref"].split(";") if x]
        values = r["value"].split(";") if r["value"] else []
        assert len(values) <= len(refs), f"{r['rule_id']}: more values than code references"
        for ref, written in zip(refs, values + [""] * len(refs)):
            assert ref.startswith("openppc_online."), f"{r['rule_id']}: {ref} is outside the companion"
            code = resolve(ref)  # fails when the code moved and the rulebook didn't
            if written:
                assert same(code, written), f"{r['rule_id']}: {ref} is {code!r} in the code, {written} in the rulebook"


def test_rule_ids_are_unique_and_point_at_code():
    rs = rows("rules.csv")
    ids = [r["rule_id"] for r in rs]
    assert len(ids) == len(set(ids)) and all(i.startswith("site-") for i in ids)
    assert all(r["code_ref"] for r in rs)
    assert {r["status"] for r in rs} <= {"live", "planned"} and {r["tier"] for r in rs} == {"free"}
    assert all(r["metrics"] == "" and r["conflicts_with"] == "" for r in rs)


def test_every_cited_source_exists():
    sources = {r["source_id"] for r in rows("sources.csv")}
    cited = {s for r in rows("rules.csv") for s in r["source_ids"].split(";") if s}
    assert cited == sources


def test_every_site_rule_has_a_row_and_every_row_a_rule():
    rs = [r for r in rows("rules.csv") if r["area"] != "site-crawl"]
    assert {r["rule_id"] for r in rs} == set(checks.RULES)
    assert all(r["area"] == checks.RULES[r["rule_id"]].category for r in rs)

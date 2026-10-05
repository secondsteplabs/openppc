"""The rulebook is the backend sheet: every threshold the code uses has a row there, and the two can't drift."""
import csv
import importlib
import inspect
from pathlib import Path

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
            code = resolve(ref)  # fails when the code moved and the rulebook didn't
            if written:
                assert same(code, written), f"{r['rule_id']}: {ref} is {code!r} in the code, {written} in the rulebook"


def test_rule_ids_are_unique_and_live_rules_point_at_code():
    rs = rows("rules.csv")
    ids = [r["rule_id"] for r in rs]
    assert len(ids) == len(set(ids))
    assert all(r["code_ref"] for r in rs if r["status"] == "live")
    assert {r["status"] for r in rs} <= {"live", "planned", "reference"}
    assert {r["tier"] for r in rs} <= {"free", "paid"}


def test_every_cited_source_and_metric_exists():
    sources = {r["source_id"] for r in rows("sources.csv")}
    metrics = {r["metric_id"] for r in rows("metrics.csv")}
    for r in rows("rules.csv"):
        for s in filter(None, r["source_ids"].split(";")):
            assert s in sources, f"{r['rule_id']} cites unknown source {s}"
        for m in filter(None, r["metrics"].split(";")):
            assert m in metrics, f"{r['rule_id']} uses unknown metric {m}"
        for other in filter(None, r["conflicts_with"].split(";")):
            assert other in {x["rule_id"] for x in rows("rules.csv")}, f"{r['rule_id']} conflicts with unknown rule {other}"

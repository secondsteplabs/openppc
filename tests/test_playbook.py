"""The Playbook: a guide for every finding, no number of its own, and every step tied to a rule and a source."""
import csv
import re
from pathlib import Path

import pytest

from openppc import cli, mcp_server, playbook
from openppc.checkfacts import facts_for_check
from openppc.engine.trace import trace
from openppc.templates import run_template_book

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
BRAND = "Acme Plumbing, Acme"
SAMPLES = [("search-term-waste", "search_terms_acme.csv", {"brand": BRAND}),
           ("search-term-waste", "search_terms_acme.csv", {}),
           ("keyword-audit", "keywords_acme.csv", {"brand": BRAND}),
           ("account-structure", "account_structure_acme.json", {"brand": BRAND}),
           ("account-read", "account_acme.json", {})]
RULES = {r["rule_id"]: r for r in csv.DictReader((ROOT / "rulebook" / "rules.csv").open(encoding="utf-8"))}
TEMPLATE_CODE = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "openppc" / "templates").glob("*.py"))


@pytest.mark.parametrize("guide", sorted(playbook.guides().values(), key=lambda g: g.id), ids=lambda g: g.id)
def test_every_guide_rests_on_live_rules_and_real_sources(guide):
    assert guide.rules and guide.sources and guide.title
    for rule in guide.rules:
        assert RULES[rule]["status"] == "live", rule
    for source in guide.sources:
        assert source in playbook.sources(), source
    for section in guide.finding.split(";"):  # the report section the guide fixes really exists
        assert section.strip() in TEMPLATE_CODE, section
    assert guide.body.count("{found}") == 1 and not re.search(r"\{(?!found\})\w+\}", guide.body)
    assert not re.search("[–—]", guide.title + guide.body)


@pytest.mark.parametrize("guide", sorted(playbook.guides().values(), key=lambda g: g.id), ids=lambda g: g.id)
def test_a_guide_promises_no_figure_its_rules_do_not_state(guide):
    # money and percentages are what an outcome promise looks like ("cuts cost 20%"); a guide may only use the ones
    # its own rules state, such as the waste model's 90% bar
    backing = " ".join(RULES[r][k] for r in guide.rules for k in ("rule", "threshold", "value", "notes"))
    for figure in re.findall(r"\$[\d,.]+|\d+(?:\.\d+)?%", guide.body):
        assert figure.replace("$", "").rstrip("%") in backing, figure


def test_every_finding_a_template_reports_has_a_guide_and_every_guide_is_reachable():
    from openppc.templates import account_read, account_structure, search_term_waste
    named = (set(search_term_waste.PLAYBOOK.values()) | set(account_structure.PLAYBOOK.values())
             | {guide for _, guide in account_read.PLAYBOOK} | set(re.findall(r'"guide": "([a-z-]+)"', TEMPLATE_CODE)))
    assert named <= set(playbook.guides()), named - set(playbook.guides())
    assert set(playbook.guides()) <= named, set(playbook.guides()) - named


@pytest.mark.parametrize("template, export, params", SAMPLES)
def test_a_fix_plan_quotes_only_numbers_that_trace_to_the_export(template, export, params):
    path = str(EXAMPLES / export)
    _, book, _ = run_template_book(template, path, **params)
    assert book.findings, "every sample has something to fix"
    plan = playbook.fix_plan(template, path, **params)
    claims, contradictions = trace(plan, facts_for_check(plan, [path], None))
    wrong = [(c.written, c.verdict, c.context[:80]) for c in claims if c.verdict in ("mismatch", "not in data")]
    assert not wrong and not contradictions
    for found in (f["found"] for f in book.findings):  # each finding is quoted in full, under its guide
        assert found in plan


def test_findings_follow_the_reports_own_to_do_list():
    _, book, _ = run_template_book("search-term-waste", str(EXAMPLES / "search_terms_acme.csv"), brand=BRAND)
    assert [f["guide"] for f in book.findings][:3] == ["stw-not-proven-yet", "stw-expensive-converters", "stw-harvest"]
    assert [a["kind"] for a in book.cards["actions"]] == ["watch", "review", "add"]


def test_one_guide_covers_several_findings_once():
    findings = [{"guide": "as-rsa-coverage", "found": "Headlines and descriptions: 3 of 7 ads."},
                {"guide": "as-rsa-coverage", "found": "Pinning: 1 fully pinned."},
                {"guide": "no-such-guide", "found": "ignored"}]
    plan = playbook.render(findings)
    assert plan.count("## 1.") == 1 and "## 2." not in plan and "ignored" not in plan
    assert "3 of 7 ads. Pinning: 1 fully pinned." in plan
    assert "Nothing to fix here" in playbook.render([])


def test_the_command_line_prints_a_fix_plan(capsys):
    assert cli.main(["playbook", "account-structure", "--sample", "--brand", BRAND]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Fix plan: Account structure audit") and "### How to fix it in Google Ads" in out


def test_mcp_tools_return_the_same_fix_plan_from_a_path_or_contents():
    path = EXAMPLES / "keywords_acme.csv"
    from_path = mcp_server.fix_plan_for_account("keyword-audit", str(path), brand=BRAND)
    from_text = mcp_server.fix_plan_for_export("keyword-audit", path.read_text(encoding="utf-8"), path.name, brand=BRAND)
    assert from_path == from_text == playbook.fix_plan("keyword-audit", str(path), brand=BRAND)

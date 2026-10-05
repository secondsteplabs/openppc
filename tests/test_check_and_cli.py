from pathlib import Path

import pytest

from openppc import mcp_server
from openppc.checkfacts import facts_for_paths
from openppc.cli import main
from openppc.engine.trace import trace

EXAMPLES = Path(__file__).parent.parent / "examples"
CSV = EXAMPLES / "search_terms_acme.csv"
SAMPLE = EXAMPLES / "ai_audit_sample.md"


def test_sample_ai_audit_is_caught():
    claims, contradictions = trace(SAMPLE.read_text(), facts_for_paths([CSV]))
    flagged = {c.written: c.verdict for c in claims if c.verdict != "traced"}
    # 14% ("fell from 9% to 14%") is not the account's conversion rate; 9% is the earlier figure, which a one-month
    # export cannot hold; with no industry chosen, 6.47% is an outside average: neither can be checked
    assert flagged == {"$4,200": "not in data", "22": "mismatch", "9%": "can't check", "14%": "not in data",
                       "62%": "not in data", "6.47%": "can't check"}
    assert [n for n, _, _ in contradictions] == [11]
    traced = {c.written for c in claims if c.verdict == "traced"}
    assert {"$312", "41", "$58.51", "$9,000", "7.4%"} <= traced


def test_industry_averages_count_as_data_when_asked():
    claims, _ = trace(SAMPLE.read_text(), facts_for_paths([CSV], "home-services"))
    assert next(c for c in claims if c.written == "6.47%").verdict == "traced"


def test_cli(tmp_path):
    out = tmp_path / "report.md"
    assert main(["audit", "search-term-waste", str(CSV), "--out", str(out)]) == 0
    assert "Number check: every number in this report traces back to your data." in out.read_text()
    assert main(["check", "--audit", str(SAMPLE), "--data", str(CSV), "--out", str(tmp_path / "c.md")]) == 2
    assert main(["audit", "keyword-audit", str(CSV)]) == 1  # wrong export for this template


def test_mcp_tools_work_without_the_mcp_extra():
    assert "search-term-waste" in mcp_server.list_templates()
    assert "Number check: every number" in mcp_server.audit_account("search-term-waste", str(CSV))
    assert "Needs attention" in mcp_server.check_numbers(SAMPLE.read_text(), [str(CSV)])


def test_mcp_server_registers_read_only_tools():
    pytest.importorskip("mcp")
    import asyncio
    import inspect

    server = mcp_server.build_server()
    tools = server.list_tools()
    tools = asyncio.run(tools) if inspect.isawaitable(tools) else tools
    assert sorted(t.name for t in tools) == ["audit_account", "check_numbers", "list_templates"]
    # SDK 2.x names the field read_only_hint; 1.x named it readOnlyHint
    assert all(getattr(t.annotations, "read_only_hint", None) or getattr(t.annotations, "readOnlyHint", None)
               for t in tools)

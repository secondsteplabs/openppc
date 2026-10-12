import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from openppc import mcp_server, webapi
from openppc.checkfacts import facts_for_paths
from openppc.cli import main
from openppc.engine.trace import render_check, trace

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
FIXTURES = Path(__file__).parent / "fixtures"
CSV = EXAMPLES / "search_terms_acme.csv"
SAMPLE = EXAMPLES / "ai_audit_sample.md"


def test_sample_ai_audit_is_caught():
    claims, contradictions = trace(SAMPLE.read_text(encoding="utf-8"), facts_for_paths([CSV]))
    flagged = {c.written: c.verdict for c in claims if c.verdict != "traced"}
    # 14% ("fell from 9% to 14%") is not the account's conversion rate; 9% is the earlier figure, which a one-month
    # export cannot hold; with no industry chosen, 6.47% is an outside average: neither can be checked
    assert flagged == {"$4,200": "not in data", "22": "mismatch", "9%": "can't check", "14%": "not in data",
                       "62%": "not in data", "6.47%": "can't check"}
    assert [n for n, _, _ in contradictions] == [11]
    traced = {c.written for c in claims if c.verdict == "traced"}
    assert {"$312", "41", "$58.51", "$9,000", "7.4%"} <= traced


def test_a_flag_prints_money_with_its_symbol_and_one_sentence_reads_as_one():
    claims, contradictions = trace(SAMPLE.read_text(encoding="utf-8"), facts_for_paths([CSV], "home-services"))
    detail = next(c.detail for c in claims if c.written == "$4,200")
    assert detail == "no: the cost of all search terms with no conversions is $784.70"
    markdown = render_check(claims, contradictions)
    assert "1 sentence contradicts its own numbers." in markdown and "sentence(s)" not in markdown


def test_industry_averages_count_as_data_when_asked():
    claims, _ = trace(SAMPLE.read_text(encoding="utf-8"), facts_for_paths([CSV], "home-services"))
    assert next(c for c in claims if c.written == "6.47%").verdict == "traced"


def test_cli(tmp_path):
    out = tmp_path / "report.md"
    assert main(["audit", "search-term-waste", str(CSV), "--out", str(out)]) == 0
    assert "Number check: every number in this report traces back to your data." in out.read_text(encoding="utf-8")
    assert main(["check", "--audit", str(SAMPLE), "--data", str(CSV), "--out", str(tmp_path / "c.md")]) == 2
    assert main(["audit", "keyword-audit", str(CSV)]) == 1  # wrong export for this template


def test_a_threshold_that_is_not_an_amount_is_refused(capsys):
    for bad in ("nan", "inf", "-5"):
        assert main(["audit", "search-term-waste", str(CSV), "--min-cost", bad]) == 1, bad
        assert "waste threshold must be an amount of zero or more" in capsys.readouterr().err, bad
    assert main(["audit", "keyword-audit", str(EXAMPLES / "keywords_acme.csv"), "--min-cost", "nan"]) == 1
    assert main(["audit", "search-term-waste", str(CSV), "--min-cost", "0"]) == 0
    capsys.readouterr()
    refused = json.loads(webapi.audit("search-term-waste", str(CSV), "", "twenty", ""))
    assert refused == {"ok": False, "error": "The waste threshold must be an amount such as 20, not 'twenty'."}


@pytest.mark.parametrize("argv", [[], ["audit"], ["audit", "no-such-template"], ["frobnicate"],
                                  ["audit", "search-term-waste", "--min-cost", "twenty"], ["check", "--nope"]])
def test_a_usage_mistake_exits_1_like_any_bad_input(argv, capsys):
    """2 means only that the check found problems (ADR-3, since 0.2.0)."""
    with pytest.raises(SystemExit) as stop:
        main(argv)
    assert stop.value.code == 1 and "openppc" in capsys.readouterr().err


def test_a_report_in_rupees_prints_on_a_legacy_code_page():
    run = subprocess.run([sys.executable, "-c", "from openppc.cli import main; raise SystemExit(main())",
                          "audit", "search-term-waste", str(FIXTURES / "search_terms_en_in.csv")],
                         capture_output=True, cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert run.returncode == 0, run.stderr.decode("utf-8", "replace")
    assert "₹72,922.00" in run.stdout.decode("utf-8")


def _refusal(capsys, *argv):
    assert main(list(argv)) == 1
    return capsys.readouterr().err


def test_files_that_cannot_be_read_are_refused_in_words(tmp_path, capsys):
    head = "\n".join(CSV.read_text(encoding="utf-8").splitlines()[:3]) + "\n"
    (tmp_path / "header_only.csv").write_text(head, encoding="utf-8")
    (tmp_path / "bad.json").write_text("{x", encoding="utf-8")
    assert "is a folder. Give the name of a file in it." in _refusal(capsys, "audit", "search-term-waste", str(tmp_path))
    assert "is a folder" in _refusal(capsys, "check", "--audit", str(SAMPLE), "--data", str(tmp_path))
    assert "is a folder" in _refusal(capsys, "check", "--audit", str(tmp_path), "--data", str(CSV))
    assert "no rows of data. Check the date range" in _refusal(capsys, "audit", "search-term-waste",
                                                                str(tmp_path / "header_only.csv"))
    assert "not valid JSON (expecting property name enclosed in double quotes at line 1, column 2)" in _refusal(
        capsys, "audit", "account-structure", str(tmp_path / "bad.json"))
    missing = tmp_path / "no" / "such"
    assert f"the folder {missing} doesn't exist. Create it, or pick another --out." in _refusal(
        capsys, "audit", "search-term-waste", "--sample", "--out", str(missing / "report.md"))
    assert "is a folder. Give --out a file name" in _refusal(capsys, "check", "--sample", "--out", str(tmp_path))


@pytest.mark.parametrize("encoding", ["cp1252", "utf-16", "utf-16-le"])
def test_check_reads_an_audit_saved_in_an_old_or_wide_encoding(tmp_path, capsys, encoding):
    audit = tmp_path / "audit.md"
    audit.write_bytes((SAMPLE.read_text(encoding="utf-8") + "\nCafé – done.\n").encode(encoding))
    assert main(["check", "--audit", str(audit), "--data", str(CSV)]) == 2
    assert "$4,200" in capsys.readouterr().out


def test_check_takes_several_exports_after_one_data_flag(capsys):
    both = [str(CSV), str(EXAMPLES / "keywords_acme.csv")]
    assert main(["check", "--audit", str(SAMPLE), "--data", *both]) == 2
    one_flag = capsys.readouterr().out
    assert main(["check", "--audit", str(SAMPLE), "--data", both[0], "--data", both[1]]) == 2
    assert capsys.readouterr().out == one_flag


def test_a_crash_exits_3_in_one_line_and_debug_shows_the_traceback(monkeypatch, capsys):
    def broken(*args, **kwargs):
        raise ZeroDivisionError("division by zero")
    monkeypatch.setattr("openppc.cli.run_template", broken)
    assert main(["audit", "search-term-waste", "--sample"]) == 3
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "(ZeroDivisionError: division by zero). This is a bug" in err
    for argv in (["--debug", "audit", "search-term-waste", "--sample"], ["audit", "search-term-waste", "--sample",
                                                                          "--debug"]):
        assert main(argv) == 3
        assert "Traceback (most recent call last)" in capsys.readouterr().err


def test_mcp_tools_work_without_the_mcp_extra():
    assert "search-term-waste" in mcp_server.list_templates()
    assert "Number check: every number" in mcp_server.audit_account("search-term-waste", str(CSV))
    assert "Needs attention" in mcp_server.check_numbers(SAMPLE.read_text(encoding="utf-8"), [str(CSV)])


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


def test_flags_are_called_wrong_number_and_wrong_label(capsys):
    # The codes stay ("not in data", "mismatch"); people read plainer names.
    assert main(["check", "--sample"]) == 2
    out = capsys.readouterr().out
    assert "3 wrong numbers, 1 wrong label" in out and "| wrong number |" in out and "| wrong label |" in out
    assert "not in data" not in out.lower() and "mismatch" not in out.lower()


def test_openppcs_own_report_passes_its_own_check_whatever_its_settings(tmp_path, capsys):
    # A report made with brand terms, its own threshold or an industry says so, and the check runs the same audit
    from openppc.checkfacts import facts_for_check, report_settings
    for opts in ([], ["--brand", "plumber, drain"], ["--min-cost", "7.50"], ["--industry", "home-services"]):
        out = tmp_path / "own.md"
        assert main(["audit", "search-term-waste", str(CSV), "--out", str(out), *opts]) == 0
        text = out.read_text(encoding="utf-8")
        claims, contradictions = trace(text, facts_for_check(text, [CSV]))
        assert not [c for c in claims if c.verdict in ("mismatch", "not in data")] and not contradictions, opts
        assert main(["check", "--audit", str(out), "--data", str(CSV)]) == 0, opts  # can't check never fails a check
    capsys.readouterr()
    assert report_settings(text) == {"template": "search-term-waste", "min_cost": 20.0, "industry": "home-services"}
    assert report_settings("Settings: waste threshold $1.00") == {}  # only OpenPPC's own reports carry settings

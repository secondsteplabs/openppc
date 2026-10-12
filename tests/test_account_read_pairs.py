"""account-read on two exports of one report, one per period."""
from pathlib import Path

import pytest

from openppc import cli, mcp_server
from openppc.checkfacts import facts_for_paths
from openppc.engine.trace import trace
from openppc.templates import run_template

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES, FIXTURES = ROOT / "examples", ROOT / "tests" / "fixtures"
JULY, JUNE = EXAMPLES / "search_terms_acme.csv", EXAMPLES / "search_terms_acme_june.csv"


def _section(markdown):
    """The findings, from "## Period over period" up to "## How this was computed"."""
    return markdown.split("## Period over period")[1].split("## How this was computed")[0]


def test_the_two_samples_read_like_the_totals_file():
    """June's sample adds up to the prior period in account_acme.json, July's to the current one."""
    pair, _, passed = run_template("account-read", [JULY, JUNE])
    totals, _, _ = run_template("account-read", EXAMPLES / "account_acme.json")
    assert passed and _section(pair) == _section(totals)
    assert ("Source: `search_terms_acme.csv` (current) and `search_terms_acme_june.csv` (prior) · July 1 to July 31, "
            "2026 (31 days) vs June 1 to June 30, 2026 (30 days)") in pair
    assert "_Note: the two periods are different lengths" in pair


def test_the_later_file_is_the_current_period_whichever_comes_first():
    a, _, _ = run_template("account-read", [JULY, JUNE])
    b, _, _ = run_template("account-read", [JUNE, JULY])
    assert a == b


def test_periods_of_one_length_get_no_note(tmp_path):
    may = tmp_path / "search_terms_may.csv"
    may.write_bytes(JULY.read_bytes().replace(b"July", b"May"))
    markdown, _, passed = run_template("account-read", [JULY, may])
    assert passed and "different lengths" not in markdown


@pytest.mark.parametrize("other, problem", [
    (JULY, "cover overlapping dates"),
    (EXAMPLES / "keywords_acme.csv", "are different reports"),
    (FIXTURES / "search_terms_de.csv", "is in USD and search_terms_de.csv in EUR"),
    (FIXTURES / "search_terms_microsoft.csv", "are different reports"),
])
def test_a_pair_that_is_not_two_periods_of_one_report_is_refused(other, problem):
    with pytest.raises(ValueError, match=problem):
        run_template("account-read", [JULY, other])


def test_an_export_with_no_dates_or_no_impressions_is_refused(tmp_path):
    undated = tmp_path / "undated.csv"
    undated.write_bytes(b"\n".join(JUNE.read_bytes().split(b"\n")[2:]))
    with pytest.raises(ValueError, match="undated.csv has no date range"):
        run_template("account-read", [JULY, undated])
    no_impr = tmp_path / "no_impressions.csv"
    no_impr.write_text("Search terms report\nJune 1, 2026 - June 30, 2026\nSearch term,Clicks,Cost,Conversions\n"
                       "plumber,10,50.00,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no_impressions.csv has no impressions column"):
        run_template("account-read", [JULY, no_impr])


def test_one_export_or_three_is_not_a_pair():
    with pytest.raises(ValueError, match="account-read compares two periods"):
        run_template("account-read", JULY)
    with pytest.raises(ValueError, match="account-read compares two periods"):
        run_template("account-read", [JULY, JUNE, JULY])
    with pytest.raises(ValueError, match="search-term-waste reads one file"):
        run_template("search-term-waste", [JULY, JUNE])


@pytest.mark.parametrize("pair", [[JULY, JUNE], [FIXTURES / "search_terms_july.csv", FIXTURES / "search_terms_june.csv"]])
def test_check_mode_traces_a_pair_report_from_the_two_exports(pair):
    markdown, facts, passed = run_template("account-read", pair)
    assert passed
    thresholds = {f.value for f in facts if f.metric == "rule"}  # settings, not account data
    claims, contradictions = trace(markdown, facts_for_paths(pair))
    assert [c.written for c in claims if c.verdict != "traced" and c.value not in thresholds] == []
    assert not contradictions


def test_the_command_line_takes_two_exports(capsys):
    assert cli.main(["audit", "account-read", str(JULY), str(JUNE)]) == 0
    assert "EFFICIENCY GAIN" in capsys.readouterr().out
    assert cli.main(["audit", "account-read", str(JULY)]) == 1
    assert "compares two periods" in capsys.readouterr().err


def test_the_mcp_tools_take_the_prior_period():
    local = mcp_server.audit_account("account-read", str(JULY), prior_path=str(JUNE))
    web = mcp_server.audit_export("account-read", JULY.read_text(encoding="utf-8"), "export.csv",
                                  prior_text=JUNE.read_text(encoding="utf-8"), prior_name="export.csv")
    assert "EFFICIENCY GAIN" in local and _section(local) == _section(web)

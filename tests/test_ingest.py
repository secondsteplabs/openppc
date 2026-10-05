from pathlib import Path

from openppc.ingest import load_report, parse_number

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_search_terms_export_parses():
    report = load_report(EXAMPLES / "search_terms_acme.csv")
    assert report.title == "Search terms report"
    assert report.days == 31
    assert report.currency == "USD"
    assert len(report.rows) == 18  # Google's two Total lines are skipped
    free = next(r for r in report.rows if r["search_term"] == "free plumbing estimate")
    assert (free["cost"], free["clicks"], free["conversions"]) == (312.0, 41.0, 0.0)


def test_parse_number_handles_google_formats():
    assert parse_number("1,361.04") == 1361.04
    assert parse_number("$6.42") == 6.42
    assert parse_number("9.86%") == 9.86
    assert parse_number("--") is None
    assert parse_number("") is None


def test_utf16_tab_separated_export(tmp_path):
    text = (EXAMPLES / "search_terms_acme.csv").read_text(encoding="utf-8")
    import csv
    import io
    rows = list(csv.reader(io.StringIO(text)))
    tsv = "\n".join("\t".join(r) for r in rows)
    path = tmp_path / "excel_export.csv"
    path.write_bytes(tsv.encode("utf-16"))
    report = load_report(path)
    assert len(report.rows) == 18
    assert sum(r["cost"] for r in report.rows) == 4973.64

import csv
import io
import re
from pathlib import Path

import pytest

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


ACME_CSV = EXAMPLES / "search_terms_acme.csv"


def _edited(tmp_path, line, column, value):
    """The sample export with one cell changed."""
    lines = ACME_CSV.read_text(encoding="utf-8").splitlines()
    cells = next(csv.reader([lines[line]]))
    cells[next(csv.reader([lines[2]])).index(column)] = value
    out = io.StringIO()
    csv.writer(out, lineterminator="").writerow(cells)
    lines[line] = out.getvalue()
    path = tmp_path / "edited.csv"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_a_negative_cost_or_click_count_is_refused(tmp_path):
    for column, value, words in (("Cost", "-12.00", "negative cost"), ("Clicks", "-3", "negative click count")):
        with pytest.raises(ValueError, match=words):
            load_report(_edited(tmp_path, 4, column, value))
    assert len(load_report(_edited(tmp_path, 4, "Conversions", "-1.00")).rows) == 18  # adjustments can be negative


def test_a_row_with_more_cells_than_the_header_is_refused(tmp_path):
    lines = ACME_CSV.read_text(encoding="utf-8").splitlines()
    lines[3] += ",150"  # "2,150" broken into two cells
    path = tmp_path / "broken.csv"
    path.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(ValueError, match="more cells than the header row"):
        load_report(path)


def test_a_european_export_reads_the_same_numbers(tmp_path):
    def european(cell):  # "1,361.04" -> "1.361,04"
        return cell.translate(str.maketrans(",.", ".,")) if re.fullmatch(r"[\d,]+(\.\d+)?%?", cell) else cell
    lines = ACME_CSV.read_text(encoding="utf-8").splitlines()
    want = load_report(ACME_CSV)
    for delim in (";", ","):
        out = io.StringIO()
        writer = csv.writer(out, delimiter=delim, lineterminator="\n")
        for i, line in enumerate(lines):
            cells = next(csv.reader([line]))
            writer.writerow([european(c) for c in cells] if i > 2 else cells)
        path = tmp_path / "european.csv"
        path.write_text(out.getvalue(), encoding="utf-8")
        got = load_report(path)
        assert [(r["cost"], r["clicks"]) for r in got.rows] == [(r["cost"], r["clicks"]) for r in want.rows], delim

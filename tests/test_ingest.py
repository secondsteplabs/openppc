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


def test_a_row_cut_short_or_with_no_cost_is_refused(tmp_path):
    lines = ACME_CSV.read_text(encoding="utf-8").splitlines()
    header = next(csv.reader([lines[2]]))
    cells = next(csv.reader([lines[4]]))[:header.index("Cost")]
    out = io.StringIO()
    csv.writer(out, lineterminator="").writerow(cells)
    path = tmp_path / "short.csv"
    path.write_text("\n".join(lines[:4] + [out.getvalue()] + lines[5:]), encoding="utf-8")
    with pytest.raises(ValueError, match="stops before the Cost column"):
        load_report(path)
    with pytest.raises(ValueError, match="has no Cost figure"):
        load_report(_edited(tmp_path, 4, "Cost", ""))
    assert len(load_report(_edited(tmp_path, 4, "Cost", "--")).rows) == 18  # Google writes -- for none


def test_money_in_a_count_column_is_refused(tmp_path):
    with pytest.raises(ValueError, match=r"money amount \(₹20.00\) in the Conversions column"):
        load_report(_edited(tmp_path, 3, "Conversions", "₹20.00"))


def test_a_note_line_with_no_numbers_is_skipped(tmp_path):
    lines = ACME_CSV.read_text(encoding="utf-8").splitlines()
    path = tmp_path / "note.csv"
    path.write_text("\n".join(lines + ["Downloaded from Google Ads"]), encoding="utf-8")
    assert len(load_report(path).rows) == 18


def test_line_ends_quoted_line_breaks_and_old_encodings_read_as_before(tmp_path):
    # The reader takes the file a piece at a time; these are the cases where pieces could go wrong.
    head = ("Search terms report\nJuly 1, 2026 - July 31, 2026\nSearch term,Match type,Campaign,Ad group,Clicks,Impr.,"
            "Currency code,Cost,Conversions\n")
    rows = '"pipe\nrepair",Exact match,Core,Drains,4,40,USD,12.50,1\ncafé plumber,Exact match,Core,Drains,6,60,USD,7.25,0\n'
    for name, data in (("cr.csv", (head + rows).replace("\n", "\r").encode()),
                       ("crlf.csv", (head + rows).replace("\n", "\r\n").encode()),
                       ("latin1.csv", (head + rows).encode("latin-1"))):
        path = tmp_path / name
        path.write_bytes(data)
        report = load_report(str(path))
        assert [(r["search_term"], r["cost"]) for r in report.rows] == [("pipe\nrepair", 12.5), ("café plumber", 7.25)]
        assert (report.start.day, report.end.day, report.title) == (1, 31, "Search terms report")
    empty = tmp_path / "blank.csv"
    empty.write_text("\n \n\t\n", encoding="utf-8")
    with pytest.raises(ValueError, match="the file is empty"):
        load_report(str(empty))

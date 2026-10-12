import csv
import io
import re
from pathlib import Path

import pytest

from openppc.ingest import column_names, load_report, parse_number
from openppc.templates import run_template

EXAMPLES = Path(__file__).parent.parent / "examples"
FIXTURES = Path(__file__).parent / "fixtures"


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


def test_parse_number_reads_spaces_apostrophes_and_trailing_currency():
    assert parse_number("1\u202f254,40\xa0€", european=True) == 1254.40  # French: narrow no-break space, € after
    assert parse_number("1 234,50 kr", european=True) == 1234.50
    assert parse_number("1'234.56") == parse_number("1\u2019234.56") == 1234.56  # Swiss
    assert parse_number("₹1,19,168.00") == 119168.0  # Indian grouping
    assert parse_number("Rs. 1,234") == 1234.0
    assert parse_number("12.00 USD") == 12.0
    assert parse_number("\u221212") == -12.0  # typographic minus
    assert parse_number("abc") is None


def test_french_export_reads_the_same_as_the_english_one():
    fr = load_report(FIXTURES / "search_terms_fr.csv")
    assert fr.currency == "EUR"
    assert round(sum(r["cost"] for r in fr.rows), 2) == 4347.25
    assert sum(r["impressions"] for r in fr.rows) > 0
    en_in = load_report(FIXTURES / "search_terms_en_in.csv")
    assert en_in.currency == "INR"
    assert round(sum(r["cost"] for r in en_in.rows), 2) == 412988.75


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


def test_windows_1252_reads_the_euro_sign_and_curly_quotes(tmp_path):
    text = ACME_CSV.read_text(encoding="utf-8").replace("plumber near me", "plombier \u2019urgent\u2019 \u20ac")
    path = tmp_path / "excel_save_as.csv"
    path.write_bytes(text.encode("cp1252"))
    report = load_report(path)
    assert report.rows[0]["search_term"] == "plombier \u2019urgent\u2019 \u20ac"  # Latin-1 made these control codes
    assert report.notes == ["the file is not in Unicode, so it was read as Western European: check accented names"]
    assert load_report(ACME_CSV).notes == []


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-16-be"])
def test_utf16_without_a_byte_order_mark(tmp_path, encoding):
    path = tmp_path / "no_bom.csv"
    path.write_bytes(ACME_CSV.read_text(encoding="utf-8").encode(encoding))
    report = load_report(path)
    assert len(report.rows) == 18
    assert round(sum(r["cost"] for r in report.rows), 2) == 4973.64
    assert report.notes == []


PIPES = {"free plumbing estimate": "free | plumbing estimate", "plumber jobs hiring": "plumber || jobs",
         "plumbing franchise cost": "franchise \\| cost"}


@pytest.mark.parametrize("template, export", [("search-term-waste", "search_terms_acme.csv"),
                                              ("keyword-audit", "keywords_acme.csv")])
def test_a_name_with_pipes_passes_its_own_number_check(tmp_path, template, export):
    text = (EXAMPLES / export).read_text(encoding="utf-8")
    for plain, piped in PIPES.items():
        text = text.replace(plain, piped)
    path = tmp_path / export
    path.write_text(text, encoding="utf-8")
    markdown, _, passed = run_template(template, str(path))
    assert passed
    if template == "search-term-waste":
        assert "free \\| plumbing estimate" in markdown


def test_column_names_for_a_report_are_the_header_row_and_nothing_else(tmp_path):
    german = column_names(FIXTURES / "search_terms_german_headers.csv")
    assert german == "Suchbegriff Keyword-Option Kampagne Anzeigengruppe Klicks Impr. Kosten Conversions".split()
    no_header = tmp_path / "rows.csv"
    no_header.write_text("Some title\nplumber,12,3.50\nboiler,4,1.20\n", encoding="utf-8")
    workbook = tmp_path / "terms.xlsx"
    workbook.write_bytes(b"PK\x03\x04" + b"\0" * 64)
    assert column_names(no_header) == column_names(workbook) == column_names(tmp_path / "missing.csv") == []


def test_rows_in_two_currencies_are_refused(tmp_path):
    with pytest.raises(ValueError, match=r"more than one currency \(EUR, USD\)"):
        load_report(_edited(tmp_path, 4, "Currency code", "EUR"))
    assert load_report(_edited(tmp_path, 4, "Currency code", "usd")).currency == "USD"


def test_a_report_says_when_it_read_decimal_commas():
    fr = load_report(FIXTURES / "search_terms_fr.csv")
    assert fr.notes == ["numbers read with decimal commas, as the file writes them"]
    markdown, _, passed = run_template("search-term-waste", str(FIXTURES / "search_terms_fr.csv"))
    assert passed
    assert "_How the file was read: numbers read with decimal commas, as the file writes them._" in markdown

"""Read a report exported from the Google Ads UI (Download > .csv).

Real exports are messy, so this handles: a report title and a date-range line above
the header (US or day-first dates), UTF-16 "Excel" exports (tab separated), thousands
separators, European number style ("1.361,04", usually with semicolons), currency and
percent signs, "--" for empty cells, and the "Total:" rows Google appends. Those totals
are ignored; every total is recomputed from the rows.

Microsoft Advertising reports read the same way (experimental): their column names (Spend,
Conv., Campaign name, Delivered match type) map to the same columns, the "Report Time:" line
gives the dates, and the totals and copyright rows under the table are skipped.

So do Meta Ads Manager exports (experimental), known by their Reporting starts column: Link
clicks are clicks, Amount spent (EUR) is the cost in that currency, the rows' Reporting starts
and ends give the period, and Results are conversions only when every row counts the same kind
of result, as the Result indicator column says.

Read-only by construction: this module opens one local file and nothing else.
"""
import codecs
import csv
import datetime as dt
import itertools
import os
import re
from array import array
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

# canonical column -> header names Google and Microsoft Advertising have used for it (lower-case)
ALIASES = {
    "search_term": ["search term", "search query"],
    "keyword": ["keyword", "search keyword"],
    "match_type": ["match type", "search keyword match type", "search term match type", "delivered match type"],
    "added_excluded": ["added/excluded"],
    "campaign": ["campaign", "campaign name"],
    "campaign_type": ["campaign type"],
    "ad_group": ["ad group", "ad group name"],
    "clicks": ["clicks"],
    "impressions": ["impr.", "impressions"],
    "cost": ["cost", "spend"],
    "conversions": ["conversions", "conv."],
    "quality_score": ["quality score", "qual. score"],
    "currency": ["currency code", "currency"],
}
HEADER_LINES = 50  # a report's title, date and filter lines above the header row
GOOGLE, MICROSOFT, META = "Google Ads", "Microsoft Advertising", "Meta Ads Manager"
# Meta's own words for the same columns, read only in a file with a Reporting starts column, so a Google export with
# a column named Results is never misread
META_MARK = "reporting starts"
META_ALIASES = {"link clicks": "clicks", "results": "conversions", "ad set name": "ad_group",
                "result indicator": "result_indicator", "reporting starts": "date_start", "reporting ends": "date_end"}
AMOUNT_SPENT = re.compile(r"amount spent \(([a-z]{3})\)")
MS_DATES = re.compile(r"Report Time:\s*(\d{1,2}/\d{1,2}/\d{4})\s*,\s*(\d{1,2}/\d{1,2}/\d{4})")
MS_PREAMBLE = re.compile(r'^"?(?:Report Name|Report Time):')
EDITOR_COLUMNS = ("criteriontype", "campaignstatus", "adgroupstatus")
NUMERIC = {"clicks", "impressions", "cost", "conversions", "quality_score"}
COUNTS = ("clicks", "impressions", "conversions", "quality_score")  # never money
MONEY_MARK = re.compile(r"[$€£₹¥]|\bRs\.?|\b(?:USD|INR|EUR|GBP|AUD|CAD|NZD|JPY)\b")
DATE_RANGE = re.compile(r"([A-Z][a-z]+\.? \d{1,2}, \d{4}|\d{1,2} [A-Z][a-z]+\.? \d{4})\s*[-–—]\s*"
                        r"([A-Z][a-z]+\.? \d{1,2}, \d{4}|\d{1,2} [A-Z][a-z]+\.? \d{4})")
TOTAL_ROW = re.compile(r"^\s*total\s*:", re.I)  # "Total: Account"; a search term like "total gym" is data
EU_NUMBER = re.compile(r"^-?[\d.]*\d,\d{1,2}%?$")  # "1.361,04", "5,23%"
US_NUMBER = re.compile(r"^-?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{1,2})%?$")  # "1,361.04", "5.23%"
DOTTED = re.compile(r"-?\d{1,3}(?:\.\d{3})+")  # "1.450": European thousands, or nothing to go on
GROUPING = str.maketrans({"'": None, "’": None, "−": "-"})  # "1'234.56" (Swiss), "−5" (typographic minus)
DECORATION = re.compile(r"^(?:Rs\.|[^\d.\-])+|[^\d%]+$")  # a currency mark or code before or after the number


@dataclass
class Report:
    rows: list[dict[str, Any]] = field(default_factory=list)
    columns: set[str] = field(default_factory=set)
    source: str = ""
    title: str = ""
    start: dt.date | None = None
    end: dt.date | None = None
    currency: str = "USD"
    notes: list[str] = field(default_factory=list)  # how the file was read, when that is not the plain way
    platform: str = GOOGLE
    result: str = ""  # Meta: the one kind of result its Results column counts, or "" when it counts none

    @property
    def days(self) -> int | None:
        return (self.end - self.start).days + 1 if (self.start and self.end) else None

    def has(self, *columns):
        return all(c in self.columns for c in columns)


def _compact(cell):
    """The number as written, without what only decorates it: spaces of any kind and apostrophes used as
    thousands marks ('1 254,40', "1'234.56") and a currency mark on either side ('1 254,40 €', '₹95,617.50')."""
    return DECORATION.sub("", "".join(str(cell).split()).translate(GROUPING))


def parse_number(cell, european=False):
    """'1,361.04' -> 1361.04, '$6.42' -> 6.42, '9.86%' -> 9.86, '--' or '' -> None.
    European style swaps the two marks: '1.361,04' -> 1361.04, '1 254,40 €' -> 1254.4."""
    if cell is None:
        return None
    text = _compact(cell)
    if european:
        text = text.replace(".", "").replace(",", ".")
    text = text.replace(",", "").replace("%", "")
    if text in ("", "-", ".", "--"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _date(text):
    text = text.replace(".", "")
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _decodes(path, encoding):
    """Whether the whole file reads as this encoding, checked a megabyte at a time."""
    decoder = codecs.getincrementaldecoder(encoding)()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                decoder.decode(chunk)
        decoder.decode(b"", final=True)
        return True
    except UnicodeDecodeError:
        return False


def _utf16_without_bom(head):
    """'utf-16-le' or 'utf-16-be' when the first bytes are text with every other byte zero, as UTF-16 writes
    Latin letters and digits; else None. Such a file is valid UTF-8 too, so this is asked first."""
    even, odd = head[0:len(head) - len(head) % 2:2], head[1::2]
    if len(odd) < 8:
        return None
    if odd.count(0) >= 0.4 * len(odd) and even.count(0) <= 0.05 * len(even):
        return "utf-16-le"
    if even.count(0) >= 0.4 * len(even) and odd.count(0) <= 0.05 * len(odd):
        return "utf-16-be"
    return None


def _encoding(path, head):
    """UTF-16 when the file starts with its byte order mark (Excel's tab-separated exports) or plainly is UTF-16
    without one, else UTF-8, else Windows-1252 (Western European, what Excel saves as "CSV" on Windows), else
    Latin-1, which reads any bytes. The whole file decides, as if it were read in one go."""
    if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        if not _decodes(path, "utf-16"):
            with open(path, "rb") as f:
                f.read().decode("utf-16")  # raises the decoder's own error about the broken file
        return "utf-16"
    bare = _utf16_without_bom(head)
    if bare and _decodes(path, bare):
        return bare
    return next(e for e in ("utf-8-sig", "cp1252", "latin-1") if e == "latin-1" or _decodes(path, e))


def _lines(f):
    """The file's lines, as str.splitlines() splits them, read a piece at a time."""
    for line in f:
        yield from line.splitlines()


def _ended(lines):
    """Each line with the line end csv reads it by, but the last: what io.StringIO("\\n".join(lines)) would give."""
    last = None
    for line in lines:
        if last is not None:
            yield last + "\n"
        last = line
    if last is not None:
        yield last


def _canonical(header, meta=False):
    name = (header or "").strip().lower()
    if meta and AMOUNT_SPENT.fullmatch(name):
        return "cost"
    if meta and name in META_ALIASES:
        return META_ALIASES[name]
    for key, names in ALIASES.items():
        if name in names:
            return key
    return None


def _find_header(lines):
    """(index, delimiter, keys, meta) of the header row: the first line with Clicks and Cost columns."""
    for i, line in enumerate(lines[:HEADER_LINES]):
        for delim in (",", "\t", ";"):
            cells = next(csv.reader([line], delimiter=delim), [])
            meta = META_MARK in (c.strip().lower() for c in cells)
            keys = [_canonical(c, meta) for c in cells]
            if "clicks" in keys and "cost" in keys:
                return i, delim, keys, meta
    return None


def _day(text):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return _date(text)


def squash(header):
    """'Campaign Status' and 'campaign_status' -> 'campaignstatus'."""
    return re.sub(r"[\s_]+", "", (header or "").strip().lower())


def editor_header(lines):
    """(index, delimiter, cells) of a Google Ads Editor export's header row in these lines, or None. Editor writes
    Criterion Type, or Campaign Status and Ad Group Status, which no report download has."""
    for i, line in enumerate(lines[:HEADER_LINES]):
        for delim in ("\t", ",", ";"):
            cells = next(csv.reader([line], delimiter=delim), [])
            names = {squash(c) for c in cells}
            if EDITOR_COLUMNS[0] in names or set(EDITOR_COLUMNS[1:]) <= names:
                return i, delim, cells
    return None


def _not_a_report(path, raw):
    """Why a file is plainly not a report export, or None. Google Ads offers .xlsx and .pdf in the same
    Download menu as .csv, so those are the usual mix-ups."""
    if raw.startswith(b"PK\x03\x04"):
        if str(path).lower().endswith(".zip"):
            return "this is a zip file. Unzip it, then add the .csv inside."
        return ("this is an Excel workbook, not a .csv. In Google Ads choose Download > .csv, or open the file "
                "in Excel or Google Sheets and save it as .csv.")
    if raw.startswith(b"\xd0\xcf\x11\xe0"):
        return ("this is an old Excel workbook (.xls), not a .csv. In Google Ads choose Download > .csv, or open "
                "the file in Excel and save it as .csv.")
    if raw.startswith(b"%PDF"):
        return "this is a PDF. OpenPPC needs the data itself: in Google Ads choose Download > .csv."
    return None


def not_a_folder(path):
    """Refuse a folder given where a file belongs, which Windows would only call 'Permission denied'."""
    if os.path.isdir(path):
        raise ValueError(f"{path} is a folder. Give the name of a file in it.")


def read_text(path):
    """A whole text file, such as an audit to check, decoded the way an export is: UTF-16, UTF-8, Windows-1252."""
    not_a_folder(path)
    with open(path, "rb") as f:
        head = f.read(4096)
    with open(path, encoding=_encoding(path, head)) as f:
        return f.read()


def column_names(path):
    """For a report about a file that could not be read: its column names, and nothing else from it. The first of
    the first HEADER_LINES lines that splits into three or more short cells without a digit, as a header row does
    and a title, a date range or a row of figures doesn't; else none."""
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
        if _not_a_report(path, head):
            return []
        with open(path, encoding=_encoding(path, head)) as f:
            first = list(itertools.islice(_lines(f), HEADER_LINES))
    except (OSError, UnicodeDecodeError, ValueError):
        return []
    for line in first:
        for delim in (",", "\t", ";"):
            cells = [c.strip() for c in next(csv.reader([line], delimiter=delim), [])]
            if len(cells) >= 3 and all(c and len(c) <= 60 and not any(ch.isdigit() for ch in c) for c in cells):
                return cells
    return []


LEGACY = "the file is not in Unicode, so it was read as Western European: check accented names"


@contextmanager
def lines_of(path):
    """(lines, encoding): an export's lines, decoded as UTF-16, UTF-8 or Windows-1252, read a piece at a time."""
    not_a_folder(path)
    with open(path, "rb") as f:
        head = f.read(4096)
    problem = _not_a_report(path, head)
    if problem:
        raise ValueError(f"{path}: {problem}")
    encoding = _encoding(path, head)
    with open(path, encoding=encoding) as f:
        yield _lines(f), encoding


def records(first, idx, rest, delim):
    """The rows under the header row first[idx], then the rest of the file's lines, as csv reads them."""
    return csv.reader(_ended(itertools.chain(first[idx + 1:], rest)), delimiter=delim)


def _style(cell):
    """(decimal comma, decimal point, dotted thousands) for how one number cell is written."""
    c = _compact(cell)
    return (bool(EU_NUMBER.match(c)), bool(US_NUMBER.match(c)), bool(DOTTED.fullmatch(c))) if c else (0, 0, 0)


def _european(eu, us, dotted, delim):
    return eu > 0 or (delim == ";" and not us and dotted)


def decimal_commas(cells, delim, name):
    """Whether these number cells write decimals with a comma ("1.250,00"), decided for all of them at once, as a
    report's numbers are. Cells in both styles are refused."""
    eu = us = 0
    dotted = False
    for cell in cells:
        e, u, d = _style(cell)
        eu, us, dotted = eu + e, us + u, dotted or d
    if eu and us:
        raise ValueError(f"{name}: the numbers mix two styles (1,234.56 and 1.234,56), so they cannot be read "
                         "safely. Export the file again.")
    return _european(eu, us, dotted, delim)


def load_report(path: str | os.PathLike[str]) -> Report:
    """Read the export a piece at a time: a 250,000-row file is never held as text, lines and cells at once."""
    with lines_of(path) as (lines, encoding):
        report = _read(path, lines)
    if encoding in ("cp1252", "latin-1"):
        report.notes.insert(0, LEGACY)
    return report


def _read(path, lines):
    first = list(itertools.islice(lines, HEADER_LINES))
    if not any(line.strip() for line in first) and not any(line.strip() for line in lines):
        raise ValueError(f"{path}: the file is empty.")
    found = _find_header(first)
    if not found:
        if editor_header(first):
            raise ValueError(f"{path} is a Google Ads Editor export. Use it with the account-structure template; "
                             "the other templates read reports downloaded from the Google Ads website.")
        if any(AMOUNT_SPENT.search(line.lower()) and "link clicks" in line.lower() for line in first):
            raise ValueError(f"{path} looks like a Meta Ads Manager export without its Reporting starts and "
                             "Reporting ends columns, which give its period. Add them in Ads Manager and export "
                             "again.")
        raise ValueError(
            f"{path}: no header row with Clicks and Cost columns in the first {HEADER_LINES} lines. "
            "Export the report from the Google Ads UI with Download > .csv. If Google Ads is set to another "
            "language, the column names will not match: switch it to English and download again.")
    idx, delim, keys, meta = found
    report = Report(columns={k for k in keys if k}, source=str(path), platform=META if meta else GOOGLE)
    for line in first[:idx]:
        m = DATE_RANGE.search(line) or MS_DATES.search(line)
        if MS_PREAMBLE.match(line.strip()):
            report.platform = MICROSOFT
        if m:
            report.start, report.end = _date(m.group(1)), _date(m.group(2))
        elif line.strip() and not report.title:
            report.title = line.strip().strip('"').strip().removeprefix("Report Name:").strip()
    if "spend" in (c.strip().lower() for c in next(csv.reader([first[idx]], delimiter=delim))):
        report.platform = MICROSOFT  # Google Ads calls it Cost
    name_at = next((keys.index(k) for k in ("search_term", "keyword") if k in keys), None)
    entity_at = [keys.index(k) for k in ("campaign", "ad_group") if k in keys] if meta else []
    names = [c.strip() for c in next(csv.reader([first[idx]], delimiter=delim))]
    numeric = [i for i, k in enumerate(keys) if k in NUMERIC]
    again = "The file looks damaged or hand-edited: download it again with Download > .csv."
    eu = us = 0  # how the numbers are written ("1.361,04" or "1,361.04"), which decides how all of them are read
    dotted = False
    pool, line_of = {}, array("q")  # one copy of each text value; each row's line, for a refusal after reading
    for n, cells in enumerate(records(first, idx, lines, delim), idx + 2):
        if not any(c.strip() for c in cells):
            continue
        lead = next(c for c in cells if c.strip())
        name = cells[name_at] if name_at is not None and name_at < len(cells) else None
        # Google's "Total: Account"; Microsoft's "Total" with no search term. A term like "total gym" is data.
        if TOTAL_ROW.match(lead) or name and TOTAL_ROW.match(name) or (
                name is not None and not name.strip() and lead.strip().lower().startswith("total")):
            continue
        if entity_at and not any(i < len(cells) and cells[i].strip() for i in entity_at):
            continue  # Meta's summary row: figures for the whole file, under no campaign or ad set
        if not any(i < len(cells) and cells[i].strip() for i in numeric):
            continue  # a note under the table, not a row
        # a broken file must be refused, never read with its numbers in the wrong columns
        if any(c.strip() for c in cells[len(keys):]):
            raise ValueError(f"{path}: line {n} has more cells than the header row, so its numbers would land in the "
                             f"wrong columns. {again}")
        if any(i >= len(cells) for i in numeric):
            raise ValueError(f"{path}: line {n} stops before the {names[min(i for i in numeric if i >= len(cells))]} "
                             f"column, so some of its numbers are missing. {again}")
        blank = next((names[keys.index(k)] for k in ("cost", "clicks") if not cells[keys.index(k)].strip()), None)
        if blank and not meta:  # Meta leaves a cell blank for none; Google Ads never does
            raise ValueError(f"{path}: line {n} has no {blank} figure. Google Ads always writes one (0 or -- when "
                             f"there is none). {again}")
        money = next((i for i, k in enumerate(keys) if k in COUNTS and MONEY_MARK.search(cells[i])), None)
        if money is not None:
            raise ValueError(f"{path}: line {n} has a money amount ({cells[money].strip()}) in the {names[money]} "
                             f"column, which only holds counts, so the columns look shifted. {again}")
        for i in numeric:
            e, u, d = _style(cells[i])
            eu, us, dotted = eu + e, us + u, dotted or d
        row = {}
        for key, cell in zip(keys, cells):
            if key:  # numbers stay as written until the file says how to read them
                row[key] = cell if key in NUMERIC else pool.setdefault(cell.strip(), cell.strip())
        report.rows.append(row)
        line_of.append(n)
    if not report.rows:
        raise ValueError(f"{path}: the export has a header row but no rows of data. Check the date range in Google "
                         "Ads (a range with no traffic exports no rows), then download it again.")
    if eu and us:
        raise ValueError(f"{path}: the numbers mix two styles (1,234.56 and 1.234,56), so they cannot be read "
                         "safely. Download the report again with Download > .csv.")
    european = _european(eu, us, dotted, delim)
    if european:
        report.notes.append("numbers read with decimal commas, as the file writes them")
    for n, row in zip(line_of, report.rows):
        for key in NUMERIC:
            if key in row:
                row[key] = parse_number(row[key], european)
        negative = next((k for k in ("cost", "clicks", "impressions") if (row.get(k) or 0) < 0), None)
        if negative:
            what = {"cost": "cost", "clicks": "click count", "impressions": "impression count"}[negative]
            raise ValueError(f"{path}: line {n} has a negative {what} ({row[negative]:g}). Google Ads never exports "
                             "one, so the file was edited or is damaged: download it again with Download > .csv.")
    currencies = {r["currency"].upper() for r in report.rows if r.get("currency")}
    if len(currencies) > 1:
        raise ValueError(f"{path}: the rows are in more than one currency ({', '.join(sorted(currencies))}), so "
                         "their costs can't be added up. Download one account, or one currency, per file.")
    if currencies:
        report.currency = currencies.pop()
    if meta:
        _read_meta(report, path, names)
    return report


def _read_meta(report, path, names):
    """A Meta export's currency is in its Amount spent header, its period in the rows, and its Results are
    conversions only when every row counts the same kind of result."""
    spent = next((m[1] for c in names if (m := AMOUNT_SPENT.fullmatch(c.lower()))), None)
    if spent and "currency" not in report.columns:
        report.currency = spent.upper()
    days = [d for r in report.rows for k in ("date_start", "date_end") if r.get(k) and (d := _day(r[k]))]
    if days:
        report.start, report.end = min(days), max(days)
    kinds = sorted({r.get("result_indicator") or "" for r in report.rows} - {""})
    if len(kinds) > 1:
        raise ValueError(f"{path}: the Results column counts different things in different rows "
                         f"({', '.join(kinds[:4])}), so it can't be added up as conversions. In Ads Manager, export "
                         "campaigns that share one result type, or one file per result type.")
    report.result = kinds[0] if kinds else ""
    if "conversions" in report.columns and "result_indicator" not in report.columns:
        report.columns.discard("conversions")
        for r in report.rows:
            r.pop("conversions", None)
        report.notes.append("Meta's link clicks counted as clicks; its Results not counted as conversions, since "
                            "the file has no Result indicator column to say what they are")
    elif "conversions" in report.columns:
        report.notes.append("Meta's link clicks counted as clicks and its Results as conversions")
    else:
        report.notes.append("Meta's link clicks counted as clicks")

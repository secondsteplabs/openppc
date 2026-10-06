"""Read a report exported from the Google Ads UI (Download > .csv).

Real exports are messy, so this handles: a report title and a date-range line above
the header (US or day-first dates), UTF-16 "Excel" exports (tab separated), thousands
separators, European number style ("1.361,04", usually with semicolons), currency and
percent signs, "--" for empty cells, and the "Total:" rows Google appends. Those totals
are ignored; every total is recomputed from the rows.

Read-only by construction: this module opens one local file and nothing else.
"""
import codecs
import csv
import datetime as dt
import itertools
import re
from array import array
from dataclasses import dataclass, field

# canonical column -> header names Google has used for it (lower-case)
ALIASES = {
    "search_term": ["search term"],
    "keyword": ["keyword", "search keyword"],
    "match_type": ["match type", "search keyword match type", "search term match type"],
    "added_excluded": ["added/excluded"],
    "campaign": ["campaign"],
    "campaign_type": ["campaign type"],
    "ad_group": ["ad group"],
    "clicks": ["clicks"],
    "impressions": ["impr.", "impressions"],
    "cost": ["cost"],
    "conversions": ["conversions"],
    "quality_score": ["quality score", "qual. score"],
    "currency": ["currency code", "currency"],
}
NUMERIC = {"clicks", "impressions", "cost", "conversions", "quality_score"}
COUNTS = ("clicks", "impressions", "conversions", "quality_score")  # never money
MONEY_MARK = re.compile(r"[$€£₹¥]|\bRs\.?|\b(?:USD|INR|EUR|GBP|AUD|CAD|NZD|JPY)\b")
DATE_RANGE = re.compile(r"([A-Z][a-z]+\.? \d{1,2}, \d{4}|\d{1,2} [A-Z][a-z]+\.? \d{4})\s*[-–—]\s*"
                        r"([A-Z][a-z]+\.? \d{1,2}, \d{4}|\d{1,2} [A-Z][a-z]+\.? \d{4})")
TOTAL_ROW = re.compile(r"^\s*total\s*:", re.I)  # "Total: Account"; a search term like "total gym" is data
EU_NUMBER = re.compile(r"^-?[\d.]*\d,\d{1,2}%?$")  # "1.361,04", "5,23%"
US_NUMBER = re.compile(r"^-?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{1,2})%?$")  # "1,361.04", "5.23%"
DOTTED = re.compile(r"-?\d{1,3}(?:\.\d{3})+")  # "1.450": European thousands, or nothing to go on


@dataclass
class Report:
    rows: list = field(default_factory=list)
    columns: set = field(default_factory=set)
    source: str = ""
    title: str = ""
    start: dt.date = None
    end: dt.date = None
    currency: str = "USD"

    @property
    def days(self):
        return (self.end - self.start).days + 1 if (self.start and self.end) else None

    def has(self, *columns):
        return all(c in self.columns for c in columns)


def parse_number(cell, european=False):
    """'1,361.04' -> 1361.04, '$6.42' -> 6.42, '9.86%' -> 9.86, '--' or '' -> None.
    European style swaps the two marks: '1.361,04' -> 1361.04."""
    if cell is None:
        return None
    text = str(cell).strip()
    if european:
        text = text.replace(".", "").replace(",", ".")
    text = text.replace(",", "").replace("%", "")
    text = re.sub(r"^[^\d.\-]+", "", text)
    if text in ("", "-", ".", "--"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _date(text):
    text = text.replace(".", "")
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
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


def _encoding(path, head):
    """UTF-16 when the file starts with its byte order mark (Excel's tab-separated exports), else UTF-8, else
    Latin-1, which reads any bytes. The whole file decides, as if it were read in one go."""
    if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        if not _decodes(path, "utf-16"):
            with open(path, "rb") as f:
                f.read().decode("utf-16")  # raises the decoder's own error about the broken file
        return "utf-16"
    return "utf-8-sig" if _decodes(path, "utf-8-sig") else "latin-1"


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


def _canonical(header):
    name = (header or "").strip().lower()
    for key, names in ALIASES.items():
        if name in names:
            return key
    return None


def _find_header(lines):
    for i, line in enumerate(lines[:15]):
        for delim in (",", "\t", ";"):
            keys = [_canonical(c) for c in next(csv.reader([line], delimiter=delim), [])]
            if "clicks" in keys and "cost" in keys:
                return i, delim, keys
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


def load_report(path):
    """Read the export a piece at a time: a 250,000-row file is never held as text, lines and cells at once."""
    with open(path, "rb") as f:
        head = f.read(4)
    problem = _not_a_report(path, head)
    if problem:
        raise ValueError(f"{path}: {problem}")
    with open(path, encoding=_encoding(path, head)) as f:
        return _read(path, _lines(f))


def _read(path, lines):
    first = list(itertools.islice(lines, 15))
    if not any(line.strip() for line in first) and not any(line.strip() for line in lines):
        raise ValueError(f"{path}: the file is empty.")
    found = _find_header(first)
    if not found:
        raise ValueError(
            f"{path}: no header row with Clicks and Cost columns in the first 15 lines. "
            "Export the report from the Google Ads UI with Download > .csv. If Google Ads is set to another "
            "language, the column names will not match: switch it to English and download again.")
    idx, delim, keys = found
    report = Report(columns={k for k in keys if k}, source=str(path))
    for line in first[:idx]:
        m = DATE_RANGE.search(line)
        if m:
            report.start, report.end = _date(m.group(1)), _date(m.group(2))
        elif line.strip() and not report.title:
            report.title = line.strip().strip('"').strip()
    name_at = next((keys.index(k) for k in ("search_term", "keyword") if k in keys), None)
    names = [c.strip() for c in next(csv.reader([first[idx]], delimiter=delim))]
    numeric = [i for i, k in enumerate(keys) if k in NUMERIC]
    again = "The file looks damaged or hand-edited: download it again with Download > .csv."
    eu = us = 0  # how the numbers are written ("1.361,04" or "1,361.04"), which decides how all of them are read
    dotted = False
    pool, line_of = {}, array("q")  # one copy of each text value; each row's line, for a refusal after reading
    records = csv.reader(_ended(itertools.chain(first[idx + 1:], lines)), delimiter=delim)
    for n, cells in enumerate(records, idx + 2):
        if (not any(c.strip() for c in cells) or TOTAL_ROW.match(next(c for c in cells if c.strip()))
                or name_at is not None and name_at < len(cells) and TOTAL_ROW.match(cells[name_at])):
            continue
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
        if blank:
            raise ValueError(f"{path}: line {n} has no {blank} figure. Google Ads always writes one (0 or -- when "
                             f"there is none). {again}")
        money = next((i for i, k in enumerate(keys) if k in COUNTS and MONEY_MARK.search(cells[i])), None)
        if money is not None:
            raise ValueError(f"{path}: line {n} has a money amount ({cells[money].strip()}) in the {names[money]} "
                             f"column, which only holds counts, so the columns look shifted. {again}")
        for i in numeric:
            c = cells[i].strip()
            if c:
                eu += bool(EU_NUMBER.match(c))
                us += bool(US_NUMBER.match(c))
                dotted = dotted or bool(DOTTED.fullmatch(c))
        row = {}
        for key, cell in zip(keys, cells):
            if key:  # numbers stay as written until the file says how to read them
                row[key] = cell if key in NUMERIC else pool.setdefault(cell.strip(), cell.strip())
        report.rows.append(row)
        line_of.append(n)
    if eu and us:
        raise ValueError(f"{path}: the numbers mix two styles (1,234.56 and 1.234,56), so they cannot be read "
                         "safely. Download the report again with Download > .csv.")
    european = eu > 0 or (delim == ";" and not us and dotted)
    for n, row in zip(line_of, report.rows):
        for key in NUMERIC:
            if key in row:
                row[key] = parse_number(row[key], european)
        negative = next((k for k in ("cost", "clicks", "impressions") if (row.get(k) or 0) < 0), None)
        if negative:
            what = {"cost": "cost", "clicks": "click count", "impressions": "impression count"}[negative]
            raise ValueError(f"{path}: line {n} has a negative {what} ({row[negative]:g}). Google Ads never exports "
                             "one, so the file was edited or is damaged: download it again with Download > .csv.")
    currency = next((r.get("currency") for r in report.rows if r.get("currency")), None)
    if currency:
        report.currency = currency.upper()
    return report

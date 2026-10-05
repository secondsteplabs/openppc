"""Read a report exported from the Google Ads UI (Download > .csv).

Real exports are messy, so this handles: a report title and a date-range line above
the header (US or day-first dates), UTF-16 "Excel" exports (tab separated), thousands
separators, European number style ("1.361,04", usually with semicolons), currency and
percent signs, "--" for empty cells, and the "Total:" rows Google appends. Those totals
are ignored; every total is recomputed from the rows.

Read-only by construction: this module opens one local file and nothing else.
"""
import csv
import datetime as dt
import io
import re
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
DATE_RANGE = re.compile(r"([A-Z][a-z]+\.? \d{1,2}, \d{4}|\d{1,2} [A-Z][a-z]+\.? \d{4})\s*[-–—]\s*"
                        r"([A-Z][a-z]+\.? \d{1,2}, \d{4}|\d{1,2} [A-Z][a-z]+\.? \d{4})")
TOTAL_ROW = re.compile(r"^\s*total\s*:", re.I)  # "Total: Account"; a search term like "total gym" is data
EU_NUMBER = re.compile(r"^-?[\d.]*\d,\d{1,2}%?$")  # "1.361,04", "5,23%"
US_NUMBER = re.compile(r"^-?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{1,2})%?$")  # "1,361.04", "5.23%"


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


def _decode(raw):
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


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


def _european(rows, keys, path, delim):
    """Whether the numbers are written European style ("1.361,04"). The cells decide; a semicolon file whose
    only marks are dots between thousands ("1.450") is European too. A file that mixes both styles cannot be
    read safely, so it is refused rather than guessed."""
    cols = [i for i, k in enumerate(keys) if k in NUMERIC]
    cells = [r[i].strip() for r in rows for i in cols if i < len(r) and r[i].strip()]
    eu = sum(bool(EU_NUMBER.match(c)) for c in cells)
    us = sum(bool(US_NUMBER.match(c)) for c in cells)
    if eu and us:
        raise ValueError(f"{path}: the numbers mix two styles (1,234.56 and 1.234,56), so they cannot be read "
                         "safely. Download the report again with Download > .csv.")
    dotted = any(re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", c) for c in cells)
    return eu > 0 or (delim == ";" and not us and dotted)


def load_report(path):
    with open(path, "rb") as f:
        raw = f.read()
    problem = _not_a_report(path, raw)
    if problem:
        raise ValueError(f"{path}: {problem}")
    text = _decode(raw)
    if not text.strip():
        raise ValueError(f"{path}: the file is empty.")
    lines = text.splitlines()
    found = _find_header(lines)
    if not found:
        raise ValueError(
            f"{path}: no header row with Clicks and Cost columns in the first 15 lines. "
            "Export the report from the Google Ads UI with Download > .csv. If Google Ads is set to another "
            "language, the column names will not match: switch it to English and download again.")
    idx, delim, keys = found
    report = Report(columns={k for k in keys if k}, source=str(path))
    for line in lines[:idx]:
        m = DATE_RANGE.search(line)
        if m:
            report.start, report.end = _date(m.group(1)), _date(m.group(2))
        elif line.strip() and not report.title:
            report.title = line.strip().strip('"').strip()
    body = list(csv.reader(io.StringIO("\n".join(lines[idx + 1:])), delimiter=delim))
    name_at = next((keys.index(k) for k in ("search_term", "keyword") if k in keys), None)
    data = [(n, cells) for n, cells in enumerate(body, idx + 2)
            if any(c.strip() for c in cells)
            and not TOTAL_ROW.match(next(c for c in cells if c.strip()))
            and not (name_at is not None and name_at < len(cells) and TOTAL_ROW.match(cells[name_at]))]
    for n, cells in data:  # a broken file must be refused, never read with its numbers in the wrong columns
        if any(c.strip() for c in cells[len(keys):]):
            raise ValueError(f"{path}: line {n} has more cells than the header row, so its numbers would land in the "
                             "wrong columns. The file looks damaged or hand-edited: download it again with "
                             "Download > .csv.")
    european = _european([cells for _, cells in data], keys, path, delim)
    for n, cells in data:
        row = {}
        for key, cell in zip(keys, cells):
            if key:
                row[key] = parse_number(cell, european) if key in NUMERIC else cell.strip()
        negative = next((k for k in ("cost", "clicks", "impressions") if (row.get(k) or 0) < 0), None)
        if negative:
            what = {"cost": "cost", "clicks": "click count", "impressions": "impression count"}[negative]
            raise ValueError(f"{path}: line {n} has a negative {what} ({row[negative]:g}). Google Ads never exports "
                             "one, so the file was edited or is damaged: download it again with Download > .csv.")
        report.rows.append(row)
    currency = next((r.get("currency") for r in report.rows if r.get("currency")), None)
    if currency:
        report.currency = currency.upper()
    return report

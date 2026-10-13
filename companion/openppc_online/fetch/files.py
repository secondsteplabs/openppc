"""What `openppc-online fetch` writes: the files the core's templates read, under fixed names, only inside --out.
Nothing is written until every answer is in, and a file already there is replaced only with --force."""
import csv
import datetime as dt
import io
import json
import os
from pathlib import Path
from typing import Any

DAYS = 30
NAMES = frozenset({"search_terms.csv", "keywords.csv", "account.json", "account_structure.json"})


def window(days: int, today: dt.date | None = None) -> tuple[dt.date, dt.date, dt.date, dt.date]:
    """(start, end, prior start, prior end): the last full days, and as many days just before them."""
    end = (today or dt.date.today()) - dt.timedelta(days=1)
    start = end - dt.timedelta(days=days - 1)
    return start, end, start - dt.timedelta(days=days), start - dt.timedelta(days=1)


def long_date(d: dt.date) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def span(start: dt.date, end: dt.date, prior_start: dt.date, prior_end: dt.date) -> str:
    return f"{long_date(start)} to {long_date(end)} vs {long_date(prior_start)} to {long_date(prior_end)}"


def report(title: str, start: dt.date, end: dt.date, header: list[str], rows: list[list[Any]]) -> str:
    """A report as the platform's website exports it: a title, the dates, then the table."""
    out = io.StringIO()
    out.write(f"{title}\n{long_date(start)} - {long_date(end)}\n")
    csv.writer(out, lineterminator="\n").writerows([header, *rows])
    return out.getvalue()


def as_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def folder(out: str | os.PathLike[str], names: list[str], force: bool) -> Path:
    """The --out folder, checked before anything is downloaded."""
    path = Path(out)
    if path.exists() and not path.is_dir():
        raise ValueError(f"{out} is a file. Give --out a folder, such as exports/")
    taken = [n for n in names if (path / n).exists()]
    if taken and not force:
        raise ValueError(f"{', '.join(taken)} already in {path}. Add --force to replace, or pick another --out.")
    return path


def save(path: Path, files: dict[str, str]) -> list[Path]:
    """Write the files, each whole or not at all."""
    path.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in files.items():
        if name not in NAMES:
            raise ValueError(f"not a file fetch writes: {name!r}")
        part = path / f".{name}.part"
        part.write_text(text, encoding="utf-8", newline="")
        os.replace(part, path / name)
        written.append(path / name)
    return written

"""What `openppc-online fetch` and the app's Download panel both run: check --out, download, then write the files."""
import datetime as dt
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from . import files, google, meta, microsoft
from .http import Gate, Send
from .versions import VERSIONS, WARN_DAYS

PLATFORMS = ("google", "microsoft", "meta")
NAMES = {"google": google.NAMES, "microsoft": microsoft.NAMES, "meta": meta.NAMES}
TEMPLATE = {"search_terms.csv": "search-term-waste", "keywords.csv": "keyword-audit", "account.json": "account-read",
            "account_structure.json": "account-structure"}
MAX_DAYS = 365


@dataclass
class Fetched:
    paths: list[Path]
    notes: list[str] = field(default_factory=list)


def sunset_note(platform: str, today: dt.date) -> str | None:
    version = VERSIONS[platform]
    if version.sunset is None or (version.sunset - today).days > WARN_DAYS:
        return None
    return (f"{platform.capitalize()} turns off API {version.name} on {files.long_date(version.sunset)}: update "
            "openppc-online, as a newer release calls a newer version")


def contents(platform: str, account: str, env: Mapping[str, str], *, days: int = files.DAYS,
             conversion: str | None = None, send: Send | None = None, sleep: Callable[[float], object] = time.sleep,
             today: dt.date | None = None) -> tuple[dict[str, str], list[str]]:
    """The platform's files by name, and notes. Nothing is written."""
    if platform not in PLATFORMS:
        raise ValueError(f"fetch reads {', '.join(PLATFORMS)}, not {platform!r}")
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"--days is 1 to {MAX_DAYS}, not {days}")
    if conversion and platform != "meta":
        raise ValueError("--conversion is for fetch meta: Google and Microsoft report conversions as you set them up")
    gate = Gate(platform, send) if send else Gate(platform)
    if platform == "google":
        out, notes = google.download(account, env, gate, days, today)
    elif platform == "microsoft":
        out, notes = microsoft.download(account, env, gate, days, today, sleep)
    else:
        out, notes = meta.download(account, env, gate, days, today, conversion)
    warning = sunset_note(platform, today or dt.date.today())
    return out, [*notes, warning] if warning else notes


def run(platform: str, account: str, out: str | os.PathLike[str], env: Mapping[str, str], *, force: bool = False,
        days: int = files.DAYS, conversion: str | None = None, send: Send | None = None,
        sleep: Callable[[float], object] = time.sleep, today: dt.date | None = None) -> Fetched:
    """--out is checked before connecting; the files are written only once every answer is in."""
    folder = files.folder(out, NAMES.get(platform, []), force)
    found, notes = contents(platform, account, env, days=days, conversion=conversion, send=send, sleep=sleep,
                            today=today)
    return Fetched(files.save(folder, found), notes)

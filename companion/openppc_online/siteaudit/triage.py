"""What happens to the findings after the checks: suppressions with reasons, fingerprints that stay
the same from run to run, the comparison with an earlier run (--baseline), category scores, and
whether the scan was healthy enough to judge the site by."""
import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .checks import CATEGORIES, Finding
from .crawl import PROBE_PREFIX, Crawl
from .packs import Suppression
from .render import NOT_RUN

FINGERPRINT = "fp1"   # the recipe's version: sha256 of the finding id and the item, the item's origin dropped
SECRETS = {"token", "auth", "key", "apikey", "password", "passwd", "pwd", "secret", "session", "sessionid", "sid",
           "sig", "signature", "code", "email", "jwt", "otp"}
URL = re.compile(r"https?://[^\s`'\"<>)|\]]+")
SCORE_HIGH = 20       # points a finding costs its category, by severity; 100 is a clean category
SCORE_MEDIUM = 10
SCORE_LOW = 4
SCORE_INFO = 0
GRADES = ((90, "A"), (80, "B"), (70, "C"), (60, "D"), (0, "F"))
FAILED_SHARE = 0.25   # this share of pages with no answer makes a scan inconclusive
FAILED_MIN_PAGES = 4
BROWSER_CATEGORIES = ("tracking", "accessibility", "performance")  # scored only after a browser pass
# axe rules that find what an SEO rule already found: the SEO finding costs the points, the axe one none
TWINS = {"site-a11y:image-alt": "site-img-alt-missing", "site-a11y:document-title": "site-title-missing",
         "site-a11y:html-has-lang": "site-lang-missing"}


def _secret(name: str) -> bool:
    low = name.lower()
    return low in SECRETS or any(part in SECRETS for part in re.split(r"[^a-z0-9]+", low))


def redact(url: str) -> str:
    """The URL with the values of secret-looking query parameters (token=, session=, email=...) masked."""
    if "?" not in url:
        return url
    head, _, query = url.partition("?")
    query, hash_mark, frag = query.partition("#")
    masked = re.sub(r"([^&=]+)=([^&]*)", lambda m: f"{m[1]}=REDACTED" if _secret(m[1]) and m[2] else m[0], query)
    return f"{head}?{masked}{hash_mark}{frag}"


def redact_text(text: str) -> tuple[str, int]:
    """Every URL in the text redacted, and how many changed."""
    changed = 0

    def one(m: re.Match[str]) -> str:
        nonlocal changed
        out = redact(m[0])
        changed += out != m[0]
        return out
    return URL.sub(one, text), changed


def item_key(item: str) -> str:
    """What identifies an item across runs: a URL's path and query (so staging and live match), else its text."""
    text = item.strip("`")
    if not text.startswith(("http://", "https://")):
        return text
    parts = urlsplit(redact(text))
    if parts.path.startswith(PROBE_PREFIX):  # the made-up missing page: older versions named it at random
        return PROBE_PREFIX
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


def fingerprint(finding_id: str, item: str = "") -> str:
    return hashlib.sha256(f"{FINGERPRINT}\n{finding_id}\n{item_key(item) if item else ''}".encode()).hexdigest()[:16]


# suppressions

@dataclass
class Suppressed:
    rule: Suppression
    items: list[tuple[str, str]] = field(default_factory=list)  # (finding id, item) it hid


def _hides(s: Suppression, f: Finding, item: str) -> bool:
    return (fnmatchcase(f.id, s.rule) or fnmatchcase(f.rule, s.rule)) and (
        not s.match or fnmatchcase(item_key(item), s.match))


def suppress(findings: list[Finding], rules: list[Suppression]) -> tuple[list[Finding], list[Suppressed]]:
    """The findings without what the suppressions hide, and what each one hid (an unused one hid nothing)."""
    used = [Suppressed(s) for s in rules]
    kept: list[Finding] = []
    for f in findings:
        items = []
        for item in f.items:
            hit = next((u for u in used if _hides(u.rule, f, item)), None)
            if hit:
                hit.items.append((f.id, item))
            else:
                items.append(item)
        if items:
            kept.append(f if len(items) == len(f.items) else
                        replace(f, items=items, notes={k: v for k, v in f.notes.items() if k in items}))
    return kept, used


# baselines

@dataclass
class Diff:
    file: str
    new: dict[str, list[str]] = field(default_factory=dict)   # finding id -> its items not in the baseline
    fixed: list[tuple[str, str]] = field(default_factory=list)  # (title, item) in the baseline, gone now
    unchanged: int = 0


def read_baseline(path: str) -> dict[str, tuple[str, str]]:
    """An earlier `openppc-online site --format json` result: instance fingerprint -> (title, item)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        found = {fingerprint(f["id"], item): (str(f.get("title", f["id"])), item)
                 for f in doc["findings"] for item in f["items"]}
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(f"{path} isn't an `openppc-online site --format json` result ({type(e).__name__}: {e})") from None
    return found


def compare(findings: list[Finding], baseline: dict[str, tuple[str, str]], path: str) -> Diff:
    diff = Diff(path)
    now = set()
    for f in findings:
        for item in f.items:
            fp = fingerprint(f.id, item)
            now.add(fp)
            if fp in baseline:
                diff.unchanged += 1
            else:
                diff.new.setdefault(f.id, []).append(item)
    diff.fixed = [entry for fp, entry in baseline.items() if fp not in now]
    return diff


# scan health and scores

def health(c: Crawl) -> str:
    """Why this scan can't be trusted to judge the site, or "" when it can."""
    if c.blocked_by:
        return "bot protection blocked the scan"
    if c.start not in c.pages and c.start in c.robots_blocked:
        return "robots.txt disallows the start page, so nothing on the site was checked"
    if c.robots_failed:
        return "robots.txt couldn't be read, so only the first page was checked"
    start = c.pages.get(c.start)
    if not start or start.status != 200:
        return "the start page didn't load"
    failed = sum(p.status == 0 for p in c.pages.values())
    if len(c.pages) >= FAILED_MIN_PAGES and failed >= FAILED_SHARE * len(c.pages):
        return "too many pages gave no answer"
    return ""


@dataclass
class Score:
    category: str
    score: int | None                      # None: not scored
    grade: str = ""
    lost: list[tuple[Finding, int]] = field(default_factory=list)  # each finding and the points it cost
    why_not: str = ""


def points(level: str) -> int:
    return {"high": SCORE_HIGH, "medium": SCORE_MEDIUM, "low": SCORE_LOW}.get(level, SCORE_INFO)


def grade(score: float) -> str:
    return next(g for line, g in GRADES if score >= line)


def counted_elsewhere(f: Finding, findings: list[Finding]) -> Finding | None:
    """The SEO finding that already costs points for what this axe finding found, if there is one."""
    twin = TWINS.get(f.id)
    return next((g for g in findings if g.id == twin), None) if twin else None


def scores(findings: list[Finding], rendered: bool) -> dict[str, Score]:
    out = {}
    for cat in CATEGORIES:
        if cat == "crawl":
            continue
        if cat in BROWSER_CATEGORIES and not rendered:
            out[cat] = Score(cat, None, why_not=f"needs {NOT_RUN}")
            continue
        lost = [(f, 0 if counted_elsewhere(f, findings) else points(f.level))
                for f in findings if f.about.category == cat]
        value = max(0, 100 - sum(p for _, p in lost))
        out[cat] = Score(cat, value, grade(value), lost)
    return out


def overall(by_category: dict[str, Score]) -> float | None:
    values = [s.score for s in by_category.values() if s.score is not None]
    return sum(values) / len(values) if values else None


def as_data(by_category: dict[str, Score]) -> dict[str, Any]:
    return {cat: {"score": s.score, "grade": s.grade, "not_scored": s.why_not.replace("`", "") or None,
                  "lost": [{"finding": f.id, "points": p} for f, p in s.lost]} for cat, s in by_category.items()}

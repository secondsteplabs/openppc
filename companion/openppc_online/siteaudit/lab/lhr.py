"""One reader for a Lighthouse report (an LHR), from PageSpeed Insights (`--psi`) or a local Lighthouse: the same
JSON. It keeps the score, the metrics, every category and audit, and drops the screenshots unless asked. Audit details
stay in the JSON result only; the markdown shows titles and results. The report's own redaction pass masks
secret-looking URL values in all of it."""
import csv
import io
import re
from dataclasses import dataclass, field
from importlib.resources import files
from typing import TYPE_CHECKING, Any

from .score import band

if TYPE_CHECKING:
    from ..crux import FieldData

KNOWN_MAJOR = 13         # the Lighthouse version this reader, and the parity matrix, were written against
SCREENSHOT_AUDITS = ("final-screenshot", "screenshot-thumbnails")
LEARN_MORE = re.compile(r"\[Learn [^\]]*\]\((https?://[^)\s]+)\)")
PASS_LINE = 0.9          # Lighthouse's report shows an audit scoring this or more as passed


@dataclass
class Metric:
    id: str
    title: str
    acronym: str
    value: float | None           # ms, or unitless for CLS
    score: float | None           # 0-1
    weight: int


@dataclass
class Audit:
    id: str
    title: str
    category: str                 # the first category listing it ("" when none does)
    group: str
    mode: str                     # Lighthouse's scoreDisplayMode
    score: float | None
    docs: str = ""                # the "Learn more" link
    display: str = ""             # Lighthouse's own wording of the value, JSON only
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def result(self) -> str:
        """passed, failed, info (to look at), manual (to check by hand) or n/a, as Lighthouse's report sorts them."""
        if self.mode == "notApplicable":
            return "n/a"
        if self.mode == "manual":
            return "manual"
        if self.mode == "informative" or self.score is None:
            return "info"
        return "passed" if self.score >= PASS_LINE else "failed"


@dataclass
class Category:
    id: str
    title: str
    score: float | None
    audits: list[str] = field(default_factory=list)


@dataclass
class Speed:
    url: str                      # the page asked for
    device: str                   # mobile or desktop
    source: str                   # "PageSpeed Insights" or "Lighthouse"
    final_url: str = ""
    version: str = ""             # Lighthouse's
    method: str = ""              # simulate, devtools or provided
    fetched: str = ""
    score: int | None = None      # the 0-100 performance score
    metrics: list[Metric] = field(default_factory=list)
    categories: dict[str, Category] = field(default_factory=dict)
    audits: dict[str, Audit] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    screenshot: str = ""          # the final screenshot as a data: URL, only when asked
    error: str = ""               # why there is no result
    field_data: list["FieldData"] = field(default_factory=list)  # real visitors, as PSI passes them on: page, site

    @property
    def band(self) -> str:
        return "" if self.score is None else band(self.score)

    @property
    def major(self) -> int:
        head = self.version.split(".")[0]
        return int(head) if head.isdigit() else 0


@dataclass(frozen=True)
class Mapped:
    section: str                  # "ad-click" (speed and the landing page) or "other"
    openppc: str                  # the OpenPPC rule that checks the same thing, or ""


def matrix() -> dict[str, Mapped]:
    """The parity matrix, lighthouse-<KNOWN_MAJOR>.csv: each audit Lighthouse runs, which part of the report it goes
    in, and the OpenPPC rule that checks the same thing. tests/test_lab_lhr.py keeps it complete for the fixtures."""
    text = (files("openppc_online.siteaudit.lab") / f"lighthouse-{KNOWN_MAJOR}.csv").read_text(encoding="utf-8")
    return {row["audit"]: Mapped(row["section"], row["openppc"]) for row in csv.DictReader(io.StringIO(text))}


def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def read(lhr: Any, url: str, source: str, screenshots: bool = False) -> Speed:
    """The LHR as a Speed result. Raises ValueError when it isn't one."""
    if not isinstance(lhr, dict) or not isinstance(lhr.get("audits"), dict) \
            or not isinstance(lhr.get("categories"), dict):
        raise ValueError("not a Lighthouse report")
    settings = lhr.get("configSettings") or {}
    out = Speed(url, str(settings.get("formFactor") or ""), source, str(lhr.get("finalDisplayedUrl") or
                lhr.get("finalUrl") or ""), str(lhr.get("lighthouseVersion") or ""),
                str(settings.get("throttlingMethod") or ""), str(lhr.get("fetchTime") or ""))
    out.warnings = [str(w) for w in lhr.get("runWarnings") or []]
    error = lhr.get("runtimeError")
    if isinstance(error, dict) and error.get("message"):
        out.error = str(error["message"])
    raw: dict[str, dict[str, Any]] = {k: a for k, a in lhr["audits"].items() if isinstance(a, dict)}
    first: dict[str, tuple[str, str]] = {}
    for cid, c in lhr["categories"].items():
        refs = [r for r in c.get("auditRefs") or [] if isinstance(r, dict) and r.get("id") in raw]
        out.categories[cid] = Category(cid, str(c.get("title") or cid), _num(c.get("score")), [r["id"] for r in refs])
        for r in refs:
            first.setdefault(r["id"], (cid, str(r.get("group") or "")))
            if cid == "performance" and r.get("group") == "metrics":
                a = raw[r["id"]]
                out.metrics.append(Metric(r["id"], str(a.get("title") or r["id"]), str(r.get("acronym") or ""),
                                          _num(a.get("numericValue")), _num(a.get("score")), int(r.get("weight") or 0)))
    perf = out.categories.get("performance")
    if perf and perf.score is not None:
        out.score = round(perf.score * 100)
    for aid, a in raw.items():
        details: dict[str, Any] = a["details"] if isinstance(a.get("details"), dict) else {}
        if aid in SCREENSHOT_AUDITS:
            if screenshots and aid == "final-screenshot" and str(details.get("data", "")).startswith("data:image/"):
                out.screenshot = details["data"]
            details = {}
        docs = LEARN_MORE.search(str(a.get("description") or ""))
        cid, group = first.get(aid, ("", ""))
        out.audits[aid] = Audit(aid, str(a.get("title") or aid), cid, group, str(a.get("scoreDisplayMode") or ""),
                                _num(a.get("score")), docs[1] if docs else "", str(a.get("displayValue") or ""),
                                details)
    return out


def as_data(s: Speed) -> dict[str, Any]:
    """One result for --format json: audit details included, screenshots only when they were asked for."""
    return {"url": s.url, "final_url": s.final_url, "device": s.device, "source": s.source, "method": s.method,
            "lighthouse": s.version, "fetched": s.fetched, "score": s.score, "band": s.band or None,
            "error": s.error or None, "warnings": s.warnings,
            "metrics": [{"id": m.id, "acronym": m.acronym, "value": m.value, "score": m.score, "weight": m.weight}
                        for m in s.metrics],
            "categories": {c.id: {"title": c.title, "score": c.score} for c in s.categories.values()},
            "audits": [{"id": a.id, "title": a.title, "category": a.category, "group": a.group, "mode": a.mode,
                        "score": a.score, "result": a.result, "docs": a.docs, "display": a.display,
                        "details": a.details} for a in s.audits.values()],
            "screenshot": s.screenshot or None}

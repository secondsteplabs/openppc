"""The calibration gate (SITE_AUDIT_PARITY_PLAN.md, section 8): per-metric medians of OpenPPC's lab loads against
Lighthouse's (devtools throttling, same browser, host and proxy), and the representative load's score. It passes with
at most one miss across every fixture and metric. TTI is compared but not gated."""
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from openppc_online.siteaudit.lab.metrics import representative
from openppc_online.siteaudit.lab.score import band

# metric: (share of Lighthouse's median, ms), whichever allows more
TOLERANCE = {"fcp": (0.10, 150.0), "lcp": (0.10, 150.0), "si": (0.15, 250.0), "tbt": (0.25, 50.0),
             "ttfb": (0.05, 20.0), "tti": (0.15, 0.0)}
CLS_TOLERANCE = 0.01
UNGATED = ("tti",)
SCORE_TOLERANCE = 5
BAND_MARGIN = 2             # scores this near a band line may land in the other band
BAND_LINES = (50, 90)
MISSES_ALLOWED = 1
ORDER = ("fcp", "lcp", "si", "tbt", "cls", "ttfb", "tti")

Runs = Sequence[dict[str, float | None]]


@dataclass
class Row:
    fixture: str
    device: str
    metric: str             # a lab.metrics name, or "score"
    ours: float | None
    reference: float | None
    allowed: float | None   # the largest difference that passes
    ok: bool
    gated: bool = True

    @property
    def difference(self) -> float | None:
        return None if self.ours is None or self.reference is None else self.ours - self.reference


def median(runs: Runs, metric: str) -> float | None:
    values = [v for r in runs if (v := r.get(metric)) is not None]
    return float(statistics.median(values)) if values else None


def allowance(metric: str, reference: float) -> float:
    if metric == "cls":
        return CLS_TOLERANCE
    share, ms = TOLERANCE[metric]
    return max(share * abs(reference), ms)


def _row(fixture: str, device: str, metric: str, ours: float | None, reference: float | None) -> Row:
    gated = metric not in UNGATED
    if ours is None or reference is None:
        return Row(fixture, device, metric, ours, reference, None, ours is None and reference is None, gated)
    allowed = allowance(metric, reference)
    return Row(fixture, device, metric, ours, reference, allowed, abs(ours - reference) <= allowed, gated)


def score_ok(ours: int, reference: int) -> bool:
    if abs(ours - reference) > SCORE_TOLERANCE:
        return False
    near_line = any(abs(s - line) <= BAND_MARGIN for s in (ours, reference) for line in BAND_LINES)
    return near_line or band(ours) == band(reference)


def compare(fixture: str, device: str, ours: Runs, reference: Runs,
            ours_scores: Sequence[int | None], reference_scores: Sequence[int | None]) -> list[Row]:
    """One fixture's rows: each metric's medians, then the representative load's score from each side (the scores
    listed in run order)."""
    rows = [_row(fixture, device, m, median(ours, m), median(reference, m)) for m in ORDER]
    a = _score_of(ours, ours_scores)
    b = _score_of(reference, reference_scores)
    if a is None or b is None:
        rows.append(Row(fixture, device, "score", a, b, None, a is None and b is None))
    else:
        rows.append(Row(fixture, device, "score", a, b, SCORE_TOLERANCE, score_ok(int(a), int(b))))
    return rows


def _score_of(runs: Runs, scores: Sequence[int | None]) -> float | None:
    i = representative(runs)
    return None if i is None or i >= len(scores) or scores[i] is None else float(scores[i])  # type: ignore[arg-type]


def misses(rows: Sequence[Row]) -> list[Row]:
    return [r for r in rows if r.gated and not r.ok]


def passed(rows: Sequence[Row]) -> bool:
    return len(misses(rows)) <= MISSES_ALLOWED


def cell(metric: str, v: float | None) -> str:
    if v is None:
        return "-"
    return f"{v:.3f}" if metric == "cls" else f"{v:.0f}"


def tag_table(fixtures: dict[str, dict[str, Runs]]) -> str:
    """The tag pages, kept out of the gate: each metric's median from OpenPPC's lab with the hits answered (as it
    measures), with them sent, and from Lighthouse (which sends them), so the cost of answering them is published."""
    out = ["| Fixture | Metric | OpenPPC, hits answered | OpenPPC, hits sent | Lighthouse |", "|---|---|---|---|---|"]
    for name, sides in fixtures.items():
        for m in ORDER:
            out.append(f"| {name} | {m} | {cell(m, median(sides['answered'], m))} | "
                       f"{cell(m, median(sides['sent'], m))} | {cell(m, median(sides['reference'], m))} |")
    return "\n".join(out)


def table(rows: Sequence[Row]) -> str:
    """The rows as a Markdown table, misses marked."""
    out = ["| Fixture | Device | Metric | OpenPPC | Lighthouse | Difference | Allowed | Result |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        result = "pass" if r.ok else ("miss" if r.gated else "differs (not gated)")
        out.append(f"| {r.fixture} | {r.device} | {r.metric} | {cell(r.metric, r.ours)} | "
                   f"{cell(r.metric, r.reference)} | {cell(r.metric, r.difference)} | "
                   f"{cell(r.metric, r.allowed)} | {result} |")
    n = len(misses(rows))
    out.append("")
    out.append(f"Gate: {'passed' if passed(rows) else 'failed'}, {n} miss{'es' if n != 1 else ''} "
               f"({MISSES_ALLOWED} allowed).")
    return "\n".join(out)

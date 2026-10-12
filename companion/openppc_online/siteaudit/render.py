"""What a browser pass observes, and the lab profile it measures on. The checks and the report read these; the
browser that fills them in is not in this version, so a scan has no Rendered and its browser checks say so."""
import statistics
from dataclasses import dataclass, field
from typing import Any

RENDER_PAGES = 5             # pages rendered: the home page, then one per top-level section
VITALS_RUNS = 3              # the median of this many loads is reported
VITALS_PAGES = 1             # pages measured, from the first rendered (the home page) on
# Lighthouse's mobile profile: a mid-range phone on a slow 4G connection
VIEWPORT = {"width": 412, "height": 823}
CPU_SLOWDOWN = 4
RTT_MS = 150
DOWN_KBPS = 1638.4
UP_KBPS = 750
PROFILE = (f"lab, simulated phone ({VIEWPORT['width']}x{VIEWPORT['height']}), "
           f"{CPU_SLOWDOWN}x slower CPU, {RTT_MS} ms round trips, {DOWN_KBPS / 1024:.1f} Mbps down")
AXE_TAGS = ("wcag2a", "wcag2aa", "wcag21a", "wcag21aa")
AXE_VERSION = "4.10.3"
METRICS = ("lcp", "cls", "tbt", "fcp", "ttfb")
NOT_RUN = "a browser, which this version doesn't run"


@dataclass
class Observation:
    url: str
    error: str = ""
    before: list[str] = field(default_factory=list)   # requests before any consent
    after: list[str] = field(default_factory=list)    # requests after accepting, and a reload
    consent: str = ""          # the consent platform recognised, or ""
    accepted: bool = False     # its accept button was clicked
    selector: str = ""         # the button clicked
    tcf: bool = False          # the IAB TCF API (__tcfapi) is on the page
    consent_mode: list[str] = field(default_factory=list)  # gtag('consent', ...) commands seen
    axe: list[dict[str, Any]] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # every link in the rendered page, absolute
    screenshot: str = ""       # where the page was saved as first loaded
    events: dict[str, list[str]] = field(default_factory=dict)  # tag: the events its hits sent
    datalayer: list[str] = field(default_factory=list)          # events pushed to the dataLayer


@dataclass
class Vitals:
    url: str
    runs: list[dict[str, float | None]] = field(default_factory=list)
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)  # from the first run: the LCP element, blocking files

    @property
    def median(self) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for k in METRICS:
            values = [v for r in self.runs if (v := r.get(k)) is not None]
            out[k] = float(statistics.median(values)) if values else None
        return out


@dataclass
class Rendered:
    pages: list[Observation] = field(default_factory=list)
    vitals: list[Vitals] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)  # hosts the browser was stopped from reaching

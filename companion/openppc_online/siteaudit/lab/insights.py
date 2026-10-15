"""Lighthouse's insights on a page (its `*-insight` audits): what slows the load and what fixing it would save, worked
out as Lighthouse 13.5 works them out, by the DevTools trace engine from one unthrottled load, with the slow phone or
desktop simulated (Lantern).

The engine is vendor/trace-engine.js: @paulirish/trace_engine ENGINE_VERSION, the version Lighthouse 13.5 pins,
bundled with its licences by companion/calibration/build.mjs (THIRD_PARTY_LICENSES.md). It runs in a blank page of the
same browser, which has no proxy of its own, so anything it fetched would go to net.Sink; it gets the trace and gives
back each insight's result. Savings are rounded as Lighthouse rounds them. On 17 local pages its results match
Lighthouse's with simulated throttling (tests/calibration/insights.py).
"""
import json
import re
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files
from typing import Any

from .metrics import Event
from .throttle import DESKTOP, MOBILE, MOBILE_CPU, MOBILE_DOWN_KBPS, MOBILE_LATENCY_MS, MOBILE_UP_KBPS

ENGINE_VERSION = "0.0.65"
# Lantern's throttling, as Lighthouse 13.5 passes it to the engine (lantern/simulation/Constants.ts): the mobile
# profile's round trip and throughput are the simulator's inputs, throttle.py's the applied version of them
SIMULATED = {
    "mobile": {"rttMs": 150, "throughputKbps": 1.6 * 1024, "requestLatencyMs": MOBILE_LATENCY_MS,
               "downloadThroughputKbps": MOBILE_DOWN_KBPS, "uploadThroughputKbps": MOBILE_UP_KBPS,
               "cpuSlowdownMultiplier": MOBILE_CPU},
    "desktop": {"rttMs": 40, "throughputKbps": 10 * 1024, "requestLatencyMs": 0, "downloadThroughputKbps": 0,
                "uploadThroughputKbps": 0, "cpuSlowdownMultiplier": 1},
}
DPR = {"mobile": MOBILE.scale, "desktop": DESKTOP.scale}  # sizes images as displayed
PRECISION = {"FCP": 50, "LCP": 50, "INP": 50, "TBT": 50, "CLS": 0.001}  # Lighthouse's audit.js rounds savings so
RUN_JS = """async ([text, settings, dpr, debug]) => globalThis.openppcTraceEngine.insights(
  JSON.parse(text), {throttlingMethod: 'simulate', throttling: settings}, dpr, debug)"""


@dataclass
class Insight:
    id: str                    # Lighthouse's audit id: lcp-discovery-insight
    title: str                 # the engine's English title, Lighthouse's audit title
    state: str                 # fail, pass or informative
    savings: dict[str, float] = field(default_factory=dict)  # per metric (FCP, LCP, CLS...), ms but CLS
    bytes: int | None = None   # bytes it would save
    failed: list[str] = field(default_factory=list)  # the checks it failed, in the engine's words
    items: list[str] = field(default_factory=list)   # what it blames: files, or companies for third parties


@cache
def engine_source() -> str:
    return (files("openppc_online.siteaudit") / "vendor" / "trace-engine.js").read_text(encoding="utf-8")


def audit_id(name: str) -> str:
    """The engine's insight name as Lighthouse's audit id: LCPDiscovery is lcp-discovery-insight."""
    words = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "-", name.replace("JavaScript", "Javascript"))
    return words.lower() + "-insight"


def quantized(savings: dict[str, Any]) -> dict[str, float]:
    """Savings as Lighthouse reports them: none below zero, rounded to PRECISION, and left out when that's nothing."""
    out = {}
    for metric, value in savings.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        step = PRECISION.get(metric)
        rounded = round(round(max(value, 0) / step) * step, 3) if step else max(value, 0)
        if rounded:
            out[metric] = rounded
    return out


def evaluate(browser: Any, events: list[Event], device: str, debug: bool = False) -> dict[str, Any]:
    """The engine's own answer for one trace: {"url", "insights": {name: result}} or {"error"}."""
    page = browser.new_page()
    try:
        # Runtime.evaluate, as for axe-core: the bundle is one script, run as it is
        page.context.new_cdp_session(page).send("Runtime.evaluate", {"expression": engine_source()})
        return dict(page.evaluate(RUN_JS, [json.dumps(events), SIMULATED[device], DPR[device], debug]))
    finally:
        page.context.close()


def run(browser: Any, events: list[Event], device: str) -> list[Insight]:
    """Every insight on the load traced in `events` (lab.capture's raw events of an unthrottled load), failing ones
    first. Raises ValueError when the engine finds no page load in it."""
    answer = evaluate(browser, events, device)
    if answer.get("error"):
        raise ValueError(str(answer["error"]))
    out = []
    for name, r in (answer.get("insights") or {}).items():
        if not isinstance(r, dict) or r.get("error"):
            continue
        wasted = r.get("wastedBytes")
        out.append(Insight(audit_id(name), str(r.get("title") or name), str(r.get("state") or ""),
                           quantized(r.get("metricSavings") or {}),
                           round(wasted) if isinstance(wasted, (int, float)) and wasted > 0 else None,
                           [str(x) for x in r.get("failed") or []], [str(x) for x in r.get("items") or []]))
    return sorted(out, key=lambda i: i.state != "fail")

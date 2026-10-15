"""The trace-engine spike (SITE_AUDIT_PARITY_PLAN.md, R3 item 5), from companion/tests:

    python -m calibration.insights --device mobile --lighthouse ../calibration --out insights.json

Per fixture: one unthrottled OpenPPC load, traced, with the DevTools trace engine (build/trace-engine.js, from
`npm run build` in companion/calibration) run on its trace in a blank page of the same browser, simulating Lighthouse's
throttling as Lighthouse does; and one Lighthouse run with simulated throttling. It passes when the failing insights
match on every fixture with one, and each saving both report is within SAVINGS_SHARE of Lighthouse's, on at least
PASS_FIXTURES fixtures. Offline: only the fixtures' names resolve.
"""
import argparse
import dataclasses
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from openppc_online.siteaudit import render
from openppc_online.siteaudit.lab import lighthouse
from openppc_online.siteaudit.lab.capture import capture
from openppc_online.siteaudit.lab.throttle import DESKTOP, MOBILE
from openppc_online.siteaudit.net import Guard, GuardProxy, Sink

from .fixtures import Server, url
from .harness import resolve, say

BUNDLE = Path(__file__).resolve().parents[2] / "calibration" / "build" / "trace-engine.js"
SAVINGS_SHARE = 0.10
PASS_FIXTURES = 5
# Lantern's throttling settings, as Lighthouse passes them (lantern/simulation/Constants.js)
SIMULATED = {
    "mobile": {"rttMs": 150, "throughputKbps": 1.6 * 1024, "requestLatencyMs": 150 * 3.75,
               "downloadThroughputKbps": 1.6 * 1024 * 0.9, "uploadThroughputKbps": 750 * 0.9,
               "cpuSlowdownMultiplier": 4},
    "desktop": {"rttMs": 40, "throughputKbps": 10 * 1024, "requestLatencyMs": 0, "downloadThroughputKbps": 0,
                "uploadThroughputKbps": 0, "cpuSlowdownMultiplier": 1},
}
PRECISION = {"FCP": 50, "LCP": 50, "INP": 50, "TBT": 50, "CLS": 0.001}  # Lighthouse's audit.js rounds savings so
RUN_JS = """async ([text, settings, dpr, debug]) => globalThis.openppcTraceEngine.insights(
  JSON.parse(text), {throttlingMethod: 'simulate', throttling: settings}, dpr, debug)"""


def audit_id(name: str) -> str:
    """The trace engine's insight name as Lighthouse's audit id: LCPDiscovery is lcp-discovery-insight."""
    words = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "-", name.replace("JavaScript", "Javascript"))
    return words.lower() + "-insight"


def quantized(savings: dict[str, float]) -> dict[str, float]:
    """Savings as Lighthouse reports them: rounded to PRECISION, and none when that leaves nothing."""
    out = {}
    for metric, value in savings.items():
        step = PRECISION.get(metric)
        value = max(value, 0)
        value = round(round(value / step) * step, 3) if step else value
        if value:
            out[metric] = value
    return out


def engine(browser: Any, bundle: str, events: list[dict[str, Any]], device: str, debug: bool = False) -> dict[str, Any]:
    profile = DESKTOP if device == "desktop" else MOBILE
    page = browser.new_page()
    try:
        page.add_script_tag(content=bundle)
        started = time.monotonic()
        result = page.evaluate(RUN_JS, [json.dumps(events), SIMULATED[device], profile.scale, debug])
        result["seconds"] = round(time.monotonic() - started, 2)
        return dict(result)
    finally:
        page.context.close()


def ours(browser: Any, bundle: str, target: str, device: str, proxy: str, debug: bool = False) -> dict[str, Any]:
    base = DESKTOP if device == "desktop" else MOBILE
    fast = dataclasses.replace(base, cpu=1, latency_ms=0, down_kbps=0, up_kbps=0)
    raw: list[dict[str, Any]] = []
    try:
        capture(browser, target, fast, proxy, render.BLOCK_HITS, raw)
        result = engine(browser, bundle, raw, device, debug)
    except PlaywrightError as e:
        return {"error": str(e).splitlines()[0]}
    result["trace_mb"] = round(len(json.dumps(raw)) / 1e6, 2)
    insights = result.get("insights") or {}
    for v in insights.values():
        v["metricSavings"] = quantized(v.get("metricSavings") or {})
    result["insights"] = {audit_id(name): v for name, v in insights.items()}
    return result


def reference(browser: Any, address: str, lh: Path, target: str, device: str, proxy: str,
              debug: bool = False) -> dict[str, Any]:
    try:
        lhr = lighthouse.run(browser, address, lh, target, device, proxy, "simulate")
    except lighthouse.Failed as e:
        return {"error": str(e)}
    out: dict[str, Any] = {}
    for key, audit in (lhr.get("audits") or {}).items():
        if not key.endswith("-insight"):
            continue
        score, mode = audit.get("score"), audit.get("scoreDisplayMode")
        state = ("error" if audit.get("errorMessage") else "not applicable" if mode == "notApplicable"
                 else "informative" if score is None else "pass" if score == 1 else "fail")
        extra = (audit.get("details") or {}).get("debugData") or {}
        out[key] = {"state": state, "metricSavings": {k: v for k, v in (audit.get("metricSavings") or {}).items()
                                                       if isinstance(v, (int, float)) and v},
                    "wastedBytes": extra.get("wastedBytes")}
        if debug and state == "fail":
            out[key]["details"] = audit.get("details")
    return {"insights": out}


def compare(mine: dict[str, Any], theirs: dict[str, Any]) -> dict[str, Any]:
    """Failing insights on each side, and each saving both report, with whether it is within SAVINGS_SHARE."""
    a, b = mine.get("insights") or {}, theirs.get("insights") or {}
    failing = (sorted(k for k, v in a.items() if v.get("state") == "fail"),
               sorted(k for k, v in b.items() if v.get("state") == "fail"))
    savings = []
    for key in sorted(set(failing[0]) & set(failing[1])):
        pairs = [(m, a[key]["metricSavings"].get(m), v) for m, v in b[key]["metricSavings"].items()]
        if b[key].get("wastedBytes"):
            pairs.append(("bytes", a[key].get("wastedBytes"), b[key]["wastedBytes"]))
        for metric, x, y in pairs:
            ok = isinstance(x, (int, float)) and abs(x - y) <= SAVINGS_SHARE * abs(y)
            savings.append({"insight": key, "metric": metric, "ours": x, "lighthouse": y, "ok": ok})
    same = failing[0] == failing[1]
    return {"failing": failing, "same_failing": same, "savings": savings,
            "passed": bool(not mine.get("error") and not theirs.get("error") and same
                           and all(s["ok"] for s in savings) and failing[1])}


def summary(out: dict[str, Any]) -> str:
    text = ["| Fixture | Failing (trace engine) | Failing (Lighthouse simulate) | Savings, ours / Lighthouse | Passed |",
            "|---|---|---|---|---|"]
    for name, f in out["fixtures"].items():
        c = f["compare"]
        short = [", ".join(k.removesuffix("-insight") for k in side) or "none" for side in c["failing"]]
        saved = "; ".join(f"{s['insight'].removesuffix('-insight')} {s['metric']} {s['ours']} / {s['lighthouse']}"
                          f"{'' if s['ok'] else ' (off)'}" for s in c["savings"]) or "none"
        text.append(f"| {name} | {short[0]} | {short[1]} | {saved} | {'yes' if c['passed'] else 'no'} |")
    timing = [f["ours"].get("seconds") for f in out["fixtures"].values() if f["ours"].get("seconds") is not None]
    text.append("")
    text.append(f"{out['passed_fixtures']} fixtures passed (needs {PASS_FIXTURES}); the engine took up to "
                f"{max(timing, default=0)} s a trace; bundle {out['bundle_kb']} KB; {out.get('chromium', '')}.")
    return "\n".join(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m calibration.insights")
    ap.add_argument("--device", choices=("mobile", "desktop"), default="mobile")
    ap.add_argument("--lighthouse", default="", help="the folder Lighthouse is installed in")
    ap.add_argument("--bundle", default=str(BUNDLE))
    ap.add_argument("--from", dest="saved", default="", help="print a saved run's summary instead of running")
    ap.add_argument("--only", default="", help="fixtures to run, comma-separated (all by default)")
    ap.add_argument("--debug", action="store_true", help="keep each failing insight's model and Lighthouse's details")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    if a.saved:
        saved = json.loads(Path(a.saved).read_text(encoding="utf-8"))
        print(summary(saved))
        return 0 if saved["passed"] else 1
    if not a.lighthouse:
        ap.error("--lighthouse is needed to run")
    lh = lighthouse.folder(a.lighthouse)
    bundle = Path(a.bundle).read_text(encoding="utf-8")
    guard = Guard(allow_private=True, resolve=resolve)
    out: dict[str, Any] = {"device": a.device, "bundle_kb": round(len(bundle.encode()) / 1024),
                           "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "fixtures": {}}
    with Server() as server, GuardProxy(guard) as proxy, Sink() as sink, sync_playwright() as pw:
        browser = render._launch(pw, sink.url, devtools=True)
        try:
            address = lighthouse.attach(browser, guard)
            out["chromium"] = browser.version
            for name in [n for n in server.pages if not a.only or n in a.only.split(",")]:
                target = url(name, server.port)
                say(f"{name} ({a.device})")
                mine = ours(browser, bundle, target, a.device, proxy.url, a.debug)
                theirs = reference(browser, address, lh, target, a.device, proxy.url, a.debug)
                out["fixtures"][name] = {"ours": mine, "reference": theirs, "compare": compare(mine, theirs)}
        finally:
            browser.close()
        out["browser_calls"] = sink.asked
    out["refused"] = sorted(set(guard.refused))
    out["passed_fixtures"] = sum(f["compare"]["passed"] for f in out["fixtures"].values())
    out["passed"] = out["passed_fixtures"] >= PASS_FIXTURES
    print(summary(out))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

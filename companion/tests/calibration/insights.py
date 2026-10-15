"""The trace-engine spike (SITE_AUDIT_PARITY_PLAN.md, R3 item 5), from companion/tests:

    python -m calibration.insights --device mobile --lighthouse ../calibration --out insights.json

Per fixture: one unthrottled OpenPPC load, traced, with the vendored DevTools trace engine run on its trace as
openppc_online's lab.insights runs it; and one Lighthouse run with simulated throttling. It passes when the failing insights
match on every fixture with one, and each saving both report is within SAVINGS_SHARE of Lighthouse's, on at least
PASS_FIXTURES fixtures. Offline: only the fixtures' names resolve.
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from openppc_online.siteaudit import render
from openppc_online.siteaudit.lab import insights, lighthouse
from openppc_online.siteaudit.lab.capture import capture
from openppc_online.siteaudit.lab.throttle import DESKTOP, MOBILE
from openppc_online.siteaudit.net import Guard, GuardProxy, Sink

from .fixtures import Server, url
from .harness import resolve, say

SAVINGS_SHARE = 0.10
PASS_FIXTURES = 5


def ours(browser: Any, target: str, device: str, proxy: str, debug: bool = False) -> dict[str, Any]:
    profile = DESKTOP if device == "desktop" else MOBILE
    raw: list[dict[str, Any]] = []
    try:
        capture(browser, target, profile.unthrottled(), proxy, render.BLOCK_HITS, raw)
        started = time.monotonic()
        result = insights.evaluate(browser, raw, device, debug)
    except PlaywrightError as e:
        return {"error": str(e).splitlines()[0]}
    result["seconds"] = round(time.monotonic() - started, 2)
    result["trace_mb"] = round(len(json.dumps(raw)) / 1e6, 2)
    found = result.get("insights") or {}
    for v in found.values():
        v["metricSavings"] = insights.quantized(v.get("metricSavings") or {})
    result["insights"] = {insights.audit_id(name): v for name, v in found.items()}
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
    guard = Guard(allow_private=True, resolve=resolve)
    out: dict[str, Any] = {"device": a.device, "bundle_kb": round(len(insights.engine_source().encode()) / 1024),
                           "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "fixtures": {}}
    with Server() as server, GuardProxy(guard) as proxy, Sink() as sink, sync_playwright() as pw:
        browser = render._launch(pw, sink.url, devtools=True)
        try:
            address = lighthouse.attach(browser, guard)
            out["chromium"] = browser.version
            for name in [n for n in server.pages if not a.only or n in a.only.split(",")]:
                target = url(name, server.on)
                say(f"{name} ({a.device})")
                mine = ours(browser, target, a.device, proxy.url, a.debug)
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

"""Runs the calibration (SITE_AUDIT_PARITY_PLAN.md, section 8), from companion/tests:

    python -m calibration.harness --device mobile --runs 9 --lighthouse ../calibration --out mobile.json

Each fixture is loaded `runs` times by OpenPPC's lab and by Lighthouse (devtools throttling), alternating, in the
same browser through the same guard proxy, over HTTPS with HTTP/2 (an HTTP/1.1-only host beside them; --plain for
plain HTTP); the gate (gate.py) compares the medians. The tag pages stay out of the gate, since Lighthouse's loads
send their hits and OpenPPC's answer them: there OpenPPC's lab also loads them with the hits sent, and the three are
published side by side. --proxy-gate also times one fixture with and without the guard's proxy, and --simulate
records one Lighthouse run with simulated throttling per fixture (PSI's method, never gated). Needs Node (Lighthouse,
and the HTTPS front) and cryptography. Offline: only the fixtures' names resolve.
"""
import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from openppc_online.siteaudit import render
from openppc_online.siteaudit.lab import lighthouse, metrics
from openppc_online.siteaudit.lab.capture import benchmark, capture
from openppc_online.siteaudit.lab.score import performance
from openppc_online.siteaudit.lab.throttle import DESKTOP, MOBILE, Profile
from openppc_online.siteaudit.net import Guard, GuardProxy, Sink

from . import gate
from .bypass import launch_unguarded, trusting
from .fixtures import HOST, OTHER_HOSTS, TAG_FIXTURES, Server, url

LOCAL = {HOST, *OTHER_HOSTS}
PROXY_FIXTURE = "hero"
PROXY_RUNS = 9
PROXY_LCP_SHARE = 0.03
PROXY_TTFB_MS = 20.0


def resolve(host: str, port: int) -> list[str]:
    if host in LOCAL:
        return ["127.0.0.1"]
    raise OSError("not a fixture's host (the calibration runs offline)")


def say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def lab_score(m: dict[str, float | None], device: str) -> int | None:
    values = {name: m.get(key) for key, name in render.SCORED.items()}
    if any(v is None for v in values.values()):
        return None
    return performance({k: float(v) for k, v in values.items() if v is not None}, device)


def ours(browser: Any, target: str, profile: Profile, proxy: str, answer: bool = render.BLOCK_HITS) -> dict[str, Any]:
    try:
        run = capture(browser, target, profile, proxy, answer)
        m = metrics.measure(run.events, run.trace_end, run.frames)
    except (PlaywrightError, metrics.NoNavigation) as e:
        return {"metrics": {}, "score": None, "error": str(e).splitlines()[0]}
    return {"metrics": m, "score": lab_score(m, profile.device), "capped": run.capped}


def reference(browser: Any, address: str, lh: Path, target: str, device: str, proxy: str,
              method: str = "devtools") -> dict[str, Any]:
    try:
        lhr = lighthouse.run(browser, address, lh, target, device, proxy, method)
    except lighthouse.Failed as e:
        return {"metrics": {}, "score": None, "error": str(e)}
    perf = (lhr.get("categories") or {}).get("performance") or {}
    score = perf.get("score")
    error = (lhr.get("runtimeError") or {}).get("message", "")
    return {"metrics": lighthouse.measured(lhr), "score": round(score * 100) if isinstance(score, (int, float))
            else None, "error": error, "version": lhr.get("lighthouseVersion", ""),
            "benchmark": (lhr.get("environment") or {}).get("benchmarkIndex")}


def proxy_gate(browser: Any, unguarded: Any, target: str, profile: Profile, proxy: str) -> dict[str, Any]:
    """The guard's cost: LCP within 3% and TTFB within 20 ms, medians of alternating loads."""
    guarded: list[dict[str, float | None]] = []
    direct: list[dict[str, float | None]] = []
    for i in range(PROXY_RUNS):
        say(f"proxy gate, load {i + 1} of {PROXY_RUNS}")
        pair = [(guarded, browser, proxy), (direct, unguarded, "")]
        for into, b, p in pair if i % 2 == 0 else reversed(pair):
            into.append(ours(b, target, profile, p)["metrics"])
    lcp = (gate.median(guarded, "lcp"), gate.median(direct, "lcp"))
    ttfb = (gate.median(guarded, "ttfb"), gate.median(direct, "ttfb"))
    lcp_ok = None not in lcp and abs(lcp[0] - lcp[1]) <= PROXY_LCP_SHARE * lcp[1]  # type: ignore[operator]
    ttfb_ok = None not in ttfb and abs(ttfb[0] - ttfb[1]) <= PROXY_TTFB_MS  # type: ignore[operator]
    return {"fixture": PROXY_FIXTURE, "lcp": lcp, "ttfb": ttfb, "passed": bool(lcp_ok and ttfb_ok),
            "guarded": guarded, "direct": direct}


def summary(out: dict[str, Any]) -> str:
    """The gate's table, each fixture's scores (the representative load's on each side, and Lighthouse's simulated
    throttling, PSI's method, which isn't gated), and the proxy gate."""
    rows = [gate.Row(**r) for r in out["rows"]]
    text = [gate.table(rows), "", "| Fixture | OpenPPC lab | Lighthouse (devtools) | Lighthouse (simulate) |",
            "|---|---|---|---|"]
    scores = {r.fixture: r for r in rows if r.metric == "score"}
    tagged = {name: f for name, f in out["fixtures"].items() if "sent" in f}
    for name, f in out["fixtures"].items():
        if name in tagged:
            continue
        s = scores.get(name)
        simulated = (f.get("simulate") or {}).get("score")
        text.append(f"| {name} | {gate.cell('score', s.ours if s else None)} | "
                    f"{gate.cell('score', s.reference if s else None)} | {gate.cell('score', simulated)} |")
    if tagged:
        text += ["", "Tag pages, not gated (Lighthouse's loads send the hits; OpenPPC's lab answers them):", "",
                 gate.tag_table({name: {"answered": [r["metrics"] for r in f["ours"]],
                                        "sent": [r["metrics"] for r in f["sent"]],
                                        "reference": [r["metrics"] for r in f["reference"]]}
                                 for name, f in tagged.items()})]
    text.append("")
    text.append(f"Benchmark index {out.get('benchmark')}, {out.get('chromium', '')}, {out['runs']} loads a side, "
                f"{out.get('transport', 'plain HTTP')}.")
    if "proxy" in out:
        p = out["proxy"]
        text.append(f"\nProxy gate ({p['fixture']}): LCP {p['lcp'][0]} with the guard, {p['lcp'][1]} without; "
                    f"TTFB {p['ttfb'][0]} and {p['ttfb'][1]}: {'passed' if p['passed'] else 'failed'}.")
    return "\n".join(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m calibration.harness")
    ap.add_argument("--device", choices=("mobile", "desktop"), default="mobile")
    ap.add_argument("--runs", type=int, default=9)
    ap.add_argument("--lighthouse", default="", help="the folder Lighthouse is installed in")
    ap.add_argument("--from", dest="saved", default="", help="print a saved run's summary instead of running")
    ap.add_argument("--only", default="", help="fixtures to run, comma-separated (all by default)")
    ap.add_argument("--proxy-gate", action="store_true")
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument("--plain", action="store_true", help="plain HTTP instead of HTTPS with HTTP/2")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    if a.saved:
        saved = json.loads(Path(a.saved).read_text(encoding="utf-8"))
        print(summary(saved))
        return 0 if saved["passed"] else 1
    if not a.lighthouse:
        ap.error("--lighthouse is needed to run")
    lh = lighthouse.folder(a.lighthouse)
    profile = DESKTOP if a.device == "desktop" else MOBILE
    guard = Guard(allow_private=True, resolve=resolve)
    rows: list[gate.Row] = []
    out: dict[str, Any] = {"device": a.device, "runs": a.runs, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           "transport": "plain HTTP" if a.plain else "HTTPS, HTTP/2 and one HTTP/1.1 host",
                           "fixtures": {}}
    with Server(tls=not a.plain) as server, GuardProxy(guard) as proxy, Sink() as sink, sync_playwright() as pw:
        browser = render._launch(trusting(pw, server.tls), sink.url, devtools=True)
        try:
            address = lighthouse.attach(browser, guard)
            out["chromium"] = browser.version
            out["benchmark"] = benchmark(browser)
            names = [n for n in server.pages if not a.only or n in a.only.split(",")]
            for name in names:
                target = url(name, server.on)
                mine: list[dict[str, Any]] = []
                theirs: list[dict[str, Any]] = []
                sent: list[dict[str, Any]] = []
                for i in range(a.runs):
                    say(f"{name} ({a.device}), load {i + 1} of {a.runs}")
                    sides = [(mine, lambda: ours(browser, target, profile, proxy.url)),
                             (theirs, lambda: reference(browser, address, lh, target, a.device, proxy.url))]
                    if name in TAG_FIXTURES:
                        sides.append((sent, lambda: ours(browser, target, profile, proxy.url, answer=False)))
                    for into, load in sides if i % 2 == 0 else reversed(sides):
                        into.append(load())
                result: dict[str, Any] = {"url": target, "ours": mine, "reference": theirs}
                if a.simulate:
                    say(f"{name} ({a.device}), simulated")
                    result["simulate"] = reference(browser, address, lh, target, a.device, proxy.url, "simulate")
                out["fixtures"][name] = result
                if name in TAG_FIXTURES:
                    result["sent"] = sent
                    continue
                rows += gate.compare(name, a.device, [r["metrics"] for r in mine], [r["metrics"] for r in theirs],
                                     [r["score"] for r in mine], [r["score"] for r in theirs])
            if a.proxy_gate:
                unguarded = launch_unguarded(pw, server.tls)
                try:
                    out["proxy"] = proxy_gate(browser, unguarded, url(PROXY_FIXTURE, server.on), profile,
                                              proxy.url)
                finally:
                    unguarded.close()
        finally:
            browser.close()
        out["browser_calls"] = sink.asked
    out["refused"] = sorted(set(guard.refused))
    out["rows"] = [asdict(r) for r in rows]
    out["passed"] = gate.passed(rows) and out.get("proxy", {}).get("passed", True)
    print(summary(out))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

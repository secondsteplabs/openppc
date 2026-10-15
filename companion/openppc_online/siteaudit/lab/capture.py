"""One measured load: a Chromium trace of a throttled page load, waited out as Lighthouse 13 waits under DevTools
throttling, and kept as a `LabRun` that lab.metrics turns into numbers. Not "trace", which already means the report's
number checker.

The wait (Lighthouse's waitForFullyLoaded with its non-simulated quiet windows): 5.25 s after First Contentful Paint
and after load, with the network at most 2 requests in flight and no high-priority request of the page in flight for
5.25 s, then 5.25 s without a long task; never past LOAD_CAP_MS. The trace records Lighthouse's categories, less the
script-source rundown it adds for DevTools (it copies every script into the trace and isn't timed).

A LabRun keeps only the events lab.metrics reads, without request headers, and each distinct screenshot as a colour
histogram; the screenshots themselves are dropped once counted.
"""
import contextlib
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from ..tags import hit_patterns, is_hit
from .metrics import SCHEDULABLE, WHITE, Event, NoNavigation, main_threads
from .throttle import LOAD_CAP_MS, Profile

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:  # the `render` extra isn't installed; render.py says how to install it
    PlaywrightError = PlaywrightTimeout = Exception  # type: ignore[assignment,misc]

CATEGORIES = ("-*", "disabled-by-default-lighthouse", "loading", "v8", "v8.execute", "blink.user_timing",
              "blink.console", "devtools.timeline", "disabled-by-default-devtools.timeline",
              "disabled-by-default-devtools.timeline.stack", "disabled-by-default-devtools.timeline.frame",
              "latencyInfo")  # with screenshots, which Playwright adds
QUIET_MS = 5250              # Lighthouse's nonSimulatedSettingsOverrides
POLL_MS = 100
KEEP = {"TracingStartedInBrowser", "TracingStartedInPage", "FrameCommittedInBrowser", "ProcessReadyInBrowser",
        "navigationStart", "firstPaint", "firstContentfulPaint", "largestContentfulPaint::Candidate",
        "largestContentfulPaint::Invalidate", "LayoutShift", "domContentLoadedEventEnd", "loadEventEnd", "viewport",
        "ResourceSendRequest", "ResourceReceiveResponse", "ResourceFinish"}
DROP_DATA = ("headers", "responseHeaders", "requestHeaders", "stackTrace")
NOT_NETWORK = ("data:", "blob:", "about:", "chrome:", "chrome-extension:", "file:", "filesystem:")
LONG_TASKS_JS = """() => {
  if (window.__openppcLastLongTask !== undefined) return;
  window.__openppcLastLongTask = performance.now();
  new PerformanceObserver(l => l.getEntries().forEach(e => {
    window.__openppcLastLongTask = Math.max(window.__openppcLastLongTask, e.startTime + e.duration);
  })).observe({entryTypes: ['longtask']});
}"""
SINCE_LONG_TASK_JS = "() => performance.now() - window.__openppcLastLongTask"
HEAVY_FILES = 5              # the largest files listed under a measurement
# Read after the trace stops: the LCP element (buffered entries, read synchronously), render-blocking files, the
# largest files
DETAILS_JS = """() => {
  const po = new PerformanceObserver(() => {});
  let lcp = null;
  try { po.observe({type: 'largest-contentful-paint', buffered: true}); const e = po.takeRecords(); lcp = e[e.length - 1] || null; }
  catch (e) {}
  po.disconnect();
  const el = lcp && lcp.element;
  const cls = el && typeof el.className === 'string' ? el.className.trim().split(/\\s+/).slice(0, 2) : [];
  const files = performance.getEntriesByType('resource');
  return {
    lcp_element: el ? el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + cls.filter(Boolean).map(c => '.' + c).join('') : '',
    lcp_url: (lcp && lcp.url) || '',
    blocking: files.filter(f => f.renderBlockingStatus === 'blocking').map(f => f.name),
    heavy: files.filter(f => f.transferSize > 0).sort((a, b) => b.transferSize - a.transferSize)
                .slice(0, HEAVY_FILES).map(f => [f.name, f.transferSize]),
  };
}""".replace("HEAVY_FILES", str(HEAVY_FILES))
# Each screenshot's red, green and blue histograms (256 bins each), leaving out near-white pixels, as speedline counts
# them; decoded by the browser, without colour management
HISTOGRAMS_JS = """async (shots) => {
  const out = [];
  for (const b64 of shots) {
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const bmp = await createImageBitmap(new Blob([bytes], {type: 'image/jpeg'}),
                                        {colorSpaceConversion: 'none', premultiplyAlpha: 'none'});
    const canvas = new OffscreenCanvas(bmp.width, bmp.height);
    const ctx = canvas.getContext('2d', {willReadFrequently: true});
    ctx.drawImage(bmp, 0, 0);
    const d = ctx.getImageData(0, 0, bmp.width, bmp.height).data;
    const h = new Array(768).fill(0);
    for (let i = 0; i < d.length; i += 4) {
      if (d[i] >= WHITE && d[i + 1] >= WHITE && d[i + 2] >= WHITE) continue;
      h[d[i]]++; h[256 + d[i + 1]]++; h[512 + d[i + 2]]++;
    }
    out.push(h);
  }
  return out;
}""".replace("WHITE", str(WHITE))


@dataclass
class LabRun:
    url: str
    device: str
    events: list[Event] = field(default_factory=list)
    trace_end: float = 0.0     # the trace's last timestamp, microseconds
    frames: list[tuple[float, list[int]]] = field(default_factory=list)  # (timestamp, histogram) per distinct screen
    capped: bool = False       # still loading, or not yet quiet, at LOAD_CAP_MS: measured as it was then
    hits_answered: int = 0     # tag hits this load answered itself
    details: dict[str, Any] = field(default_factory=dict)  # DETAILS_JS

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> "LabRun":
        raw = json.loads(text)
        raw["frames"] = [(ts, list(h)) for ts, h in raw.get("frames", [])]
        return cls(**raw)


def answer_hits(cdp: Any, answered: list[str]) -> None:
    """Tag hits get an empty 204 from here; everything else, and anything that goes wrong, continues to the network.
    CDP's Fetch, not page.route, which would turn the HTTP cache off and send every request through Python."""
    def paused(event: dict[str, Any]) -> None:
        url, request = event["request"]["url"], {"requestId": event["requestId"]}
        try:
            if event.get("resourceType") != "Document" and is_hit(url):
                cdp.send("Fetch.fulfillRequest", {**request, "responseCode": 204})
                answered.append(url)
                return
        except PlaywrightError:
            pass
        with contextlib.suppress(PlaywrightError):  # the page may have gone, with its request
            cdp.send("Fetch.continueRequest", request)
    cdp.on("Fetch.requestPaused", paused)
    cdp.send("Fetch.enable", {"patterns": [{"urlPattern": p, "requestStage": "Request"} for p in hit_patterns()]})


class _Network:
    """Requests in flight on the measured page, from CDP's Network events, as Lighthouse's network monitor counts
    them."""

    def __init__(self, cdp: Any) -> None:
        self.inflight: dict[str, bool] = {}  # request id: whether it is critical
        self.root_frame = ""
        cdp.on("Network.requestWillBeSent", self._sent)
        cdp.on("Network.loadingFinished", self._done)
        cdp.on("Network.loadingFailed", self._done)

    def _sent(self, e: dict[str, Any]) -> None:
        url = str(e.get("request", {}).get("url", ""))
        if url.startswith(NOT_NETWORK):
            return
        if e.get("type") == "Document" and not self.root_frame:
            self.root_frame = e.get("frameId", "")
        self.inflight[e["requestId"]] = (
            e.get("frameId") == self.root_frame and e.get("type") not in ("WebSocket", "EventSource")
            and e.get("request", {}).get("initialPriority") in ("VeryHigh", "High"))

    def _done(self, e: dict[str, Any]) -> None:
        self.inflight.pop(e.get("requestId", ""), None)

    def two_idle(self) -> bool:
        return len(self.inflight) <= 2

    def critical_idle(self) -> bool:
        return not any(self.inflight.values())


def _wait_quiet(page: Any, net: _Network, painted: Callable[[], float | None], loaded: float, started: float) -> bool:
    """Waits as Lighthouse does after load; False when LOAD_CAP_MS (from `started`) came first."""
    cap = started + LOAD_CAP_MS / 1000
    quiet = QUIET_MS / 1000
    two = crit = None

    def tick() -> bool:
        page.wait_for_timeout(POLL_MS)
        return time.monotonic() < cap

    while True:
        now = time.monotonic()
        two = (two or now) if net.two_idle() else None
        crit = (crit or now) if net.critical_idle() else None
        fcp = painted()
        if (fcp is not None and now - fcp >= quiet and now - loaded >= quiet and two and now - two >= quiet
                and crit and now - crit >= quiet):
            break
        if not tick():
            return False
    page.evaluate(LONG_TASKS_JS)
    while page.evaluate(SINCE_LONG_TASK_JS) < QUIET_MS:
        if not tick():
            return False
    return True


def slim(trace: dict[str, Any]) -> tuple[list[Event], float, list[tuple[float, str]]]:
    """The events lab.metrics reads (the main thread's tasks, not every thread's), the trace's end, and each
    screenshot that differs from the one before it."""
    events = trace.get("traceEvents", trace) if isinstance(trace, dict) else trace
    end = max((e.get("ts", 0) + e.get("dur", 0) for e in events), default=0)
    shots: list[tuple[float, str]] = []
    for e in sorted((e for e in events if e.get("name") == "Screenshot"), key=lambda e: e["ts"]):
        snap = (e.get("args") or {}).get("snapshot")
        if snap and (not shots or shots[-1][1] != snap):
            shots.append((e["ts"], snap))
    kept = [_clean(e) for e in events if e.get("name") in KEEP
            or (e.get("ph") == "M" and e.get("name") == "thread_name")]
    try:
        _, threads = main_threads(kept)
    except NoNavigation:
        threads = {}
    kept += [{k: e[k] for k in ("name", "ph", "ts", "dur", "pid", "tid") if k in e} for e in events
             if e.get("name") in SCHEDULABLE and e.get("dur") and threads.get(e.get("pid", -1)) == e.get("tid")]
    return kept, end, shots


def _clean(e: Event) -> Event:
    data = (e.get("args") or {}).get("data")
    if not isinstance(data, dict) or not any(k in data for k in DROP_DATA):
        return e
    return {**e, "args": {**e["args"], "data": {k: v for k, v in data.items() if k not in DROP_DATA}}}


# Lighthouse 13.5's computeBenchmarkIndex (core/lib/page-functions.js): a string-building loop that leans on the
# garbage collector and an array copy that doesn't, half a second each, averaged
BENCHMARK_JS = """() => {
  function benchmarkIndexGC() {
    const start = Date.now();
    let iterations = 0;
    while (Date.now() - start < 500) {
      let s = '';
      for (let j = 0; j < 10000; j++) s += 'a';
      if (s.length === 1) throw new Error('will never happen, but prevents compiler optimizations');
      iterations++;
    }
    const durationInSeconds = (Date.now() - start) / 1000;
    return Math.round(iterations / 10 / durationInSeconds);
  }
  function benchmarkIndexNoGC() {
    const arrA = [];
    const arrB = [];
    for (let i = 0; i < 100000; i++) arrA[i] = arrB[i] = i;
    const start = Date.now();
    let iterations = 0;
    while (iterations % 10 !== 0 || Date.now() - start < 500) {
      const src = iterations % 2 === 0 ? arrA : arrB;
      const tgt = iterations % 2 === 0 ? arrB : arrA;
      for (let j = 0; j < src.length; j++) tgt[j] = src[j];
      iterations++;
    }
    const durationInSeconds = (Date.now() - start) / 1000;
    return Math.round(iterations / 10 / durationInSeconds);
  }
  return (benchmarkIndexGC() + benchmarkIndexNoGC()) / 2;
}"""


def benchmark(browser: Any) -> float | None:
    """This computer's BenchmarkIndex, in a blank page with no throttling, as Lighthouse measures it before a load
    (1000 and up is a desktop-class CPU). None when the page can't run it."""
    page = browser.new_page()
    try:
        return float(page.evaluate(BENCHMARK_JS))
    except (PlaywrightError, TypeError, ValueError):
        return None
    finally:
        page.context.close()


def histograms(browser: Any, shots: list[str]) -> list[list[int]]:
    """Each JPEG screenshot's histograms, counted in a blank page of the same browser (nothing is fetched)."""
    if not shots:
        return []
    page = browser.new_page()
    try:
        return [list(h) for h in page.evaluate(HISTOGRAMS_JS, shots)]
    finally:
        page.context.close()


def capture(browser: Any, url: str, profile: Profile, proxy: str = "", block_hits: bool = True,
            raw: list[Event] | None = None) -> LabRun:
    """One throttled load of url, traced, through `proxy` (net.GuardProxy's address); every trace event but the
    screenshots is added to `raw` when it's given. Raises PlaywrightError when the page can't be loaded at all."""
    context = browser.new_context(service_workers="block", accept_downloads=False, **profile.context(),
                                  **({"proxy": {"server": proxy}} if proxy else {}))
    answered: list[str] = []
    run = LabRun(url, profile.device)
    tracing = False
    try:
        page = context.new_page()
        cdp = context.new_cdp_session(page)
        if block_hits:
            answer_hits(cdp, answered)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": profile.cpu})
        net = _Network(cdp)
        cdp.send("Network.enable")
        if network := profile.network():
            cdp.send("Network.emulateNetworkConditions", network)
        fcp: list[float] = []

        def lifecycle(e: dict[str, Any]) -> None:
            if e.get("name") == "firstContentfulPaint" and not fcp:
                fcp.append(time.monotonic())
        cdp.on("Page.lifecycleEvent", lifecycle)
        cdp.send("Page.enable")
        cdp.send("Page.setLifecycleEventsEnabled", {"enabled": True})
        browser.start_tracing(page=page, categories=list(CATEGORIES), screenshots=True)
        tracing = True
        started = time.monotonic()
        try:
            page.goto(url, wait_until="load", timeout=LOAD_CAP_MS)
            run.capped = not _wait_quiet(page, net, lambda: fcp[0] if fcp else None, time.monotonic(), started)
        except PlaywrightTimeout:
            run.capped = True
        data = browser.stop_tracing()
        tracing = False
        with contextlib.suppress(PlaywrightError):  # a page that navigated away mid-read keeps no details
            run.details = dict(page.evaluate(DETAILS_JS))
    finally:
        if tracing:
            with contextlib.suppress(PlaywrightError):
                browser.stop_tracing()
        context.close()
    trace = json.loads(data)
    if raw is not None:
        events = trace.get("traceEvents", trace) if isinstance(trace, dict) else trace
        raw.extend(e for e in events if e.get("name") != "Screenshot")
    run.events, run.trace_end, shots = slim(trace)
    run.frames = list(zip([ts for ts, _ in shots], histograms(browser, [s for _, s in shots])))
    run.hits_answered = len(answered)
    return run

"""Lab metrics from one load's trace, as Lighthouse 13 computes them when it measures a throttled load ("observed",
its DevTools throttling): First Contentful Paint and Largest Contentful Paint of the main frame, Cumulative Layout
Shift over the main frame and its subframes by session windows, Total Blocking Time between FCP and Time to
Interactive, Time to First Byte, and Speed Index by speedline's method. TTI only bounds TBT and picks the
representative run; it is never shown.

Ported from Lighthouse 13.5 (Apache-2.0: core/lib/tracehouse/trace-processor.js, core/computed/metrics/interactive.js
and cumulative-layout-shift.js, core/gather/driver/network-monitor.js, core/lib/median-run.js), the DevTools trace
engine (BSD-3-Clause: models/trace/lantern/metrics/TBTUtils.js, models/trace/insights/Common.js) and speedline-core
1.4 (MIT: lib/speed-index.js, lib/frame.js), credited in THIRD_PARTY_LICENSES.md.

Times are milliseconds from the time origin (the main frame's last navigationStart); trace timestamps are
microseconds.
"""
import math
import re
import statistics
from collections.abc import Iterable, Sequence
from typing import Any

Event = dict[str, Any]

SCHEDULABLE = {"RunTask", "ThreadControllerImpl::RunTask", "ThreadControllerImpl::DoWork",
               "TaskQueueManager::ProcessTaskFromWorkQueue"}
NAVIGATION_URL = re.compile(r"^(chrome|https?):")
NON_NETWORK = ("data:", "blob:", "about:", "chrome:", "chrome-extension:", "file:", "filesystem:", "javascript:")
LONG_TASK_MS = 50            # Lighthouse's blocking threshold and long-task line
QUIET_WINDOW_MS = 5000       # TTI: CPU and network quiet together this long
ALLOWED_REQUESTS = 2         # requests in flight a quiet network allows
RECENT_INPUT_MS = 500        # layout shifts this soon after the viewport is set count whatever had_recent_input says
CLS_GAP_US = 1_000_000       # a session window ends after a second without a shift
CLS_LIMIT_US = 5_000_000     # or after five seconds
WHITE = 249                  # speedline leaves out pixels this white in every channel
# The fast-mode curve: frames this far apart in progress (percent) skip the frames between them; 5 at 0 s apart, 3 at
# 1 s, -1 when far apart
FAST_MAX, FAST_MEDIAN, FAST_MIN = 5, 3, -1
SHOWN = ("fcp", "si", "lcp", "tbt", "cls", "ttfb")
UNSTABLE_CV = {"tbt": 0.25, "fcp": 0.10, "lcp": 0.10}  # coefficient of variation above which runs disagree


class NoNavigation(ValueError):
    """The trace has no navigation of the main frame to an http(s) page."""


def frame_id(e: Event) -> str | None:
    args = e.get("args") or {}
    data = args.get("data") or {}
    return data.get("frame") or data.get("frameID") or args.get("frame")


def _main_frame(events: Sequence[Event]) -> tuple[int, str]:
    """The traced tab's (process id, frame id)."""
    started = next((e for e in events if e["name"] == "TracingStartedInBrowser"), None)
    frames = ((started or {}).get("args") or {}).get("data", {}).get("frames") or []
    main = next((f for f in frames if not f.get("parent")), None)
    if main and main.get("processId") and main.get("frame"):
        return int(main["processId"]), str(main["frame"])
    page = next((e for e in events if e["name"] == "TracingStartedInPage"), None)
    if page and (page.get("args") or {}).get("data", {}).get("page"):
        return int(page["pid"]), str(page["args"]["data"]["page"])
    raise NoNavigation("the trace doesn't say which tab it traced")


def main_threads(events: Sequence[Event]) -> tuple[str, dict[int, int]]:
    """The main frame's id, and the renderer main thread of each process it was in (a cross-site redirect moves it)."""
    pid, frame = _main_frame(events)
    pids = [int(e["args"]["data"]["processId"]) for e in events
            if e["name"] in ("FrameCommittedInBrowser", "ProcessReadyInBrowser")
            and (e.get("args") or {}).get("data", {}).get("frame") == frame
            and e["args"]["data"].get("processId")] or [pid]
    out: dict[int, int] = {}
    for p in dict.fromkeys(pids):
        names = {e["args"].get("name"): e["tid"] for e in events
                 if e.get("ph") == "M" and e["name"] == "thread_name" and e.get("pid") == p}
        tid = names.get("CrRendererMain") or names.get("CrBrowserMain")
        if tid is not None:
            out[p] = tid
    return frame, out


def _frame_tree(events: Sequence[Event], main: str) -> set[str]:
    """The main frame and every frame under it."""
    parents: dict[str, str] = {}
    started = next((e for e in events if e["name"] == "TracingStartedInBrowser"), None)
    for f in ((started or {}).get("args") or {}).get("data", {}).get("frames") or []:
        if f.get("parent"):
            parents[f["frame"]] = f["parent"]
    for e in events:
        data = (e.get("args") or {}).get("data") or {}
        if e["name"] == "FrameCommittedInBrowser" and data.get("frame") and "url" in data:
            if data.get("parent"):
                parents[data["frame"]] = data["parent"]
            else:
                parents.pop(data["frame"], None)
    known = set(parents) | set(parents.values()) | {main}
    out = set()
    for f in known:
        seen, cur = set(), f
        while cur in parents and cur not in seen:
            seen.add(cur)
            cur = parents[cur]
        if cur == main:
            out.add(f)
    return out


def _navigation_of_interest(e: Event) -> bool:
    if e["name"] != "navigationStart":
        return False
    data = (e.get("args") or {}).get("data") or {}
    if "documentLoaderURL" not in data:
        return True
    return bool(data["documentLoaderURL"]) and bool(NAVIGATION_URL.match(data["documentLoaderURL"]))


def _lcp(frame_events: Sequence[Event], origin: float) -> Event | None:
    """The main frame's final LCP candidate, or None when there is none or it was invalidated last."""
    final: dict[str, Event] = {}
    for e in reversed(frame_events):
        if e["name"] not in ("largestContentfulPaint::Candidate", "largestContentfulPaint::Invalidate"):
            continue
        if not (e.get("args") or {}).get("frame"):
            continue
        if e["ts"] <= origin:
            break
        final.setdefault(e["args"]["frame"], e)
    best = None
    for e in final.values():
        data = e["args"].get("data") or {}
        if e["name"] == "largestContentfulPaint::Candidate" and data.get("size") is not None:
            if best is None or data["size"] > best["args"]["data"]["size"]:
                best = e
    return best


def layout_shift_score(events: Iterable[Event], viewport_ts: float) -> float:
    """CLS: the largest session window of shifts without recent input, each weighted by its frame's share of the
    viewport (weighted_score_delta, which is the score itself for the main frame)."""
    shifts: list[tuple[float, float]] = []
    respect_input = False
    for e in events:
        data = (e.get("args") or {}).get("data") or {}
        if e["name"] != "LayoutShift" or "is_main_frame" not in data or data.get("weighted_score_delta") is None:
            continue
        if data.get("had_recent_input"):
            if (e["ts"] - viewport_ts) / 1000 > RECENT_INPUT_MS or respect_input:
                continue
        else:
            respect_input = True
        shifts.append((e["ts"], float(data["weighted_score_delta"])))
    best = window = 0.0
    first = prev = -math.inf
    for ts, score in shifts:
        if ts - first > CLS_LIMIT_US or ts - prev > CLS_GAP_US:
            first, window = ts, 0.0
        prev = ts
        window += score
        best = max(best, window)
    return best


def top_level_tasks(events: Sequence[Event], threads: dict[int, int], origin: float) -> list[tuple[float, float]]:
    """The main thread's tasks as (start, end), in order; a task overlapping the next is cut short (a Chrome bug)."""
    out: list[list[float]] = []
    for e in sorted((e for e in events if e["name"] in SCHEDULABLE and e.get("dur")
                     and threads.get(e.get("pid", -1)) == e.get("tid")), key=lambda e: e["ts"]):
        start, end = (e["ts"] - origin) / 1000, (e["ts"] + e["dur"] - origin) / 1000
        if out and start < out[-1][1]:
            out[-1][1] = start - 0.001
        out.append([start, end])
    return [(s, e) for s, e in out]


def sum_blocking_time(tasks: Iterable[tuple[float, float]], start: float, end: float) -> float:
    """Each task's part beyond 50 ms, after clipping it to [start, end]: TBT with FCP and TTI as the bounds."""
    if end <= start:
        return 0.0
    total = 0.0
    for s, e in tasks:
        if e - s < LONG_TASK_MS or e < start or s > end:
            continue
        clipped = min(e, end) - max(s, start)
        if clipped > LONG_TASK_MS:
            total += clipped - LONG_TASK_MS
    return total


def network_quiet_periods(requests: Iterable[tuple[float, float | None]], allowed: int,
                          end: float) -> list[tuple[float, float]]:
    """Periods with at most `allowed` requests in flight, from (start, finish or None) pairs."""
    bounds = sorted([(s, True) for s, _ in requests] + [(f, False) for _, f in requests if f is not None],
                    key=lambda b: b[0])
    out, inflight, since = [], 0, -math.inf
    for t, starts in (b for b in bounds if b[0] <= end):
        if starts:
            if inflight == allowed:
                out.append((since, t))
            inflight += 1
        else:
            inflight -= 1
            if inflight == allowed:
                since = t
    if inflight <= allowed:
        out.append((since, end))
    return [p for p in out if p[0] != p[1]]


def cpu_quiet_periods(long_tasks: Sequence[tuple[float, float]], end: float) -> list[tuple[float, float]]:
    if not long_tasks:
        return [(-math.inf, end)]
    out = [(-math.inf, long_tasks[0][0])]
    for i, (_, e) in enumerate(long_tasks):
        out.append((e, long_tasks[i + 1][0] if i + 1 < len(long_tasks) else end))
    return out


def interactive(tasks: Sequence[tuple[float, float]], requests: Iterable[tuple[float, float | None]], fcp: float,
                dcl: float | None, end: float) -> float | None:
    """TTI: the start of the first CPU quiet window of 5 s that overlaps a network quiet window of 5 s, both ending
    after FCP + 5 s; never before FCP or DOMContentLoaded. None when there is no such window (or no DOMContentLoaded)."""
    if dcl is None:
        return None

    def long_enough(p: tuple[float, float]) -> bool:
        return p[1] > fcp + QUIET_WINDOW_MS and p[1] - p[0] >= QUIET_WINDOW_MS

    cpu = [p for p in cpu_quiet_periods([t for t in tasks if t[1] - t[0] >= LONG_TASK_MS], end) if long_enough(p)]
    net = [p for p in network_quiet_periods(requests, ALLOWED_REQUESTS, end) if long_enough(p)]
    i = j = 0
    while i < len(cpu) and j < len(net):
        c, n = cpu[i], net[j]
        if c[0] >= n[0]:
            if n[1] >= c[0] + QUIET_WINDOW_MS:
                return max(c[0], fcp, dcl)
            j += 1
        elif c[1] >= n[0] + QUIET_WINDOW_MS:
            return max(c[0], fcp, dcl)
        else:
            i += 1
    return None


def _requests(events: Sequence[Event], origin: float) -> list[tuple[float, float | None]]:
    """Finished GET requests that didn't fail or answer 4xx/5xx, as TTI counts them: (sent, finished)."""
    sent: dict[str, Event] = {}
    status: dict[str, Event] = {}
    done: dict[str, Event] = {}
    for e in events:
        data = (e.get("args") or {}).get("data") or {}
        rid = data.get("requestId")
        if not rid:
            continue
        if e["name"] == "ResourceSendRequest":
            sent.setdefault(rid, e)
        elif e["name"] == "ResourceReceiveResponse":
            status[rid] = e
        elif e["name"] == "ResourceFinish":
            done[rid] = e
    out: list[tuple[float, float | None]] = []
    for rid, e in sent.items():
        data = e["args"]["data"]
        url = str(data.get("url", ""))
        if url.startswith(NON_NETWORK) or url.startswith(("ws:", "wss:")):
            continue
        fin = done.get(rid)
        code = ((status.get(rid) or {}).get("args") or {}).get("data", {}).get("statusCode") or 0
        if fin is None or fin["args"]["data"].get("didFail") or data.get("requestMethod", "GET") != "GET" \
                or code >= 400:
            continue
        finish = fin["args"]["data"].get("finishTime")
        out.append(((e["ts"] - origin) / 1000,
                    (finish * 1_000_000 - origin) / 1000 if finish else (fin["ts"] - origin) / 1000))
    return out


def _first_byte(events: Sequence[Event], navigation: Event, origin: float) -> float | None:
    """TTFB: the navigation's (final) response headers, from navigation start."""
    nav_id = ((navigation.get("args") or {}).get("data") or {}).get("navigationId")
    response = None
    for e in events:
        data = (e.get("args") or {}).get("data") or {}
        if e["name"] == "ResourceReceiveResponse" and nav_id and data.get("requestId") == nav_id:
            response = data
    timing = (response or {}).get("timing")
    if not timing or timing.get("requestTime") is None:
        return None
    headers = timing.get("receiveHeadersStart")
    if headers is None:
        headers = timing.get("receiveHeadersEnd")
    if headers is None:
        return None
    return (timing["requestTime"] * 1_000_000 + headers * 1000 - origin) / 1000


def _fast_mode_allowance(elapsed_ms: float) -> float:
    multiplier = FAST_MAX - FAST_MIN
    coefficient = math.log((FAST_MEDIAN - FAST_MIN) / multiplier)
    return multiplier * math.exp(coefficient * elapsed_ms / 1000) + FAST_MIN


def _frame_progress(current: Sequence[int], target: Sequence[int]) -> int:
    """How much of the way from blank (an all-white frame, whose histogram is empty) to the final frame this one is,
    in whole percent, by colour histograms."""
    match = total = 0
    for c, t in zip(current, target):
        match += min(c, t)
        total += t
    if match == 0 and total == 0:
        return 100
    return math.floor(match / total * 100)


def speed_index(frames: Sequence[tuple[float, Sequence[int]]], origin: float) -> float | None:
    """Speed Index (ms) from screenshots as (timestamp, 768-bin RGB histogram without white pixels): speedline's
    visual progress in fast mode, after a blank frame at the time origin, as Lighthouse runs it. None without
    frames, or when it comes to 0 (Lighthouse's SPEEDINDEX_OF_ZERO)."""
    shots = [(ts / 1000, list(h)) for ts, h in frames if ts >= origin]
    if not shots:
        return None
    shots.insert(0, (origin / 1000, [0] * len(shots[0][1])))
    target = shots[-1][1]
    progress: list[int | None] = [None] * len(shots)

    def get(i: int) -> int:
        if progress[i] is None:
            progress[i] = _frame_progress(shots[i][1], target)
        return progress[i]  # type: ignore[return-value]

    def between(lo: int, hi: int) -> None:
        low, high = get(lo), get(hi)
        if abs(low - high) < _fast_mode_allowance(shots[hi][0] - shots[lo][0]):
            for k in range(lo + 1, hi):
                progress[k] = low
        elif hi - lo > 1:
            mid = (lo + hi) // 2
            between(lo, mid)
            between(mid, hi)

    between(0, len(shots) - 1)
    values = [get(i) for i in range(len(shots))]
    first_paint = next((shots[i][0] for i, p in enumerate(values) if p > 0), None)
    if first_paint is None:
        return None
    start = origin / 1000
    si = first_paint - start
    prev_ts, prev_p = shots[0][0], values[0] / 100
    for (ts, _), p in zip(shots, values):
        if ts > first_paint:
            si += (ts - prev_ts) * (1 - prev_p)
        prev_ts, prev_p = ts, p / 100
    rounded = math.floor(si + 0.5)
    return float(rounded) if rounded else None


def measure(events: Sequence[Event], trace_end: float,
            frames: Sequence[tuple[float, Sequence[int]]] = ()) -> dict[str, float | None]:
    """One load's metrics from its trace events: fcp, lcp, cls, tbt, ttfb, si and tti (ms; CLS unitless). tti is
    None when the load found no quiet window, and TBT then runs to the trace's end."""
    events = sorted(events, key=lambda e: e.get("ts", 0))
    main, threads = main_threads(events)
    tree = _frame_tree(events, main)
    frame_events = [e for e in events if frame_id(e) == main]
    navigation = next((e for e in reversed(frame_events) if _navigation_of_interest(e)), None)
    if navigation is None:
        raise NoNavigation("the trace has no navigation to an http(s) page")
    origin = navigation["ts"]

    def first(name: str) -> float | None:
        e = next((e for e in frame_events if e["name"] == name and e["ts"] > origin), None)
        return None if e is None else (e["ts"] - origin) / 1000

    fcp, dcl = first("firstContentfulPaint"), first("domContentLoadedEventEnd")
    lcp_event = _lcp(frame_events, origin)
    # Lighthouse's trace starts after its about:blank, ours takes it in: the blank page's viewport event is not the one
    viewport = next((e["ts"] for e in frame_events if e["name"] == "viewport" and e["ts"] >= origin), origin)
    tree_events = [e for e in events if frame_id(e) in tree]
    end = (trace_end - origin) / 1000
    tasks = top_level_tasks(events, threads, origin)
    requests = _requests(events, origin)
    tti = interactive(tasks, requests, fcp, dcl, end) if fcp is not None else None
    return {
        "fcp": fcp,
        "lcp": None if lcp_event is None else (lcp_event["ts"] - origin) / 1000,
        "cls": layout_shift_score(tree_events, viewport),
        "tbt": None if fcp is None else sum_blocking_time(tasks, fcp, tti if tti is not None else end),
        "ttfb": _first_byte(events, navigation, origin),
        "si": speed_index(frames, origin),
        "tti": tti,
    }


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(values))


def representative(runs: Sequence[dict[str, float | None]]) -> int | None:
    """Lighthouse CI's median run: the run nearest the median FCP and median TTI (squared distance), ties to the
    lower TTI. Runs without TTI are left out while any run has one; without TTI anywhere, FCP alone decides."""
    with_fcp = [i for i, r in enumerate(runs) if r.get("fcp") is not None]
    if not with_fcp:
        return 0 if runs else None
    valid = [i for i in with_fcp if runs[i].get("tti") is not None]
    keys = ("fcp", "tti") if valid else ("fcp",)
    pool = valid or with_fcp
    values = [{k: float(runs[i][k] or 0.0) for k in keys} for i in range(len(runs))]
    middle = {k: _median([values[i][k] for i in pool]) for k in keys}

    def distance(i: int) -> tuple[float, float]:
        return sum((middle[k] - values[i][k]) ** 2 for k in keys), float(runs[i].get("tti") or 0.0)

    return min(pool, key=distance)


def spread(runs: Sequence[dict[str, float | None]]) -> dict[str, tuple[float, float]]:
    """Each shown metric's lowest and highest value across the runs that measured it."""
    out = {}
    for k in SHOWN:
        values = [v for r in runs if (v := r.get(k)) is not None]
        if values:
            out[k] = (min(values), max(values))
    return out


def unstable(runs: Sequence[dict[str, float | None]]) -> list[str]:
    """The metrics whose runs disagree: coefficient of variation (population) above UNSTABLE_CV."""
    out = []
    for k, line in UNSTABLE_CV.items():
        values = [v for r in runs if (v := r.get(k)) is not None]
        if len(values) > 1 and statistics.fmean(values) > 0 and \
                statistics.pstdev(values) / statistics.fmean(values) > line:
            out.append(k)
    return out

"""The lab metrics Lighthouse computes from a throttled load's trace (lab.metrics), checked against the rules in
Lighthouse 13.5's code (cited per test), and the trace a load keeps (lab.capture). No browser: synthetic traces."""
import math

import pytest

from openppc_online.siteaudit.lab import metrics
from openppc_online.siteaudit.lab.capture import LabRun, slim

ORIGIN = 1_000_000  # navigationStart, microseconds


def at(ms):
    return ORIGIN + ms * 1000


# Total Blocking Time (lantern/metrics/TBTUtils.js): each task's part beyond 50 ms, clipped to FCP..TTI first

def test_tbt_counts_the_part_of_each_long_task_beyond_50_ms():
    assert metrics.sum_blocking_time([(1000, 1100), (2000, 2049), (3000, 3050), (4000, 4300)], 0, 10_000) == 300


def test_tbt_clips_a_task_to_fcp_and_tti_before_taking_50_ms_off():
    # TBTUtils' own example: a 150 ms task [0, 150] with FCP at 50 is clipped to [50, 150]: 50 ms blocking
    assert metrics.sum_blocking_time([(0, 150)], 50, 1000) == 50
    assert metrics.sum_blocking_time([(900, 1100)], 0, 1000) == 50   # clipped at TTI to [900, 1000]
    assert metrics.sum_blocking_time([(0, 120)], 100, 1000) == 0     # 20 ms left after FCP blocks nothing
    assert metrics.sum_blocking_time([(0, 500), (2000, 2500)], 600, 1500) == 0
    assert metrics.sum_blocking_time([(0, 500)], 1000, 1000) == 0    # no window: TTI at FCP


# Time to Interactive (core/computed/metrics/interactive.js, network-monitor.js)

def test_tti_is_the_start_of_the_first_5_s_cpu_quiet_window_inside_a_5_s_network_quiet_window():
    tasks = [(1500, 1600), (2000, 2100), (9000, 9100)]
    assert metrics.interactive(tasks, [], fcp=1000, dcl=800, end=20_000) == 2100


def test_tti_waits_for_the_network_but_is_the_cpu_window_s_start():
    busy = [(0, 12_000)] * 3  # three requests in flight until 12 s: the network is quiet from then on
    tasks = [(2000, 2100), (9000, 9100)]
    assert metrics.interactive(tasks, busy, fcp=1000, dcl=800, end=30_000) == 9100


def test_tti_is_never_before_fcp_or_dom_content_loaded():
    assert metrics.interactive([], [], fcp=1000, dcl=800, end=20_000) == 1000
    assert metrics.interactive([], [], fcp=1000, dcl=3000, end=20_000) == 3000


def test_no_tti_without_a_quiet_window_or_dom_content_loaded():
    tasks = [(t, t + 60) for t in range(1000, 20_000, 1000)]  # a long task every second until the end
    assert metrics.interactive(tasks, [], fcp=1000, dcl=800, end=20_000) is None
    assert metrics.interactive([], [], fcp=1000, dcl=None, end=20_000) is None
    assert metrics.interactive([], [], fcp=1000, dcl=800, end=5500) is None  # the trace ended too soon


def test_network_quiet_allows_two_requests_in_flight():
    requests = [(0, 1000), (0, 2000), (500, 3000)]
    assert metrics.network_quiet_periods(requests, 2, 10_000) == [(-math.inf, 500), (1000, 10_000)]
    assert metrics.network_quiet_periods(requests, 0, 10_000) == [(-math.inf, 0), (3000, 10_000)]


# Cumulative Layout Shift (core/computed/metrics/cumulative-layout-shift.js)

def shift(ms, score, main=True, recent=False):
    return {"name": "LayoutShift", "ts": at(ms), "args": {"data": {
        "is_main_frame": main, "weighted_score_delta": score, "score": score * (1 if main else 4),
        "had_recent_input": recent}}}


def test_cls_is_the_largest_session_window():
    shifts = [shift(1000, 0.05), shift(1500, 0.05), shift(4000, 0.2)]  # 2.5 s gap: a new window
    assert metrics.layout_shift_score(shifts, ORIGIN) == pytest.approx(0.2)
    windowed = [shift(t, 0.03) for t in range(1000, 8000, 900)]  # gaps under 1 s, but a window lasts 5 s at most
    assert metrics.layout_shift_score(windowed, ORIGIN) == pytest.approx(0.03 * 6)


def test_cls_counts_iframes_by_their_weighted_score():
    assert metrics.layout_shift_score([shift(1000, 0.02, main=False), shift(1200, 0.05)], ORIGIN) \
        == pytest.approx(0.07)


def test_cls_counts_input_flagged_shifts_only_right_after_the_viewport_is_set():
    early = [shift(100, 0.1, recent=True), shift(1000, 0.05)]
    assert metrics.layout_shift_score(early, ORIGIN) == pytest.approx(0.15)
    late = [shift(1000, 0.05), shift(1100, 0.1, recent=True)]  # after a real shift, the flag is respected
    assert metrics.layout_shift_score(late, ORIGIN) == pytest.approx(0.05)
    assert metrics.layout_shift_score([shift(900, 0.1, recent=True)], ORIGIN) == 0


# Speed Index (speedline-core lib/speed-index.js, as Lighthouse runs it: fast mode, from the time origin)

def hist(progress, size=1000):
    """A histogram `progress` per cent of the way to the final frame's."""
    h = [0] * 768
    h[10] = h[256 + 10] = h[512 + 10] = size * progress // 100
    return h


def test_speed_index_sums_how_unfinished_the_screen_looked():
    frames = [(at(1000), hist(50)), (at(2000), hist(100))]
    assert metrics.speed_index(frames, ORIGIN) == 1500  # 1000 blank, then 1000 at half done


def test_speed_index_skips_frames_before_the_time_origin_and_needs_some_paint():
    frames = [(ORIGIN - 5000, hist(100)), (at(800), hist(100))]
    assert metrics.speed_index(frames, ORIGIN) == 800
    assert metrics.speed_index([], ORIGIN) is None
    assert metrics.speed_index([(at(500), [0] * 768)], ORIGIN) is None  # a white page: Lighthouse's SPEEDINDEX_OF_ZERO


def test_fast_mode_carries_progress_over_frames_too_close_to_differ():
    assert metrics._fast_mode_allowance(0) == pytest.approx(5)
    assert metrics._fast_mode_allowance(1000) == pytest.approx(3)
    frames = [(at(200), hist(60)), (at(400), hist(1)), (at(1000), hist(50)), (at(3000), hist(100))]
    # blank at 0 and 1% at 400 ms are close enough that the frame between them is taken as blank, unseen
    assert metrics.speed_index(frames, ORIGIN) == 400 + 600 * 0.99 + 2000 * 0.5


# One load's trace

def trace_events(lcp_size=5000):
    meta = [{"name": "thread_name", "ph": "M", "pid": 1, "tid": 10, "ts": 0, "args": {"name": "CrRendererMain"}},
            {"name": "thread_name", "ph": "M", "pid": 1, "tid": 11, "ts": 0, "args": {"name": "Compositor"}}]
    frame = {"frame": "F", "processId": 1, "url": "about:blank"}
    events = meta + [
        {"name": "TracingStartedInBrowser", "ph": "I", "pid": 9, "tid": 1, "ts": ORIGIN - 50_000,
         "args": {"data": {"frames": [frame, {"frame": "IF", "parent": "F", "processId": 1, "url": ""}]}}},
        {"name": "navigationStart", "ph": "R", "pid": 1, "tid": 10, "ts": ORIGIN - 40_000,
         "args": {"frame": "F", "data": {"documentLoaderURL": "about:blank"}}},
        {"name": "navigationStart", "ph": "R", "pid": 1, "tid": 10, "ts": ORIGIN,
         "args": {"frame": "F", "data": {"documentLoaderURL": "https://shop.test/", "navigationId": "N"}}},
        {"name": "ResourceSendRequest", "ph": "I", "pid": 1, "tid": 10, "ts": at(10),
         "args": {"data": {"requestId": "N", "url": "https://shop.test/", "requestMethod": "GET", "frame": "F"}}},
        {"name": "ResourceReceiveResponse", "ph": "I", "pid": 1, "tid": 10, "ts": at(320),
         "args": {"data": {"requestId": "N", "statusCode": 200, "headers": [{"name": "set-cookie", "value": "s=1"}],
                           "timing": {"requestTime": ORIGIN / 1e6 + 0.01, "receiveHeadersStart": 290.5}}}},
        {"name": "ResourceFinish", "ph": "I", "pid": 1, "tid": 10, "ts": at(400),
         "args": {"data": {"requestId": "N", "didFail": False, "finishTime": ORIGIN / 1e6 + 0.4}}},
        {"name": "firstContentfulPaint", "ph": "R", "pid": 1, "tid": 10, "ts": at(800), "args": {"frame": "F"}},
        {"name": "largestContentfulPaint::Candidate", "ph": "R", "pid": 1, "tid": 10, "ts": at(900),
         "args": {"frame": "F", "data": {"size": 100}}},
        {"name": "largestContentfulPaint::Candidate", "ph": "R", "pid": 1, "tid": 10, "ts": at(1500),
         "args": {"frame": "F", "data": {"size": lcp_size}}},
        {"name": "domContentLoadedEventEnd", "ph": "R", "pid": 1, "tid": 10, "ts": at(1200), "args": {"frame": "F"}},
        {"name": "RunTask", "ph": "X", "pid": 1, "tid": 10, "ts": at(1000), "dur": 250_000},
        {"name": "RunTask", "ph": "X", "pid": 1, "tid": 10, "ts": at(3000), "dur": 120_000},
        {"name": "RunTask", "ph": "X", "pid": 1, "tid": 11, "ts": at(3000), "dur": 900_000},  # not the main thread
        shift(2000, 0.04), shift(2100, 0.02, main=False) | {"args": {"data": {
            "is_main_frame": False, "weighted_score_delta": 0.02, "frame": "IF"}}},
    ]
    events[-2]["args"]["data"]["frame"] = "F"
    return events


def test_a_load_s_metrics_come_from_its_trace():
    got = metrics.measure(trace_events(), at(20_000), [(at(800), hist(60)), (at(1500), hist(100))])
    assert got["fcp"] == 800 and got["lcp"] == 1500 and got["ttfb"] == pytest.approx(300.5)
    assert got["tti"] == 3120  # after the last long task, 3120 to 20000 is quiet
    assert got["tbt"] == 200 + 70  # the other thread's 900 ms task is not the page's
    assert got["cls"] == pytest.approx(0.06) and got["si"] == 800 + 700 * 0.4


def test_without_a_quiet_window_tbt_counts_to_the_end_of_the_trace():
    events = trace_events() + [{"name": "RunTask", "ph": "X", "pid": 1, "tid": 10, "ts": at(t), "dur": 80_000}
                               for t in range(4000, 9000, 1000)]
    got = metrics.measure(events, at(9500))
    assert got["tti"] is None and got["tbt"] == 200 + 70 + 5 * 30


def test_an_invalidated_lcp_is_not_measured_and_a_trace_with_no_page_is_refused():
    events = trace_events() + [{"name": "largestContentfulPaint::Invalidate", "ph": "R", "pid": 1, "tid": 10,
                                "ts": at(1600), "args": {"frame": "F"}}]
    assert metrics.measure(events, at(20_000))["lcp"] is None
    blank = [e for e in trace_events() if e.get("args", {}).get("data", {}).get("navigationId") != "N"]
    with pytest.raises(metrics.NoNavigation):
        metrics.measure(blank, at(20_000))


def test_a_lab_run_keeps_only_what_the_metrics_read():
    shot = {"name": "Screenshot", "ph": "O", "pid": 1, "tid": 10, "args": {"snapshot": "AAAA"}}
    noise = {"name": "Paint", "ph": "X", "pid": 1, "tid": 10, "ts": at(5), "dur": 10, "args": {"data": {}}}
    events, end, shots = slim({"traceEvents": trace_events() + [noise, shot | {"ts": at(100)},
                                                                 shot | {"ts": at(200)},
                                                                 shot | {"ts": at(300), "args": {"snapshot": "BBBB"}}]})
    assert end == at(3900) and [s for _, s in shots] == ["AAAA", "BBBB"]
    assert not any(e["name"] in ("Paint", "Screenshot") for e in events)
    assert [e["tid"] for e in events if e["name"] == "RunTask"] == [10, 10]
    response = next(e for e in events if e["name"] == "ResourceReceiveResponse")
    assert "headers" not in response["args"]["data"] and response["args"]["data"]["timing"]
    run = LabRun("https://shop.test/", "mobile", events, end, [(at(800), hist(60))], capped=True)
    again = LabRun.from_json(run.to_json())
    assert again == run and metrics.measure(again.events, again.trace_end, again.frames)["fcp"] == 800


# Runs (Lighthouse CI's median run, core/lib/median-run.js)

def test_the_representative_run_is_nearest_the_median_fcp_and_tti():
    runs = [{"fcp": 1000, "tti": 5000}, {"fcp": 1200, "tti": 9000}, {"fcp": 1100, "tti": 6000}]
    assert metrics.representative(runs) == 2
    tie = [{"fcp": 1000, "tti": 6000}, {"fcp": 1000, "tti": 4000}]  # both as far from the medians: the lower TTI
    assert metrics.representative(tie) == 1


def test_runs_without_tti_are_left_out_while_any_has_one():
    runs = [{"fcp": 3000, "tti": None}, {"fcp": 1000, "tti": 5000}, {"fcp": 1300, "tti": 7000}]
    assert metrics.representative(runs) == 1  # as near the medians as run 2, with the lower TTI
    assert metrics.representative([{"fcp": 900, "tti": None}, {"fcp": 2000, "tti": None},
                                   {"fcp": 1000, "tti": None}]) == 2
    assert metrics.representative([{"fcp": None}]) == 0 and metrics.representative([]) is None


def test_the_range_and_stability_of_the_runs():
    runs = [{"fcp": 1000, "lcp": 2000, "tbt": 100}, {"fcp": 1050, "lcp": 2100, "tbt": 300},
            {"fcp": 1020, "lcp": 2050, "tbt": 120}]
    assert metrics.spread(runs) == {"fcp": (1000, 1050), "lcp": (2000, 2100), "tbt": (100, 300)}
    assert metrics.unstable(runs) == ["tbt"]  # TBT varies by about 52%; FCP and LCP by about 2%
    assert metrics.unstable(runs[:1]) == []

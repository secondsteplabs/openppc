"""The native lab's setup is Lighthouse's own: the screens, user agents and DevTools (applied) throttling of
Lighthouse 13, copied from core/config/constants.js and Lantern's simulation/Constants.ts. Lantern's 150 ms and
1.6 Mbps are its simulator's inputs; applied, DevTools throttling scales them by 3.75 and 0.9."""
import pytest

from openppc_online.siteaudit.lab import throttle
from openppc_online.siteaudit.lab.throttle import DESKTOP, MOBILE

# Lighthouse 13.5: throttling.mobileSlow4G and desktopDense4G, screenEmulationMetrics, userAgents, maxWaitForLoad
RTT_FACTOR, THROUGHPUT_FACTOR = 3.75, 0.9
SLOW_4G = {"rttMs": 150, "throughputKbps": 1.6 * 1024, "uploadKbps": 750, "cpuSlowdownMultiplier": 4}
MOTO_G_POWER = {"mobile": True, "width": 412, "height": 823, "deviceScaleFactor": 1.75}
DESKTOP_SCREEN = {"mobile": False, "width": 1350, "height": 940, "deviceScaleFactor": 1}


def test_the_mobile_profile_is_lighthouses_applied_slow_4g_on_a_moto_g_power():
    assert MOBILE.latency_ms == pytest.approx(SLOW_4G["rttMs"] * RTT_FACTOR) == 562.5
    assert MOBILE.down_kbps == pytest.approx(SLOW_4G["throughputKbps"] * THROUGHPUT_FACTOR)
    assert MOBILE.up_kbps == pytest.approx(SLOW_4G["uploadKbps"] * THROUGHPUT_FACTOR)
    assert MOBILE.cpu == SLOW_4G["cpuSlowdownMultiplier"]
    assert (MOBILE.mobile, MOBILE.width, MOBILE.height, MOBILE.scale) == tuple(MOTO_G_POWER.values())
    assert "moto g power (2022)" in MOBILE.user_agent and "Mobile Safari" in MOBILE.user_agent


def test_the_desktop_profile_throttles_no_network_as_lighthouse_applies_it():
    # desktopDense4G's requestLatencyMs and throughputs are 0, "unset": DevTools throttling leaves the network alone
    assert (DESKTOP.latency_ms, DESKTOP.down_kbps, DESKTOP.up_kbps, DESKTOP.cpu) == (0, 0, 0, 1)
    assert (DESKTOP.mobile, DESKTOP.width, DESKTOP.height, DESKTOP.scale) == tuple(DESKTOP_SCREEN.values())
    assert DESKTOP.network() is None and "Macintosh" in DESKTOP.user_agent


def test_what_the_browser_is_told():
    assert MOBILE.context() == {"viewport": {"width": 412, "height": 823}, "device_scale_factor": 1.75,
                                "is_mobile": True, "has_touch": True, "user_agent": MOBILE.user_agent}
    assert MOBILE.network() == {"offline": False, "latency": 562.5, "downloadThroughput": 1474.56 * 1024 / 8,
                                "uploadThroughput": 675 * 1024 / 8}
    assert throttle.LOAD_CAP_MS == 45_000  # maxWaitForLoad: then Lighthouse measures what loaded, and so do we
    assert "rough estimate" in MOBILE.label and "562.5 ms" in MOBILE.label and "simulated" not in MOBILE.label

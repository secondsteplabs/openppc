"""The screens, user agents and throttling a speed load uses: Lighthouse 13's, as its DevTools (applied) throttling
sets up its own tab. Lighthouse's default is simulated throttling, which loads the page fast and works out the slow
timings in its simulator (Lantern), so these numbers are a rough estimate of its score's inputs, not a copy of them.

Copied from Lighthouse's core/config/constants.js and Lantern's simulation/Constants.ts (Apache-2.0 and BSD-3,
credited in THIRD_PARTY_LICENSES.md); tests/test_lab.py checks each value. Lantern's 150 ms and 1.6 Mbps are the
simulator's inputs: applied as they are, they would make a load faster than the phone they describe, so DevTools
throttling scales latency by 3.75 and throughput by 0.9.
"""
from dataclasses import dataclass, replace
from typing import Any

LOAD_CAP_MS = 45_000  # Lighthouse's maxWaitForLoad: a page still loading then is measured as it is, and flagged
MOBILE_LATENCY_MS = 562.5    # 150 ms x 3.75
MOBILE_DOWN_KBPS = 1474.56   # 1.6 x 1024 kbps x 0.9
MOBILE_UP_KBPS = 675.0       # 750 kbps x 0.9
MOBILE_CPU = 4
MOBILE_UA = ("Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/136.0.0.0 Mobile Safari/537.36")
DESKTOP_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/136.0.0.0 Safari/537.36")


@dataclass(frozen=True)
class Profile:
    device: str          # "mobile" or "desktop"
    width: int
    height: int
    scale: float         # device pixel ratio
    mobile: bool
    user_agent: str
    cpu: float           # CPU slowdown
    latency_ms: float    # per request; 0 leaves the network alone, as Lighthouse's desktop profile does
    down_kbps: float
    up_kbps: float

    def context(self) -> dict[str, Any]:
        """Playwright's new_context arguments."""
        return {"viewport": {"width": self.width, "height": self.height}, "device_scale_factor": self.scale,
                "is_mobile": self.mobile, "has_touch": self.mobile, "user_agent": self.user_agent}

    def network(self) -> dict[str, Any] | None:
        """CDP Network.emulateNetworkConditions' parameters, in bytes per second, or None for no throttling."""
        if not self.latency_ms:
            return None
        return {"offline": False, "latency": self.latency_ms, "downloadThroughput": self.down_kbps * 1024 / 8,
                "uploadThroughput": self.up_kbps * 1024 / 8}

    def unthrottled(self) -> "Profile":
        """The same screen and user agent, at full speed: the load Lighthouse's simulator (Lantern) starts from."""
        return replace(self, cpu=1, latency_ms=0, down_kbps=0, up_kbps=0)

    @property
    def label(self) -> str:
        if self.device == "desktop":
            return f"desktop (rough estimate): {self.width}x{self.height} screen, no throttling"
        return (f"throttled phone (rough estimate): {self.width}x{self.height} screen, {self.cpu:g}x slower CPU, "
                f"{self.latency_ms:g} ms latency, {self.down_kbps / 1024:.2f} Mbps down")


MOBILE = Profile("mobile", 412, 823, 1.75, True, MOBILE_UA, MOBILE_CPU, MOBILE_LATENCY_MS, MOBILE_DOWN_KBPS,
                 MOBILE_UP_KBPS)
DESKTOP = Profile("desktop", 1350, 940, 1, False, DESKTOP_UA, 1, 0, 0, 0)

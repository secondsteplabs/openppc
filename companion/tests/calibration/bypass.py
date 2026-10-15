"""What the calibration does that OpenPPC never may: a browser without the guard, for the proxy gate only (it measures
what the guard's proxy costs a load), and a browser that ignores certificate errors, for the fixtures' self-signed
certificate. Both stay offline, since only the fixtures' names resolve. They live here, never in openppc_online/,
and tests/test_boundary.py checks that the flags they use stay out of the package."""
from typing import Any

from .fixtures import HOST, OTHER_HOSTS

IGNORE_CERTIFICATES = "--ignore-certificate-errors"


def launch_unguarded(pw: Any, tls: bool = False) -> Any:
    """Chromium with no proxy at all, the fixtures' names mapped to loopback by the browser itself."""
    rules = ",".join(f"MAP {h} 127.0.0.1" for h in (HOST, *OTHER_HOSTS))
    return pw.chromium.launch(channel="chromium", args=["--disable-quic", f"--host-resolver-rules={rules}",
                                                        *([IGNORE_CERTIFICATES] if tls else [])])


class _Launcher:
    def __init__(self, chromium: Any) -> None:
        self._chromium = chromium

    def launch(self, **kwargs: Any) -> Any:
        return self._chromium.launch(**{**kwargs, "args": [*kwargs.get("args", []), IGNORE_CERTIFICATES]})


class _Trusting:
    def __init__(self, pw: Any) -> None:
        self.chromium = _Launcher(pw.chromium)


def trusting(pw: Any, tls: bool = True) -> Any:
    """Playwright as render._launch uses it, whose browsers also ignore certificate errors when tls, so OpenPPC's own
    launch is what gets measured on the HTTPS fixtures."""
    return _Trusting(pw) if tls else pw

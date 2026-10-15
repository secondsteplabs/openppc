"""A browser without the guard, for the proxy gate only: it measures what the guard's proxy costs a load. It lives
here, never in openppc_online/, and tests/test_boundary.py checks that the flag it uses stays out of the package."""
from typing import Any

from .fixtures import HOST, OTHER_HOSTS


def launch_unguarded(pw: Any) -> Any:
    """Chromium with no proxy at all, the fixtures' names mapped to loopback by the browser itself."""
    rules = ",".join(f"MAP {h} 127.0.0.1" for h in (HOST, *OTHER_HOSTS))
    return pw.chromium.launch(channel="chromium", args=["--disable-quic", f"--host-resolver-rules={rules}"])

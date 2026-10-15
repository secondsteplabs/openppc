"""Lighthouse itself, on a page OpenPPC opens: the calibration's reference, and later `--lighthouse`.

Node runs a Lighthouse 13 installed with npm, started directly (a .cmd shim would hand its arguments to cmd.exe,
which re-reads them). It attaches over the browser's DevTools port to a page in a context whose traffic goes
through net.GuardProxy, so Lighthouse's load meets the same rules as OpenPPC's own. The port is on 127.0.0.1, opened
only for the run (render._launch with devtools=True), and the guard refuses it, so no page reaches it through the
proxy. Lighthouse sends no error reports from here (off unless asked, as a module), and its load fires the page's
tags, which OpenPPC's own loads answer themselves (render.BLOCK_HITS).
"""
import json
import secrets
import shutil
import subprocess
import time
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

from ..net import Guard
from .lhr import KNOWN_MAJOR

ATTACH = "lighthouse.mjs"
RUN_S = 300                  # Lighthouse's 45 s load cap, its quiet waits and its audits, with room to spare
PORT_WAIT_S = 5.0            # for Chrome to write its DevToolsActivePort file after starting
METHODS = ("devtools", "simulate")
# The metrics audit's names for lab.metrics.measure's
METRICS = {"fcp": "firstContentfulPaint", "lcp": "largestContentfulPaint", "tbt": "totalBlockingTime",
           "cls": "cumulativeLayoutShift", "si": "speedIndex", "ttfb": "timeToFirstByte", "tti": "interactive"}


class Failed(ValueError):
    """Lighthouse ran and didn't produce a report."""


def folder(path: str | Path) -> Path:
    """The Lighthouse package (the folder with core/index.js), given it or a project that installed it. Raises
    ValueError when there's none, or it isn't Lighthouse KNOWN_MAJOR."""
    base = Path(path)
    for candidate in (base, base / "node_modules" / "lighthouse"):
        try:
            info = json.loads((candidate / "package.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(info, dict) or info.get("name") != "lighthouse" \
                or not (candidate / "core" / "index.js").is_file():
            continue
        version = str(info.get("version", ""))
        if version.split(".")[0] != str(KNOWN_MAJOR):
            raise ValueError(f"{candidate} has Lighthouse {version}; OpenPPC reads Lighthouse {KNOWN_MAJOR}")
        return candidate.resolve()
    raise ValueError(f"no Lighthouse in {base}: install it there with npm install lighthouse@{KNOWN_MAJOR}")


def node() -> str:
    """node itself, never a script that wraps it."""
    found = shutil.which("node")
    if not found:
        raise ValueError("Lighthouse needs Node.js, and node isn't on PATH")
    if Path(found).suffix.lower() in (".cmd", ".bat"):
        raise ValueError(f"node on PATH is a script ({found}) that cmd.exe would run; put node.exe first on PATH")
    return found


def attach(browser: Any, guard: Guard) -> str:
    """The browser's DevTools address (ws://127.0.0.1:port/devtools/browser/id), from the DevToolsActivePort file
    Chrome writes in its profile folder, found from chrome://version. Closes the port to every page in `guard`."""
    page = browser.new_page()
    try:
        page.goto("chrome://version")
        profile = Path(page.locator("#profile_path").inner_text().strip())
    finally:
        page.context.close()
    deadline = time.monotonic() + PORT_WAIT_S
    while True:
        try:
            port, path = (profile.parent / "DevToolsActivePort").read_text(encoding="utf-8").split()[:2]
            break
        except (OSError, ValueError) as e:
            if time.monotonic() > deadline:
                raise ValueError("the browser has no DevTools port (it was launched without one)") from e
            time.sleep(0.1)
    if not port.isdigit() or not path.startswith("/devtools/browser/"):
        raise ValueError("the browser's DevToolsActivePort file isn't as Chrome writes it")
    guard.closed.add(int(port))
    return f"ws://127.0.0.1:{port}{path}"


def run(browser: Any, address: str, lighthouse: Path, url: str, device: str, proxy: str,
        method: str = "devtools") -> dict[str, Any]:
    """One Lighthouse run of url on `device` with `method` throttling, in a new context of `browser` whose traffic
    goes through `proxy` (net.GuardProxy's address). Returns the report (LHR); raises Failed when there's none."""
    if method not in METHODS or device not in ("mobile", "desktop"):
        raise ValueError(f"no Lighthouse run for {device} with {method} throttling")
    context = browser.new_context(service_workers="block", accept_downloads=False, proxy={"server": proxy})
    marker = f"about:blank#openppc-{secrets.token_hex(8)}"
    try:
        context.new_page().goto(marker)
        with as_file(files(__package__) / ATTACH) as script:
            done = subprocess.run([node(), str(script), str(lighthouse), address, marker, url, device, method],
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=RUN_S, check=False)
    except subprocess.TimeoutExpired as e:
        raise Failed(f"Lighthouse ran past {RUN_S} seconds") from e
    finally:
        context.close()
    if done.returncode:
        said = [line.strip() for line in done.stderr.splitlines() if line.strip()]
        raise Failed(f"Lighthouse stopped: {said[-1][:300] if said else f'exit code {done.returncode}'}")
    try:
        lhr = json.loads(done.stdout)
    except ValueError as e:
        raise Failed("Lighthouse's output isn't a report") from e
    if not isinstance(lhr, dict):
        raise Failed("Lighthouse's output isn't a report")
    return lhr


def measured(lhr: dict[str, Any]) -> dict[str, float | None]:
    """The report's lab metrics, named as lab.metrics.measure names them, from its metrics audit (the load as
    measured with devtools throttling, or as simulated)."""
    try:
        items = lhr["audits"]["metrics"]["details"]["items"]
        values = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
    except (KeyError, TypeError):
        values = {}
    return {k: float(v) if isinstance(v := values.get(name), (int, float)) and not isinstance(v, bool) else None
            for k, name in METRICS.items()}

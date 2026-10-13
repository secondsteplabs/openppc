"""The browser pass (`openppc-online site --render`): a real browser loads a few pages to see what only JavaScript
shows, namely which tags fire before and after consent, the accessibility problems axe-core finds, and lab Web
Vitals on a simulated phone. The checks and the report read what it observes; without --render a scan has no
Rendered, and its browser checks say so.

The browser reaches the network only through net.GuardProxy, so a rendered page is held to the same rules as the
crawler: no private, link-local or metadata addresses unless --allow-private opens the private ones.
"""
import contextlib
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .crawl import Crawl
from .net import Guard, GuardProxy
from .tags import CONSENT, consent_platform_of, events_of, vendor_of

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:  # the `render` extra isn't installed; render() and preflight() say how to install it
    sync_playwright = None  # type: ignore[assignment]
    PlaywrightError = Exception  # type: ignore[assignment,misc]

RENDER_PAGES = 5             # pages rendered: the home page, then one per top-level section
SETTLE_MS = 3000             # wait after load, and after the consent click, for late tags
LOAD_MS = 30_000
VITALS_RUNS = 3              # the median of this many loads is reported
VITALS_PAGES = 1             # pages measured, from the first rendered (the home page) on
VITALS_SETTLE_MS = 5000
# Lighthouse's mobile profile: a mid-range phone on a slow 4G connection
VIEWPORT = {"width": 412, "height": 823}
PHONE: dict[str, Any] = {"viewport": VIEWPORT, "device_scale_factor": 2.625, "is_mobile": True, "has_touch": True}
CPU_SLOWDOWN = 4
RTT_MS = 150
DOWN_KBPS = 1638.4
UP_KBPS = 750
PROFILE = (f"lab, simulated phone ({VIEWPORT['width']}x{VIEWPORT['height']}), "
           f"{CPU_SLOWDOWN}x slower CPU, {RTT_MS} ms round trips, {DOWN_KBPS / 1024:.1f} Mbps down")
AXE_TAGS = ("wcag2a", "wcag2aa", "wcag21a", "wcag21aa")
AXE_VERSION = "4.10.3"
METRICS = ("lcp", "cls", "tbt", "fcp", "ttfb")
RENDER_FLAG = "`--render`"  # what a check that needs the browser asks for
INSTALL = ('--render needs Playwright and Chromium: pip install "openppc-online[render]", '
           "then playwright install chromium")

AXE_RUN = """async (tags) => {
  const r = await axe.run(document, {runOnly: {type: 'tag', values: tags}, resultTypes: ['violations']});
  return r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help, url: v.helpUrl, nodes: v.nodes.length,
                                 targets: v.nodes.slice(0, 5).map(n => String(n.target[0] ?? '')),
                                 criteria: v.tags.filter(t => /^wcag\\d{3,}$/.test(t))
                                                 .map(t => `${t[4]}.${t[5]}.${t.slice(6)}`)}));
}"""
# events the site pushed to the GTM dataLayer, without GTM's own gtm.* events
DATALAYER = ("(window.dataLayer || []).filter(e => e && typeof e.event === 'string' && !e.event.startsWith('gtm.'))"
             ".map(e => e.event.slice(0, 100))")
SIGNALS = """() => ({
  tcf: typeof window.__tcfapi === 'function',
  consent: (window.dataLayer || []).filter(e => e && e[0] === 'consent').map(e => String(e[1])),
  links: Array.from(document.querySelectorAll('a[href], area[href]'), a => a.href),
  datalayer: DATALAYER,
})""".replace("DATALAYER", DATALAYER)
BODY_CHARS = 16_384          # of a tag hit's POST body, read for the events batched in it
HEAVY_FILES = 5              # the largest files listed under a Web Vitals measurement
DETAILS = ("lcp_element", "lcp_url", "blocking", "heavy")
# LCP, CLS by session windows (as Chrome counts it), and Total Blocking Time from FCP on; INP needs a real visitor's
# clicks, so a lab run can't measure it
VITALS_JS = """(() => {
  const v = {lcp: null, cls: 0, tbt: null, fcp: null, ttfb: null};
  const tasks = [];
  let win = 0, first = 0, last = 0, lcpEl = null;
  const watch = (type, cb) => {
    try { new PerformanceObserver(l => l.getEntries().forEach(cb)).observe({type, buffered: true}); } catch (e) {}
  };
  watch('largest-contentful-paint', e => { v.lcp = e.startTime; lcpEl = e.element; v.lcp_url = e.url || ''; });
  watch('paint', e => { if (e.name === 'first-contentful-paint') v.fcp = e.startTime; });
  watch('longtask', e => tasks.push([e.startTime, e.duration]));
  watch('layout-shift', e => {
    if (e.hadRecentInput) return;
    if (win && e.startTime - last < 1000 && e.startTime - first < 5000) { win += e.value; }
    else { win = e.value; first = e.startTime; }
    last = e.startTime;
    v.cls = Math.max(v.cls, win);
  });
  window.__openppcVitals = () => {
    const nav = performance.getEntriesByType('navigation')[0];
    v.ttfb = nav ? nav.responseStart : null;
    if (v.fcp !== null) v.tbt = tasks.filter(([s]) => s >= v.fcp).reduce((t, [, d]) => t + Math.max(0, d - 50), 0);
    const cls = lcpEl && typeof lcpEl.className === 'string' ? lcpEl.className.trim().split(/\\s+/).slice(0, 2) : [];
    v.lcp_element = lcpEl ? lcpEl.tagName.toLowerCase() + (lcpEl.id ? '#' + lcpEl.id : '')
                            + cls.filter(Boolean).map(c => '.' + c).join('') : '';
    v.lcp_url = v.lcp_url || '';
    const files = performance.getEntriesByType('resource');
    v.blocking = files.filter(f => f.renderBlockingStatus === 'blocking').map(f => f.name);
    v.heavy = files.filter(f => f.transferSize > 0).sort((a, b) => b.transferSize - a.transferSize)
                   .slice(0, HEAVY_FILES).map(f => [f.name, f.transferSize]);
    return v;
  };
})();""".replace("HEAVY_FILES", str(HEAVY_FILES))

Progress = Callable[[str], object]


@dataclass
class Observation:
    url: str
    error: str = ""
    before: list[str] = field(default_factory=list)   # requests before any consent
    after: list[str] = field(default_factory=list)    # requests after accepting, and a reload
    consent: str = ""          # the consent platform recognised, or ""
    accepted: bool = False     # its accept button was clicked
    selector: str = ""         # the button clicked
    tcf: bool = False          # the IAB TCF API (__tcfapi) is on the page
    consent_mode: list[str] = field(default_factory=list)  # gtag('consent', ...) commands seen
    axe: list[dict[str, Any]] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # every link in the rendered page, absolute
    screenshot: str = ""       # where --screenshots saved the page as first loaded
    events: dict[str, list[str]] = field(default_factory=dict)  # tag: the events its hits sent
    datalayer: list[str] = field(default_factory=list)          # events pushed to the dataLayer


@dataclass
class Vitals:
    url: str
    runs: list[dict[str, float | None]] = field(default_factory=list)
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)  # from the first run: DETAILS

    @property
    def median(self) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for k in METRICS:
            values = [v for r in self.runs if (v := r.get(k)) is not None]
            out[k] = float(statistics.median(values)) if values else None
        return out


@dataclass
class Rendered:
    pages: list[Observation] = field(default_factory=list)
    vitals: list[Vitals] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)  # hosts the browser was stopped from reaching


def pick(c: Crawl, n: int = RENDER_PAGES) -> list[str]:
    """The home page, then the first page found in each top-level section."""
    sections: set[str] = set()
    out = []
    for p in c.html_pages():
        section = urlsplit(p.url).path.strip("/").split("/")[0]
        if section not in sections:
            sections.add(section)
            out.append(p.url)
    return out[:n]


@cache
def axe_source() -> str:
    return (files("openppc_online.siteaudit") / "vendor" / "axe.min.js").read_text(encoding="utf-8")


def _http(url: str) -> bool:
    return url.startswith(("http://", "https://"))


def _accept_button(page: Any, selectors: list[str]) -> tuple[Any, str] | None:
    for frame in page.frames:
        for selector in selectors:
            try:
                el = frame.query_selector(selector)
                if el and el.is_visible():
                    return el, selector
            except PlaywrightError:
                continue
    return None


def _events(requests: list[str], bodies: dict[int, str]) -> dict[str, list[str]]:
    """Each tag that sent a hit: the distinct events, in the order they were first sent."""
    out: dict[str, list[str]] = {}
    for i, url in enumerate(requests):
        found = events_of(url, bodies.get(i, ""))
        if found:
            seen = out.setdefault(found[0], [])
            for name in found[1]:
                if name not in seen:
                    seen.append(name)
    return out


def _unique(names: list[str]) -> list[str]:
    return list(dict.fromkeys(names))


def _observe(browser: Any, url: str, consent_selector: str, screenshot: str = "") -> Observation:
    o = Observation(url)
    context = browser.new_context(service_workers="block", accept_downloads=False)
    requests: list[str] = []
    bodies: dict[int, str] = {}

    def seen(req: Any) -> None:
        if not _http(req.url):
            return
        if req.method == "POST" and (hit := vendor_of(req.url)) and hit[1] == "hit":
            with contextlib.suppress(PlaywrightError, UnicodeDecodeError, ValueError):  # a binary body has no events
                bodies[len(requests)] = (req.post_data or "")[:BODY_CHARS]
        requests.append(req.url)

    try:
        page = context.new_page()
        page.on("request", seen)
        page.goto(url, wait_until="load", timeout=LOAD_MS)
        page.wait_for_timeout(SETTLE_MS)
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(SETTLE_MS // 2)
        signals = page.evaluate(SIGNALS)
        o.tcf, o.consent_mode = bool(signals["tcf"]), list(signals["consent"])
        o.links = [x for x in signals["links"] if _http(x)]
        o.datalayer = _unique(list(signals["datalayer"]))
        if screenshot:
            page.evaluate("() => window.scrollTo(0, 0)")
            page.screenshot(path=screenshot)
            o.screenshot = screenshot
        # Runtime.evaluate, not a <script> tag, so the page's Content-Security-Policy can't block axe
        context.new_cdp_session(page).send("Runtime.evaluate", {"expression": axe_source()})
        o.axe = page.evaluate(AXE_RUN, list(AXE_TAGS))
        o.before = list(requests)

        o.consent = next((cid for cid in map(consent_platform_of, o.before) if cid), "")
        selectors = [consent_selector] if consent_selector else [
            c["accept"] for cid, c in CONSENT.items() if c["accept"] and (not o.consent or cid == o.consent)]
        found = _accept_button(page, selectors)
        if found:
            el, o.selector = found
            o.consent = o.consent or next((cid for cid, c in CONSENT.items() if c["accept"] == o.selector), "custom")
            mark = len(requests)
            el.click(timeout=5000)
            o.accepted = True
            page.wait_for_timeout(SETTLE_MS)
            page.reload(wait_until="load", timeout=LOAD_MS)
            page.wait_for_timeout(SETTLE_MS)
            o.after = requests[mark:]
            o.datalayer = _unique(o.datalayer + list(page.evaluate(f"() => {DATALAYER}")))
    except PlaywrightError as e:
        o.error = str(e).splitlines()[0]
        o.before = o.before or list(requests)
    finally:
        context.close()
    o.events = _events(requests, bodies)
    return o


def _vitals_run(browser: Any, url: str) -> dict[str, Any]:
    context = browser.new_context(service_workers="block", accept_downloads=False, **PHONE)
    try:
        page = context.new_page()
        page.add_init_script(VITALS_JS)
        cdp = context.new_cdp_session(page)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": CPU_SLOWDOWN})
        cdp.send("Network.enable")
        cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": RTT_MS,
                                                      "downloadThroughput": DOWN_KBPS * 1024 / 8,
                                                      "uploadThroughput": UP_KBPS * 1024 / 8})
        page.goto(url, wait_until="load", timeout=LOAD_MS * 2)
        page.wait_for_timeout(VITALS_SETTLE_MS)
        return dict(page.evaluate("() => window.__openppcVitals()"))
    finally:
        context.close()


def installed() -> bool:
    """Whether the `render` extra is here (Chromium itself is checked by preflight)."""
    return sync_playwright is not None


def preflight() -> None:
    """Fails before a long crawl, not after it, when the browser can't start."""
    if sync_playwright is None:
        raise ValueError(INSTALL)
    with sync_playwright() as pw:
        try:
            pw.chromium.launch().close()
        except PlaywrightError as e:
            raise ValueError(f"{INSTALL} ({str(e).splitlines()[0]})") from e


def _shot_name(folder: str, n: int, url: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in urlsplit(url).path.strip("/"))[:60] or "home"
    return str(Path(folder) / f"{n:02d}-{slug}.png")


def render(c: Crawl, guard: Guard, pages: int = RENDER_PAGES, consent_selector: str = "",
           vitals: int = VITALS_PAGES, progress: Progress | None = None, screenshots: str = "",
           also: list[str] | None = None) -> Rendered:
    """Renders `pages` pages, then the `also` pages (a thank-you page no link leads to), and measures Web Vitals on
    the first `vitals` of them."""
    if sync_playwright is None:
        raise ValueError(INSTALL)
    targets = pick(c, pages)
    targets += [u for u in _unique(also or []) if u not in targets]
    if screenshots:
        Path(screenshots).mkdir(parents=True, exist_ok=True)
    out = Rendered()
    already = len(guard.refused)
    with GuardProxy(guard) as proxy, sync_playwright() as pw:
        try:
            # Playwright routes loopback through the proxy too, so localhost gets the same check
            browser = pw.chromium.launch(proxy={"server": proxy.url}, args=[
                "--disable-quic", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"])
        except PlaywrightError as e:
            raise ValueError(f"{INSTALL} ({str(e).splitlines()[0]})") from e
        try:
            for n, url in enumerate(targets, 1):
                if progress:
                    progress(f"rendering {n} of {len(targets)}: {url}")
                out.pages.append(_observe(browser, url, consent_selector,
                                          _shot_name(screenshots, n, url) if screenshots else ""))
            for url in targets[:vitals]:
                v = Vitals(url)
                out.vitals.append(v)
                for n in range(VITALS_RUNS):
                    if progress:
                        progress(f"measuring Web Vitals on {url}, run {n + 1} of {VITALS_RUNS}")
                    try:
                        run = _vitals_run(browser, url)
                    except PlaywrightError as e:
                        v.error = str(e).splitlines()[0]
                        break  # a page that fails once fails again, a minute each
                    details = {k: run.pop(k, None) for k in DETAILS}
                    v.details = v.details or details
                    v.runs.append(run)
        finally:
            browser.close()
    out.refused = sorted(set(guard.refused[already:]))
    return out

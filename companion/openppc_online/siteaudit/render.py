"""The browser pass (`openppc-online site --render`): a real browser loads a few pages to see what only JavaScript
shows, namely which tags fire before and after consent, the accessibility problems axe-core finds, and lab Web
Vitals on a throttled phone, set up as Lighthouse sets up its own (lab.throttle) and measured from a trace as
Lighthouse measures it (lab.capture, lab.metrics). The checks and the report read what it observes; without --render a
scan has no Rendered, and its browser checks say so.

Each page's traffic goes through net.GuardProxy (set per browser context), so a rendered page is held to the same
rules as the crawler: no private, link-local or metadata addresses unless --allow-private opens the private ones. The
browser's own traffic (update checks, sign-in, push) goes to net.Sink, which refuses it before resolving any name, and
the calls to Google each context makes itself are turned off or sent to a name the guard refuses unresolved.
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
from .lab import metrics
from .lab.capture import benchmark, capture
from .lab.score import performance
from .lab.throttle import DESKTOP, MOBILE
from .net import Guard, GuardProxy, Sink
from .tags import CONSENT, consent_platform_of, events_of, vendor_of

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright
except ImportError:  # the `render` extra isn't installed; render() and preflight() say how to install it
    sync_playwright = None  # type: ignore[assignment]
    PlaywrightError = PlaywrightTimeout = Exception  # type: ignore[assignment,misc]

RENDER_PAGES = 5             # pages rendered: the home page, then one per top-level section
SETTLE_MS = 3000             # wait after load, and after the consent click, for late tags
LOAD_MS = 30_000
VITALS_RUNS = 3              # loads of the first measured page per device; the others get one each
MAX_RUNS = 9
VITALS_PAGES = 1             # pages measured, from the first rendered (the home page) on
PROFILE = f"lab, {MOBILE.label}"
# Speed loads answer the page's tag hits themselves (204), so the page sends no visits to its analytics or ad accounts
# (another site's frame and workers are other targets, not caught); the tag and consent load stays real. The owner's
# open question 1 (SITE_AUDIT_PARITY_PLAN.md) may turn it off.
BLOCK_HITS = True
AXE_TAGS = ("wcag2a", "wcag2aa", "wcag21a", "wcag21aa")
AXE_VERSION = "4.10.3"
METRICS = ("lcp", "cls", "tbt", "fcp", "ttfb", "si")
SCORED = {"fcp": "first-contentful-paint", "si": "speed-index", "lcp": "largest-contentful-paint",
          "tbt": "total-blocking-time", "cls": "cumulative-layout-shift"}
RENDER_FLAG = "`--render`"  # what a check that needs the browser asks for
# Each browser context calls Google itself, through the page's proxy: an AI Mode check, sent to Chrome's Google base
# URL, here a name the guard refuses before resolving it, and a preconnect to the default search engine, turned off
GOOGLE_BASE = "http://google.invalid/"
FEATURES_OFF = ("PreconnectToSearch",)
_playwright_features: list[str] = []
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
    runs: list[dict[str, float | None]] = field(default_factory=list)  # lab.metrics.measure, one per load
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)  # the representative load's (lab.capture.DETAILS_JS)
    capped: int = 0            # loads still going, or not yet quiet, at the load cap, measured as they were then
    hits_answered: int = 0     # tag hits the speed loads answered themselves (BLOCK_HITS)
    device: str = "mobile"     # the lab.throttle profile's

    @property
    def median(self) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for k in METRICS:
            values = [v for r in self.runs if (v := r.get(k)) is not None]
            out[k] = float(statistics.median(values)) if values else None
        return out

    @property
    def rep(self) -> int | None:
        """The representative load (Lighthouse CI's median run)."""
        return metrics.representative(self.runs)

    @property
    def shown(self) -> dict[str, float | None]:
        """The representative load's metrics: what the report shows and the checks judge."""
        i = self.rep
        return {k: None for k in METRICS} if i is None else {k: self.runs[i].get(k) for k in METRICS}

    @property
    def spread(self) -> dict[str, tuple[float, float]]:
        return metrics.spread(self.runs)

    @property
    def unstable(self) -> list[str]:
        return metrics.unstable(self.runs)

    @property
    def no_tti(self) -> int:
        """Loads that never went quiet for Time to Interactive's 5 s window: their TBT runs to the end of the load."""
        return sum(1 for r in self.runs if r.get("fcp") is not None and r.get("tti") is None)

    @property
    def score(self) -> int | None:
        """Lighthouse's speed score formula on the representative load (lab.score.LAB_SCORE)."""
        shown = self.shown
        values = {name: shown.get(key) for key, name in SCORED.items()}
        if any(v is None for v in values.values()):
            return None
        return performance({name: float(v) for name, v in values.items() if v is not None}, self.device)


@dataclass
class Rendered:
    pages: list[Observation] = field(default_factory=list)
    vitals: list[Vitals] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)  # hosts the browser was stopped from reaching
    browser_calls: list[str] = field(default_factory=list)  # hosts the browser itself asked for, refused (net.Sink)
    benchmark: float | None = None  # this computer's Lighthouse BenchmarkIndex, before the speed loads


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


def _observe(browser: Any, url: str, consent_selector: str, screenshot: str = "", proxy: str = "") -> Observation:
    o = Observation(url)
    context = browser.new_context(service_workers="block", accept_downloads=False,
                                  **({"proxy": {"server": proxy}} if proxy else {}))
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


def installed() -> bool:
    """Whether the `render` extra is here (Chromium itself is checked by preflight)."""
    return sync_playwright is not None


def preflight() -> None:
    """Fails before a long crawl, not after it, when the browser can't start."""
    if sync_playwright is None:
        raise ValueError(INSTALL)
    with Sink() as sink, sync_playwright() as pw:
        try:
            _launch(pw, sink.url).close()
        except PlaywrightError as e:
            raise ValueError(f"{INSTALL} ({str(e).splitlines()[0]})") from e


def _launch(pw: Any, sink: str) -> Any:
    """New headless, which paints as a visitor's Chrome does (the headless shell skips most screenshots a trace needs
    for Speed Index). Its own update, sign-in and push calls go to the sink; each context brings its page's proxy.
    Playwright routes loopback through the proxies too, so localhost gets the same check."""
    args = ["--disable-quic", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            f"--google-base-url={GOOGLE_BASE}"]
    if not _playwright_features:
        _playwright_features.extend(_features_off(pw, sink, args))
    off = ",".join(dict.fromkeys([*_playwright_features, *FEATURES_OFF]))
    return pw.chromium.launch(channel="chromium", proxy={"server": sink}, args=[*args, f"--disable-features={off}"])


def _features_off(pw: Any, sink: str, args: list[str]) -> list[str]:
    """The features Playwright turns off. Chrome reads only the last --disable-features, so turning one more off means
    repeating Playwright's, read from the browser's own chrome://version page."""
    browser = pw.chromium.launch(channel="chromium", proxy={"server": sink}, args=args)
    try:
        page = browser.new_page()
        page.goto("chrome://version")
        line = page.locator("#command_line").inner_text()
    finally:
        browser.close()
    return [f for a in line.split() if a.startswith("--disable-features=") for f in a.split("=", 1)[1].split(",") if f]


def _shot_name(folder: str, n: int, url: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in urlsplit(url).path.strip("/"))[:60] or "home"
    return str(Path(folder) / f"{n:02d}-{slug}.png")


def _measure(browser: Any, v: Vitals, runs: int, proxy: str, progress: Progress | None) -> None:
    """`runs` loads of v.url, one after another (loads side by side would share the CPU and corrupt TBT)."""
    profile = DESKTOP if v.device == "desktop" else MOBILE
    details: list[dict[str, Any]] = []
    for n in range(runs):
        if progress:
            progress(f"measuring Web Vitals ({v.device}) on {v.url}, load {n + 1} of {runs}")
        try:
            run = capture(browser, v.url, profile, proxy, BLOCK_HITS)
            measured = metrics.measure(run.events, run.trace_end, run.frames)
        except PlaywrightError as e:
            v.error = str(e).splitlines()[0]
            break  # a page that fails once fails again, a minute each
        except metrics.NoNavigation as e:
            v.error = str(e)
            break
        v.capped += run.capped
        v.hits_answered += run.hits_answered
        details.append(run.details)
        v.runs.append(measured)
    if (i := v.rep) is not None and i < len(details):
        v.details = details[i]


def render(c: Crawl, guard: Guard, pages: int = RENDER_PAGES, consent_selector: str = "",
           vitals: int = VITALS_PAGES, progress: Progress | None = None, screenshots: str = "",
           also: list[str] | None = None, desktop: bool = False, measured: set[str] | None = None,
           runs: int = VITALS_RUNS) -> Rendered:
    """Renders `pages` pages, then the `also` pages (a thank-you page no link leads to), and measures Web Vitals on
    the first `vitals` of them that aren't `measured` already (by PageSpeed Insights): on a phone, then with
    `desktop` on a desktop too. The first page measured gets `runs` loads per device, the others one each."""
    if sync_playwright is None:
        raise ValueError(INSTALL)
    targets = pick(c, pages)
    targets += [u for u in _unique(also or []) if u not in targets]
    if screenshots:
        Path(screenshots).mkdir(parents=True, exist_ok=True)
    out = Rendered()
    already = len(guard.refused)
    with GuardProxy(guard) as proxy, Sink() as sink, sync_playwright() as pw:
        try:
            browser = _launch(pw, sink.url)
        except PlaywrightError as e:
            raise ValueError(f"{INSTALL} ({str(e).splitlines()[0]})") from e
        try:
            for n, url in enumerate(targets, 1):
                if progress:
                    progress(f"rendering {n} of {len(targets)}: {url}")
                out.pages.append(_observe(browser, url, consent_selector,
                                          _shot_name(screenshots, n, url) if screenshots else "", proxy.url))
            profiles = (MOBILE, DESKTOP) if desktop else (MOBILE,)
            pending = [u for u in targets[:vitals] if u not in (measured or set())]
            if pending:
                out.benchmark = benchmark(browser)
            for i, url in enumerate(pending):
                for profile in profiles:
                    v = Vitals(url, device=profile.device)
                    out.vitals.append(v)
                    _measure(browser, v, runs if i == 0 else 1, proxy.url, progress)
        finally:
            browser.close()
        out.browser_calls = sink.asked
    out.refused = sorted(set(guard.refused[already:]))
    return out

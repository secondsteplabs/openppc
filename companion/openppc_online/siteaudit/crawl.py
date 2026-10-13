"""The crawler: the start URL, then the sitemap's URLs, then links breadth-first, on the start page's
own host, politely, with nothing fetched that robots.txt disallows.

There is no page limit unless you set one. What makes an uncapped crawl finish is the URL clean-up
(fragments and tracking parameters dropped, query keys sorted) and the per-pattern caps: endless
calendars, filters and sort orders would otherwise never run out of new URLs. Every URL a cap skips
is counted by pattern and listed in the report.
"""
import re
import threading
import time
import xml.etree.ElementTree as ET
import zlib
from collections import Counter, defaultdict, deque
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, as_completed, wait
from dataclasses import dataclass, field
from itertools import zip_longest
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import page as html
from .net import HTML_TYPES, PAGE_BYTES, ROBOTS_TOKEN, Guard, Response, encoded, fetch

MAX_PER_PATTERN = 500        # URLs queued per path pattern (/product/*); 0 lifts the cap
MAX_QUERY_VARIANTS = 10      # URLs queued per path that differ only in their query string
POLITE_WORKERS = 2
POLITE_INTERVAL = 0.5        # seconds between requests to the site, unless --fast
FAST_WORKERS = 8
CRAWL_DELAY_MAX = 10.0       # a robots.txt Crawl-delay is honoured up to this many seconds
RETRY_AFTER_MAX = 30.0       # a 429 or 503 is retried once, after Retry-After up to this
ROBOTS_BYTES = 512_000       # Google reads the first 500 KiB of robots.txt
SITEMAP_BYTES = 50_000_000   # the sitemap protocol's limit for one file, uncompressed
SITEMAP_FILES = 50           # sitemap files read, an index's children included
EXTERNAL_BYTES = 65_536      # read from an external link that has to be checked with GET
LLMS_BYTES = 4_096           # enough of /llms.txt to tell a text file from a page that says "not found"
PROBE_PREFIX = "/openppc-missing-page"
PROBE = PROBE_PREFIX + "-0d1f4a"  # the same every run, so a soft-404 finding keeps its fingerprint
TRACKING_PARAMS = ("utm_", "gclid", "gbraid", "wbraid", "dclid", "fbclid", "msclkid", "mc_cid", "mc_eid",
                   "_ga", "_gl", "yclid", "igshid", "ttclid", "twclid", "li_fat_id", "srsltid")
AI_BOTS = ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User",
           "PerplexityBot", "Perplexity-User", "Google-Extended", "Applebot-Extended", "CCBot", "Bytespider",
           "Amazonbot", "meta-externalagent")

SCHEME = re.compile(r"\s*[a-z][a-z0-9+.-]*:(?!\d)", re.I)  # a scheme, not host:port

Progress = Callable[[str], object]  # raising KeyboardInterrupt stops the run, as Ctrl-C does


def stopped(e: KeyboardInterrupt) -> str:
    """How the run was cut short: the words the interrupt carries (the app's Stop button), else Ctrl-C."""
    return str(e) or "stopped with Ctrl-C"


def normalize(url: str) -> str:
    """One spelling per page: lower-case scheme and host, no default port, no fragment, no user
    name or password, no tracking parameters, query keys sorted."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"not an http(s) address: {url}")
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    netloc = host if port is None or (scheme, port) in (("http", 80), ("https", 443)) else f"{host}:{port}"
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                             if not k.lower().startswith(TRACKING_PARAMS)))
    return urlunsplit((scheme, netloc, encoded(parts.path or "/"), query, ""))


def pattern(url: str) -> str:
    """The template a URL probably comes from: /product/blue-shirt -> /product/*."""
    parts = urlsplit(url)
    segments = [s for s in parts.path.split("/") if s]
    shape = "/" + "/".join(segments[:1] + ["*"] * (len(segments) - 1))
    return shape + ("?" if parts.query else "")


def host_of(url: str) -> str:
    return urlsplit(url).netloc.lower()


def bot_wall(resp: Response) -> str:
    """The bot protection that answered instead of the page, or ""."""
    h, body = resp.headers, resp.body[:20_000].lower()
    server = h.get("server", "").lower()
    challenge = b"challenge" in body or b"just a moment" in body
    if h.get("cf-mitigated") == "challenge" or (resp.status in (403, 503) and "cloudflare" in server and challenge):
        return "Cloudflare"
    if "x-datadome" in h or b"captcha-delivery.com" in body:
        return "DataDome"
    if b"px-captcha" in body or b"perimeterx" in body:
        return "HUMAN (PerimeterX)"
    if resp.status == 403 and "akamaighost" in server:
        return "Akamai"
    if b"sucuri website firewall" in body:
        return "Sucuri"
    if resp.status in (403, 429, 503) and b"captcha" in body:
        return "a CAPTCHA"
    return ""


class Robots:
    """robots.txt read as RFC 9309 says: the group naming the crawler, or else `*`; the longest
    matching rule wins and Allow wins a tie; `*` matches anything and `$` ends a path."""

    def __init__(self, text: str):
        self.groups: dict[str, list[tuple[bool, int, re.Pattern[str]]]] = {}
        self.delays: dict[str, float] = {}
        self.sitemaps: list[str] = []
        agents: list[str] = []
        in_rules = False
        for line in text.splitlines():
            key, _, value = line.split("#", 1)[0].partition(":")
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if in_rules:
                    agents, in_rules = [], False
                agents.append(value.split("/")[0].strip().lower())  # Googlebot/2.1 names Googlebot
                self.groups.setdefault(agents[-1], [])
            elif key in ("allow", "disallow", "crawl-delay"):
                in_rules = True
                if key == "crawl-delay":
                    try:
                        delay = float(value)
                    except ValueError:
                        continue
                    for a in agents:
                        self.delays.setdefault(a, delay)
                elif value:  # an empty Disallow allows everything
                    path = encoded(value)
                    rule = re.compile(".*".join(map(re.escape, path.rstrip("$").split("*")))
                                      + ("$" if path.endswith("$") else ""))
                    for a in agents:
                        self.groups[a].append((key == "allow", len(path), rule))
            elif key == "sitemap" and value:
                self.sitemaps.append(value)

    def _agent(self, agent: str) -> str:
        return agent.lower() if agent.lower() in self.groups else "*"

    def can_fetch(self, agent: str, url: str) -> bool:
        parts = urlsplit(url)
        if parts.path == "/robots.txt":
            return True
        target = encoded(parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        best, allow = -1, True
        for is_allow, length, rule in self.groups.get(self._agent(agent), []):
            if (length > best or (length == best and is_allow)) and rule.match(target):
                best, allow = length, is_allow
        return allow

    def crawl_delay(self, agent: str) -> float | None:
        return self.delays.get(self._agent(agent))

    def site_maps(self) -> list[str]:
        return self.sitemaps


@dataclass
class Page:
    url: str
    depth: int
    resp: Response
    info: html.PageInfo | None = None   # set for an HTML page on the site's host
    blocked_by: str = ""

    @property
    def status(self) -> int:
        return self.resp.status


@dataclass
class Crawl:
    start: str
    origin: str                 # scheme://host after the start page's redirects; the crawl stays on it
    allow_private: bool
    pages: dict[str, Page] = field(default_factory=dict)      # in crawl order
    referrer: dict[str, str] = field(default_factory=dict)    # a URL -> the first page that linked to it
    external: dict[str, Response] = field(default_factory=dict)
    robots: Response | None = None
    rules: Robots | None = None
    robots_blocked: set[str] = field(default_factory=set)
    sitemap_files: list[str] = field(default_factory=list)
    sitemap_urls: set[str] = field(default_factory=set)
    sitemap_errors: list[str] = field(default_factory=list)
    skipped: Counter[str] = field(default_factory=Counter)    # pattern -> URLs a cap left out
    probe: Response | None = None        # a made-up URL, to see how the site answers a missing page
    plain_http: Response | None = None   # the home page over http://, to see whether it moves to https
    llms_txt: bool = False
    blocked_by: str = ""
    incomplete: str = ""                 # why the crawl stopped early, or ""
    seconds: float = 0.0

    def allowed(self, url: str, agent: str = ROBOTS_TOKEN) -> bool:
        return self.rules is None or self.rules.can_fetch(agent, url)

    @property
    def robots_failed(self) -> bool:
        """robots.txt answered with a server error or 429, or not at all: RFC 9309 says crawl nothing."""
        return self.robots is not None and (self.robots.status in (0, 429) or self.robots.status >= 500)

    def html_pages(self) -> list[Page]:
        return [p for p in self.pages.values() if p.info is not None and p.status == 200 and not p.blocked_by]


class _Limiter:
    """Spaces request starts to the site at least `interval` seconds apart, across workers."""

    def __init__(self, interval: float):
        self.interval = interval
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.interval
        if delay > 0:
            time.sleep(delay)


def _get(url: str, guard: Guard, limiter: _Limiter, method: str = "GET", max_bytes: int = PAGE_BYTES,
         html_only: bool = False) -> Response:
    limiter.wait()
    resp = fetch(url, guard, method, max_bytes, html_only=html_only)
    if resp.status in (429, 503):
        try:
            pause = float(resp.headers.get("retry-after", "5"))
        except ValueError:
            pause = 5.0
        time.sleep(min(max(pause, 0.0), RETRY_AFTER_MAX))
        resp = fetch(url, guard, method, max_bytes, html_only=html_only)
    return resp


def _inflate(body: bytes) -> bytes:
    if body[:2] != b"\x1f\x8b":
        return body
    inflate = zlib.decompressobj(47)
    return inflate.decompress(body, SITEMAP_BYTES)


def _sitemap_locs(body: bytes) -> tuple[bool, list[str]]:
    """(is an index, its <loc> values). A document type declaration is refused, which rules out
    entity-expansion bombs."""
    data = _inflate(body)
    if b"<!DOCTYPE" in data[:4096].upper() or b"<!ENTITY" in data.upper():
        raise ValueError("a sitemap with a document type declaration is not read")
    root = ET.fromstring(data)
    locs = [(el.text or "").strip() for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "loc"]
    return root.tag.rsplit("}", 1)[-1] == "sitemapindex", [x for x in locs if x]


class _Crawler:
    def __init__(self, c: Crawl, guard: Guard, limiter: _Limiter, max_per_pattern: int):
        self.c, self.guard, self.limiter, self.max_per_pattern = c, guard, limiter, max_per_pattern
        self.queue: deque[tuple[str, int]] = deque()
        self.seen: set[str] = set()
        self.per_pattern: Counter[str] = Counter()
        self.per_path: Counter[str] = Counter()
        self.host = host_of(c.origin)

    def internal(self, url: str) -> bool:
        return host_of(url) == self.host

    def offer(self, url: str, depth: int, referrer: str) -> None:
        """Queue a URL found on the site, unless it was seen, robots.txt disallows it, or a cap is full."""
        try:
            url = normalize(url)
        except ValueError:
            return
        if not self.internal(url):
            if referrer:
                self.c.referrer.setdefault(url, referrer)
                self.c.external.setdefault(url, Response(url, url, -1))  # -1: not checked yet
            return
        if url in self.seen:
            return
        self.seen.add(url)
        if referrer:
            self.c.referrer.setdefault(url, referrer)
        if not self.c.allowed(url):
            self.c.robots_blocked.add(url)
            return
        shape, path = pattern(url), urlsplit(url).path
        query = bool(urlsplit(url).query)
        if (self.max_per_pattern and depth > 0 and self.per_pattern[shape] >= self.max_per_pattern) or (
                query and self.per_path[path] >= MAX_QUERY_VARIANTS):
            self.c.skipped[shape] += 1
            return
        self.per_pattern[shape] += 1
        if query:
            self.per_path[path] += 1
        self.queue.append((url, depth))

    def record(self, url: str, depth: int, resp: Response) -> None:
        p = Page(url, depth, resp, blocked_by=bot_wall(resp) if resp.status else "")
        self.c.pages[url] = p
        if resp.status == 200 and not resp.hops and resp.content_type in ("text/html", "application/xhtml+xml") \
                and not p.blocked_by:
            p.info = html.read(html.decode(resp.body, resp.headers.get("content-type", "")), resp.final_url)
            for link in p.info.links:
                self.offer(link, depth + 1, url)
            if p.info.refresh:
                self.offer(p.info.refresh, depth + 1, url)
        resp.body = b""  # read; a whole-site crawl would otherwise hold every page in memory
        if resp.final_url != url:
            self.offer(resp.final_url, depth, url)  # a redirect's target is a page of its own


def _read_sitemaps(c: Crawl, guard: Guard, limiter: _Limiter, crawler: _Crawler) -> None:
    pending = [u for u in (c.rules.site_maps() or []) if u] if c.rules else []
    pending = pending or [c.origin + "/sitemap.xml"]
    seen: set[str] = set()
    while pending and len(c.sitemap_files) < SITEMAP_FILES:
        url = pending.pop(0)
        if url in seen:
            continue
        seen.add(url)
        resp = _get(url, guard, limiter, max_bytes=SITEMAP_BYTES)
        if resp.status != 200:
            c.sitemap_errors.append(f"{url}: {resp.error or resp.status}")
            continue
        try:
            index, locs = _sitemap_locs(resp.body)
        except (ET.ParseError, ValueError, zlib.error) as e:
            c.sitemap_errors.append(f"{url}: {e}")
            continue
        c.sitemap_files.append(url)
        if index:
            pending += locs
            continue
        for loc in locs:
            try:
                loc = normalize(loc)
            except ValueError:
                continue
            c.sitemap_urls.add(loc)
            crawler.offer(loc, 1, "")


def start_url(start: str) -> str:
    if not start.strip():
        raise ValueError("no address given")
    if not SCHEME.match(start):  # example.com means https://example.com; mailto:a@b.com is refused, not rewritten
        start = "https://" + start.strip()
    return normalize(start)


def _robots_rules(robots: Response) -> Robots | None:
    if robots.status != 200:
        return None
    return Robots(html.decode(robots.body, robots.headers.get("content-type", "")))


def crawl(start: str, guard: Guard, max_pages: int | None = None, max_seconds: float | None = None,
          max_per_pattern: int = MAX_PER_PATTERN, fast: bool = False, external: bool = True,
          progress: Progress | None = None) -> Crawl:
    began = time.monotonic()
    start = start_url(start)
    limiter = _Limiter(0.0 if fast else POLITE_INTERVAL)
    parts = urlsplit(start)
    origin = f"{parts.scheme}://{parts.netloc}"
    robots = _get(origin + "/robots.txt", guard, limiter, max_bytes=ROBOTS_BYTES)
    rules = _robots_rules(robots)
    if rules and not rules.can_fetch(ROBOTS_TOKEN, start):
        c = Crawl(start, origin, guard.allow_private, robots=robots, rules=rules, robots_blocked={start},
                  incomplete="didn't fetch the start page, because robots.txt disallows it for OpenPPC")
        c.seconds = time.monotonic() - began
        return c
    first = fetch(start, guard)
    if first.status == 0:
        raise ValueError(f"couldn't fetch {start}: {first.error}")
    final = urlsplit(normalize(first.final_url))
    c = Crawl(start, f"{final.scheme}://{final.netloc}", guard.allow_private)
    crawler = _Crawler(c, guard, limiter, max_per_pattern)
    crawler.seen.add(start)
    c.blocked_by = bot_wall(first)
    if c.blocked_by:
        c.pages[start] = Page(start, 0, first, blocked_by=c.blocked_by)
        c.seconds = time.monotonic() - began
        return c

    try:
        if c.origin != origin:  # the start page moved to another host or scheme, which has its own robots.txt
            robots = _get(c.origin + "/robots.txt", guard, limiter, max_bytes=ROBOTS_BYTES)
            rules = _robots_rules(robots)
        c.robots, c.rules = robots, rules
        if c.rules:
            delay = c.rules.crawl_delay(ROBOTS_TOKEN)
            if delay:
                limiter.interval = max(limiter.interval, min(delay, CRAWL_DELAY_MAX))
        crawler.record(start, 0, first)  # after robots.txt, so its rules apply to the start page's links
        if c.robots_failed:
            crawler.queue.clear()
            c.incomplete = "stopped after the first page: robots.txt couldn't be read, and until it can, " \
                           "crawlers are expected to stay out"
        else:
            _read_sitemaps(c, guard, limiter, crawler)
            if c.allowed(c.origin + PROBE):
                c.probe = _get(c.origin + PROBE, guard, limiter)
            if c.allowed(c.origin + "/llms.txt"):
                llms = _get(c.origin + "/llms.txt", guard, limiter, max_bytes=LLMS_BYTES)
                c.llms_txt = llms.status == 200 and not llms.hops and llms.content_type not in HTML_TYPES \
                    and not llms.body.lstrip()[:15].lower().startswith((b"<!doctype", b"<html"))
            if final.scheme == "https" and c.allowed(c.origin + "/"):
                c.plain_http = _get(f"http://{final.netloc}/", guard, limiter, method="HEAD")
            _crawl_pages(c, crawler, FAST_WORKERS if fast else POLITE_WORKERS, max_pages, max_seconds, began,
                         progress)
            if external:
                _check_external(c, guard, progress)
    except KeyboardInterrupt as e:
        c.incomplete = stopped(e)
        c.pages.setdefault(start, Page(start, 0, first))
    c.seconds = time.monotonic() - began
    return c


def follow(c: Crawl, guard: Guard, links: dict[str, str], max_pages: int | None = None,
           max_seconds: float | None = None, max_per_pattern: int = MAX_PER_PATTERN, fast: bool = False,
           progress: Progress | None = None) -> int:
    """Crawls on from links the browser found and the HTML didn't (link -> the page it was on), under the same rules
    and limits as the first pass. Returns the pages added."""
    limiter = _Limiter(0.0 if fast else POLITE_INTERVAL)
    delay = c.rules.crawl_delay(ROBOTS_TOKEN) if c.rules else None
    if delay:
        limiter.interval = max(limiter.interval, min(delay, CRAWL_DELAY_MAX))
    crawler = _Crawler(c, guard, limiter, max_per_pattern)
    crawler.seen |= set(c.pages) | c.robots_blocked
    crawler.per_pattern.update(pattern(u) for u in c.pages)
    before = len(c.pages)
    for url, page in links.items():
        crawler.offer(url, c.pages[page].depth + 1 if page in c.pages else 1, page)
    began = time.monotonic() - c.seconds  # --max-time counts the first pass too
    try:
        _crawl_pages(c, crawler, FAST_WORKERS if fast else POLITE_WORKERS, max_pages, max_seconds, began, progress)
    except KeyboardInterrupt as e:
        c.incomplete = c.incomplete or f"{stopped(e)}, while following links JavaScript added"
    return len(c.pages) - before


def _crawl_pages(c: Crawl, crawler: _Crawler, workers: int, max_pages: int | None, max_seconds: float | None,
                 began: float, progress: Progress | None) -> None:
    running: dict[Future[Response], tuple[str, int]] = {}
    pool = ThreadPoolExecutor(workers)
    try:
        while crawler.queue or running:
            while crawler.queue and len(running) < workers:
                if max_pages and len(c.pages) + len(running) >= max_pages:
                    c.incomplete = c.incomplete or "stopped at the `--max-pages` limit"
                    crawler.queue.clear()
                    break
                if max_seconds and time.monotonic() - began > max_seconds:
                    c.incomplete = c.incomplete or "stopped at the `--max-time` limit"
                    crawler.queue.clear()
                    break
                url, depth = crawler.queue.popleft()
                running[pool.submit(_get, url, crawler.guard, crawler.limiter, html_only=True)] = (url, depth)
            if not running:
                break
            done, _ = wait(running, timeout=1.0, return_when=FIRST_COMPLETED)
            for fut in done:
                url, depth = running.pop(fut)
                crawler.record(url, depth, fut.result())
                if progress:
                    progress(f"{len(c.pages)} pages, {len(crawler.queue)} queued: {url}")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)  # Ctrl-C doesn't wait for the queue


def _check_one(url: str, guard: Guard, limiter: _Limiter) -> Response:
    limiter.wait()
    resp = fetch(url, guard, method="HEAD")
    if resp.status in (403, 405, 501):
        limiter.wait()
        resp = fetch(url, guard, max_bytes=EXTERNAL_BYTES)  # some servers refuse HEAD but answer GET
    return resp


def _check_external(c: Crawl, guard: Guard, progress: Progress | None) -> None:
    """Many hosts at once, each one at the polite pace: one site with many links is never hammered."""
    by_host: dict[str, list[str]] = defaultdict(list)
    for url in c.external:
        by_host[host_of(url)].append(url)
    limiters = {host: _Limiter(POLITE_INTERVAL) for host in by_host}
    order = [u for row in zip_longest(*by_host.values()) for u in row if u]  # round robin across hosts
    pool = ThreadPoolExecutor(FAST_WORKERS)
    try:
        todo = {pool.submit(_check_one, url, guard, limiters[host_of(url)]): url for url in order}
        for n, fut in enumerate(as_completed(todo), 1):
            c.external[todo[fut]] = fut.result()
            if progress and n % 25 == 0:
                progress(f"checked {n} of {len(todo)} external links")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

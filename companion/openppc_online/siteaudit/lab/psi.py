"""Google PageSpeed Insights (`openppc-online site --psi`): Google loads the page on its own servers with Lighthouse
and sends back the report, so the numbers are PSI's own. The address goes to Google, never anything else; the calls go
through the same guard as every other connection, and an optional key travels in a header, never in a URL."""
import json
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode, urlsplit

from ..crux import from_psi
from ..net import Guard, Refused, fetch
from ..triage import redact
from .lhr import Speed, read

FORM_FACTORS = {"mobile": "phone", "desktop": "desktop"}  # PSI's strategy -> the Chrome UX Report's device

ENDPOINT = "https://pagespeedonline.googleapis.com/pagespeedonline/v5/runPagespeed"
KEY_ENV = "OPENPPC_PSI_KEY"
TIMEOUT = 120.0          # PSI often sends nothing for 20-60 s while Lighthouse runs
MAX_BYTES = 20_000_000
MAX_PAGES = 5
AT_ONCE = 2
DEVICES = ("mobile", "desktop")
CATEGORIES = ("performance", "accessibility", "best-practices", "seo")
SOURCE = "PageSpeed Insights"
QUOTA = ("Google's shared PageSpeed quota is used up for now: try again later, or pass your own free key with "
         f"--psi-key or {KEY_ENV}")


def key_from(flag: str | None) -> str:
    """--psi-key KEY, else OPENPPC_PSI_KEY; PSI works without one, on a shared quota."""
    return (flag or os.environ.get(KEY_ENV, "")).strip()


def check(urls: list[str], guard: Guard) -> None:
    """Refuses what PSI can't measure, before anything is sent: a secret-looking value in the address (PSI would
    get it, and stripping it would measure another page), and a page that isn't public."""
    if guard.allow_private:
        raise ValueError("--psi measures public pages only, so it can't be used with --allow-private; "
                         "use --render to measure on this computer")
    if len(urls) > MAX_PAGES:
        raise ValueError(f"--psi measures at most {MAX_PAGES} pages: the start page and up to "
                         f"{MAX_PAGES - 1} --render-url pages")
    for url in urls:
        if redact(url) != url:
            raise ValueError(f"--psi won't send {redact(url)} to Google: its address carries a secret-looking value. "
                             "Measure the page without it, or use --render")
    for host, port in dict.fromkeys(_hostport(u) for u in urls):
        try:
            Guard(resolve=guard.resolve).addresses(host, port)
        except Refused as e:
            raise ValueError(f"--psi measures public pages only, and {e}: use --render to measure it on this "
                             "computer") from None
        except OSError as e:
            raise ValueError(f"--psi measures public pages only, and {e}") from None


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _hostport(url: str) -> tuple[str, int]:
    parts = urlsplit(url)
    return parts.hostname or "", parts.port or (443 if parts.scheme == "https" else 80)


def _error(status: int, body: bytes) -> str:
    try:
        message = str(json.loads(body)["error"]["message"])
    except (ValueError, KeyError, TypeError):
        message = ""
    if status == 429:
        return QUOTA
    if status in (401, 403) or "API key" in message:
        return "the PSI key was refused"
    if message:
        return f"PageSpeed Insights couldn't measure it: {message[:300]}"
    return f"PageSpeed Insights answered {status}"


def measure_one(url: str, device: str, key: str, guard: Guard, screenshots: bool = False) -> Speed:
    query = urlencode([("url", url), ("strategy", device)] + [("category", c) for c in CATEGORIES])
    for _ in range(2):  # a dropped connection is asked once more; a refusal or a timeout (two minutes gone) isn't
        resp = fetch(f"{ENDPOINT}?{query}", guard, max_bytes=MAX_BYTES, follow=False, seconds=TIMEOUT,
                     timeout=TIMEOUT, headers={"Accept": "application/json", **({"X-Goog-Api-Key": key} if key else {})})
        if resp.status or resp.refused or resp.error == "timed out":
            break
    failed = Speed(url, device, SOURCE)
    if resp.status == 0:
        failed.error = f"couldn't reach PageSpeed Insights: {resp.error}"
    elif resp.status != 200:
        failed.error = _error(resp.status, resp.body)
    elif resp.truncated:
        failed.error = "PageSpeed Insights' answer was too large to read"
    else:
        try:
            answer = json.loads(resp.body)
            out = read(answer["lighthouseResult"], url, SOURCE, screenshots)
            out.device = device
            who = FORM_FACTORS[device]
            out.field_data = [from_psi(answer.get("loadingExperience"), url, False, who),
                         from_psi(answer.get("originLoadingExperience"), _origin(url), True, who)]
            return out
        except (ValueError, KeyError, TypeError):
            failed.error = "PageSpeed Insights' answer couldn't be read"
    if key:
        failed.error = failed.error.replace(key, "<key>")
    return failed


def measure(urls: list[str], key: str, guard: Guard, screenshots: bool = False,
            progress: Callable[[str], object] | None = None) -> list[Speed]:
    """Each page on each device, at most AT_ONCE calls at a time, in the order asked: the start page's phone first.
    progress runs on this thread, so its KeyboardInterrupt (a stop) cancels the calls not yet started."""
    jobs = [(u, d) for u in urls for d in DEVICES]
    pool = ThreadPoolExecutor(AT_ONCE)
    try:
        futures = [pool.submit(measure_one, u, d, key, guard, screenshots) for u, d in jobs]
        if progress:
            progress(f"PageSpeed Insights: {len(jobs)} loads asked for (Google takes up to a minute each)")
        for done, _ in enumerate(as_completed(futures)):
            if progress:
                progress(f"PageSpeed Insights: {done + 1} of {len(jobs)} loads done")
        return [f.result() for f in futures]
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

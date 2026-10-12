"""`openppc-online site`: crawl the website you name, check it, and write the report.

Every input is read before the crawl, so a typo fails in a second, not after an hour. The crawl, the external link
checks and the webhook all go through one siteaudit.net.Guard; the only other host is Chrome's UX Report API, and
only with --crux-key.
"""
import ipaddress
import json
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

import openppc
from openppc.formats import to_html

from . import __version__
from .siteaudit import net, packs
from .siteaudit.checks import SEVERITY_RANK, Finding, evaluate, home
from .siteaudit.crawl import Progress, crawl
from .siteaudit.crux import field_data, key_from
from .siteaudit.net import Guard
from .siteaudit.report import Extras, data, report, sarif
from .siteaudit.triage import Diff, compare, health, read_baseline, redact_text, suppress

FORMAT_VERSION = 1   # of --format json; schemas/site-report.schema.json
INCONCLUSIVE = 4     # the exit code with --fail-on when the scan was too broken to judge
LOOPBACK = ("localhost",)


@dataclass
class Result:
    origin: str
    findings: list[Finding]
    diff: Diff | None
    passed: bool
    inconclusive: str
    texts: dict[str, str]   # the report in each --format


def webhook_host(url: str) -> str:
    """The host --post-to names, once the address is known to be allowed: https, or plain http only to this
    computer. The rest of the URL stays out of every message, because webhook URLs carry their secret in the path."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme == "https" and host:
        return host
    if parts.scheme == "http" and (host in LOOPBACK or _is_loopback(host)):
        return host
    raise ValueError("--post-to needs an https:// address, or http:// to this computer (127.0.0.1)")


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def post(url: str, payload: str, guard: Guard) -> str:
    """One POST of the JSON result through the guard, no redirects followed. What happened, naming the host only;
    a failure doesn't change the exit code."""
    host = webhook_host(url)
    try:
        status = net.post(url, guard, payload.encode(), "application/json")
    except (OSError, ValueError) as e:
        return f"couldn't post the result to {host}: {str(e).replace(url, host) or type(e).__name__}"
    if not 200 <= status < 300:
        return f"couldn't post the result to {host}: it answered {status}"
    return f"posted the result to {host} ({status})"


def run(url: str, *, max_pages: int | None = None, max_seconds: float | None = None, max_per_pattern: int,
        fast: bool = False, external: bool = True, allow_private: bool = False, crux_key: str | None = None,
        config: list[str] | None = None, baseline: str | None = None, post_to: str | None = None,
        progress: Progress | None = None) -> tuple[Result, Guard]:
    """Everything the command does short of writing the report and posting it."""
    rules = packs.load(config or [])
    earlier = read_baseline(baseline) if baseline else None
    key = key_from(crux_key) if crux_key is not None else None
    if post_to:
        webhook_host(post_to)
    guard = Guard(allow_private=allow_private)
    c = crawl(url, guard, max_pages, max_seconds, max_per_pattern, fast, external, progress)
    field = field_data(c.origin, home(c).url, key) if key and not c.blocked_by else []
    findings = evaluate(c, None, field) + ([] if c.blocked_by else packs.evaluate(rules, c, None))
    findings, suppressed = suppress(findings, rules.suppress)
    diff = compare(findings, earlier, baseline) if earlier is not None and baseline else None
    extras = Extras(rules.files, suppressed, diff, field)
    markdown, book, passed = report(c, None, findings, extras)
    doc: dict[str, Any] = {"format_version": FORMAT_VERSION, "openppc_online": __version__,
                           "openppc": openppc.__version__, "passed": passed, "markdown": markdown,
                           **data(c, None, findings, extras), "facts": [asdict(f) for f in book.facts]}
    texts = {"md": markdown, "json": redact_text(json.dumps(doc, indent=2, ensure_ascii=False))[0],
             "html": to_html(markdown, f"Site audit: {c.origin}"),
             "sarif": redact_text(json.dumps(sarif(c, findings, __version__), indent=2))[0]}
    return Result(c.origin, findings, diff, passed, health(c), texts), guard


def exit_code(result: Result, fail_on: str | None) -> int:
    """0 clean, 2 a finding at --fail-on (with a baseline, a new one), 3 the report failed its own number check,
    4 too broken to judge with --fail-on."""
    if not result.passed:
        return 3
    if not fail_on:
        return 0
    if result.inconclusive:
        return INCONCLUSIVE
    gate = SEVERITY_RANK[fail_on]
    failing = [f for f in result.findings if SEVERITY_RANK[f.level] >= gate
               and (result.diff is None or f.id in result.diff.new)]
    return 2 if failing else 0


def json_with_summary(result: Result) -> str:
    """What --post-to sends: the JSON result, with a one-line "text" that chat webhooks (Slack's, for one) show."""
    high = sum(f.level == "high" for f in result.findings)
    text = f"OpenPPC site audit of {result.origin}: {len(result.findings)} findings, {high} high."
    return json.dumps({"text": text, **json.loads(result.texts["json"])}, ensure_ascii=False)

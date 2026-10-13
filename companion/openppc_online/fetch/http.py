"""The one way `openppc-online fetch` reaches the network (fitness function 10, SCOPE_WIDENING_PLAN.md section 4).

Each platform has an allowlist of methods and addresses, checked before connecting; nothing else is called. None of
them changes an account: Google's searchStream only answers SELECT queries, Microsoft's Reporting service only builds
reports, and Meta is GET only. No redirect is followed, so an answer can't send a request somewhere else.
"""
import ipaddress
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from email.message import Message
from typing import IO
from urllib.parse import urlsplit

from .versions import GOOGLE, META, MICROSOFT

SECONDS = 120
MOST = 200 * 1024 * 1024  # the largest answer read: a big account's report, unzipped later
ERROR_MOST = 64 * 1024


@dataclass(frozen=True)
class Rule:
    method: str
    host: str
    path: str  # a regular expression the whole path must match

    def allows(self, method: str, host: str, path: str) -> bool:
        return method == self.method and host == self.host and re.fullmatch(self.path, path) is not None


ALLOWED: dict[str, tuple[Rule, ...]] = {
    "google": (
        Rule("POST", "oauth2.googleapis.com", r"/token"),
        Rule("POST", "googleads.googleapis.com", rf"/{GOOGLE.name}/customers/\d{{10}}/googleAds:searchStream"),
    ),
    "microsoft": (
        Rule("POST", "login.microsoftonline.com", r"/common/oauth2/v2\.0/token"),
        Rule("POST", "reporting.api.bingads.microsoft.com", rf"/Reporting/{MICROSOFT.name}/GenerateReport/(Submit|Poll)"),
    ),
    "meta": (
        Rule("GET", "graph.facebook.com", rf"/{re.escape(META.name)}/act_\d+(/(insights|campaigns|adsets|ads))?"),
    ),
}


class Refused(ValueError):
    """A call outside the platform's allowlist. It is never made."""


class HttpError(Exception):
    """An answer that wasn't a success. The body is kept to be read for its codes, never shown."""

    def __init__(self, status: int, body: bytes):
        super().__init__(f"HTTP {status}")
        self.status, self.body = status, body


Send = Callable[[urllib.request.Request, float], tuple[int, bytes]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str,
                         headers: Message, newurl: str) -> None:
        return None  # urllib then raises the 3xx as an HTTPError


_OPENER = urllib.request.build_opener(_NoRedirect)


def _send(req: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return resp.status, resp.read(MOST + 1)
    except urllib.error.HTTPError as e:
        return e.code, e.read(ERROR_MOST)


def _hostname_only(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False


class Gate:
    """Calls for one platform, each checked against its allowlist first."""

    def __init__(self, platform: str, send: Send = _send):
        self.platform, self.rules, self.send = platform, ALLOWED[platform], send
        self._downloads: set[str] = set()

    def allow_download(self, url: str) -> None:
        """Let one GET reach an address the platform's API just gave (Microsoft names a new download address for
        each report and says not to depend on its host): https on port 443, a host name rather than an IP address."""
        parts = urlsplit(url)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.port not in (None, 443) or not _hostname_only(parts.hostname)):
            raise Refused(f"the {self.platform} API gave a download address openppc-online won't use: "
                          f"{parts.scheme}://{parts.hostname or ''}")
        self._downloads.add(url)

    def check(self, method: str, url: str) -> None:
        if method == "GET" and url in self._downloads:
            return
        parts = urlsplit(url)
        host = parts.hostname or ""
        if (parts.scheme == "https" and parts.port in (None, 443) and not parts.username
                and any(rule.allows(method, host, parts.path) for rule in self.rules)):
            return
        raise Refused(f"openppc-online fetch doesn't call {method} {host}{parts.path}")

    def call(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes | None = None) -> bytes:
        self.check(method, url)
        self._downloads.discard(url)
        req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            status, data = self.send(req, SECONDS)
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ValueError(f"couldn't reach {urlsplit(url).hostname}; check the connection and try again") \
                from None
        if not 200 <= status < 300:
            raise HttpError(status, data)
        if len(data) > MOST:
            raise ValueError(f"the {self.platform} API sent more than {MOST // 1024 // 1024} MB; ask for fewer days")
        return data


def codes(values: list[str]) -> list[str]:
    """The platform's error codes worth showing: names like RESOURCE_EXHAUSTED, never free text, which could
    carry anything."""
    return list(dict.fromkeys(v for v in values if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]{2,60}", v)))

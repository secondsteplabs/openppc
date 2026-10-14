"""The site check's only way onto the network, and the rules it obeys.

Every request goes through Guard.connect: the host is resolved once, every address it resolves to is checked, and
the connection is made to that checked address. Checking a name and letting something else resolve it again would let
a site pass the check with a public address and then connect with a private one (DNS rebinding). Redirects are
followed by hand, so each hop is checked the same way, and the browser in a --render pass reaches the network only
through GuardProxy, which uses the same check.
"""
import contextlib
import http.client
import ipaddress
import selectors
import socket
import socketserver
import ssl
import threading
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from .. import __version__

USER_AGENT = f"Mozilla/5.0 (compatible; OpenPPC-SiteAudit/{__version__}; +https://openppc.si)"
ROBOTS_TOKEN = "OpenPPC"     # the name robots.txt rules address
PAGE_BYTES = 5_000_000       # a response is cut off past this many bytes, counted after decompression
TIMEOUT = 15.0               # seconds to connect, and to wait for the next bytes
PAGE_SECONDS = 30.0          # wall-clock limit for one response
PROXY_IDLE = 60.0            # a browser connection through the proxy closes after this long with no traffic
MAX_REDIRECTS = 10
HTML_TYPES = ("text/html", "application/xhtml+xml")
URL_SAFE = "/%:@!$&'()*+,;=?~"  # kept as written when a path or query is percent-encoded; % keeps existing escapes

# Private ranges --allow-private opens, so you can check localhost or a staging host. Nothing else opens.
PRIVATE = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "::1/128", "fc00::/7"))
# Cloud metadata services outside the link-local range, which is always refused
METADATA = frozenset(ipaddress.ip_address(a) for a in ("100.100.100.200", "fd00:ec2::254"))

Address = ipaddress.IPv4Address | ipaddress.IPv6Address


class Refused(OSError):
    """A connection the safety rules stopped."""


def refusal(ip: Address, allow_private: bool = False) -> str:
    """Why this address may not be fetched, or "" when it may."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return refusal(ip.ipv4_mapped, allow_private)
        if ip.sixtofour is not None:
            return refusal(ip.sixtofour, allow_private)
        if ip.teredo is not None:
            return "a tunnelled address"
    if ip in METADATA or ip.is_link_local:
        return "a link-local or cloud metadata address, which is never fetched"
    if any(ip in net for net in PRIVATE):  # before is_reserved, which ::1 also is
        return "" if allow_private else "a private address; pass --allow-private to check your own network"
    if ip.is_global and not (ip.is_multicast or ip.is_reserved):
        return ""
    return "not a public address"


def _getaddrinfo(host: str, port: int) -> list[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


@dataclass
class Guard:
    allow_private: bool = False
    resolve: Callable[[str, int], list[str]] = _getaddrinfo
    refused: list[str] = field(default_factory=list)  # each refusal, for the report

    def addresses(self, host: str, port: int) -> list[str]:
        """The addresses to connect to. Every address the host resolves to must pass, so a name can't pair a public
        address with a private one."""
        if host.rstrip(".").lower().split(".")[-1] == "invalid":
            raise Refused(f"{host} is under .invalid, which never resolves (RFC 6761), so it isn't looked up")
        try:
            found = self.resolve(host, port)
        except OSError as e:
            raise OSError(f"{host} doesn't resolve ({e})") from e
        if not found:
            raise OSError(f"{host} doesn't resolve")
        for a in found:
            why = refusal(ipaddress.ip_address(a.split("%")[0]), self.allow_private)
            if why:
                self.refused.append(host)
                raise Refused(f"{host} resolves to {a}, {why}")
        return list(dict.fromkeys(found))

    def connect(self, host: str, port: int, timeout: float = TIMEOUT) -> socket.socket:
        """A connection to the first checked address that answers, as a browser tries them in turn."""
        error: OSError = OSError(f"{host} doesn't resolve")
        for a in self.addresses(host, port):
            try:
                return socket.create_connection((a, port), timeout=timeout)
            except OSError as e:
                error = e
        raise error


class _HTTP(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, guard: Guard, timeout: float = TIMEOUT):
        super().__init__(host, port, timeout=timeout)
        self._guard, self._wait = guard, timeout

    def connect(self) -> None:
        self.sock = self._guard.connect(self.host, self.port, self._wait)


class _HTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, guard: Guard, timeout: float = TIMEOUT):
        super().__init__(host, port, timeout=timeout)
        self._guard, self._wait = guard, timeout
        self._tls = ssl.create_default_context()

    def connect(self) -> None:
        self.sock = self._tls.wrap_socket(self._guard.connect(self.host, self.port, self._wait),
                                          server_hostname=self.host)


@dataclass
class Response:
    url: str                     # the URL asked for
    final_url: str               # after redirects
    status: int                  # 0 when there was no response, -1 when not asked yet
    headers: dict[str, str] = field(default_factory=dict)  # of the final response, names lower-case, no cookies
    body: bytes = b""
    hops: list[tuple[str, int]] = field(default_factory=list)  # each redirect followed: (url, status)
    error: str = ""              # why there is no response
    refused: bool = False        # the safety rules stopped it
    truncated: bool = False      # the body passed the byte limit and was cut off
    seconds: float = 0.0

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()


def encoded(text: str) -> str:
    """A path or query as a browser sends it: spaces and non-ASCII characters percent-encoded."""
    return quote(text, safe=URL_SAFE)


def _read(r: http.client.HTTPResponse, max_bytes: int, deadline: float) -> tuple[bytes, bool]:
    encoding = r.getheader("Content-Encoding", "").lower()
    inflate = zlib.decompressobj(47) if encoding in ("gzip", "x-gzip", "deflate") else None  # 47: gzip or zlib
    out = bytearray()
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("the response took too long")
        chunk = r.read1(65536)  # what has arrived, so a server sending a byte at a time still meets the deadline
        if not chunk:
            return bytes(out), False
        # max_length: a small compressed body is never inflated past the limit
        out += inflate.decompress(chunk, max_bytes + 1 - len(out)) if inflate else chunk
        if len(out) > max_bytes or (inflate and inflate.unconsumed_tail):
            return bytes(out[:max_bytes]), True


def connection(url: str, guard: Guard, timeout: float = TIMEOUT) -> tuple[http.client.HTTPConnection, str]:
    """A guarded connection for an http(s) URL, and the target to request on it."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"not an http(s) address: {url}")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    conn = (_HTTPS if parts.scheme == "https" else _HTTP)(parts.hostname, port, guard, timeout)
    return conn, urlunsplit(("", "", encoded(parts.path or "/"), encoded(parts.query), ""))


def post(url: str, guard: Guard, body: bytes, content_type: str) -> int:
    """One POST through the guard, with no redirect followed: the status it answered. Raises OSError (Refused when
    the safety rules stop it) when there is no answer."""
    conn, target = connection(url, guard)
    try:
        conn.request("POST", target, body, {"Content-Type": content_type, "User-Agent": USER_AGENT})
        return conn.getresponse().status
    except http.client.HTTPException as e:
        raise OSError(f"{type(e).__name__}: {e}") from e
    finally:
        conn.close()


def fetch(url: str, guard: Guard, method: str = "GET", max_bytes: int = PAGE_BYTES,
          follow: bool = True, html_only: bool = False, headers: dict[str, str] | None = None,
          body: bytes | None = None, seconds: float = PAGE_SECONDS, timeout: float = TIMEOUT) -> Response:
    """One request, its redirects followed hop by hop. Never raises for a network problem: the Response says what
    went wrong. html_only: the body of anything but an HTML page is not read. headers and body go to the first
    address only, so an API key never follows a redirect. seconds: the wall-clock limit; timeout: to connect, and to
    wait for the next bytes."""
    start = time.monotonic()
    resp = Response(url, url, 0)
    current = url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                conn, target = connection(current, guard, timeout)
            except ValueError as e:
                resp.error = str(e)
                return resp
            first = not resp.hops
            try:
                conn.request(method, target, body if first else None, headers={
                    "User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                    "Accept-Encoding": "gzip, deflate", "Connection": "close", **((headers or {}) if first else {})})
                r = conn.getresponse()
                location = r.getheader("Location")
                if follow and r.status in (301, 302, 303, 307, 308) and location:
                    resp.hops.append((current, r.status))
                    current = urljoin(current, location.strip())
                    continue
                resp.final_url = current
                resp.headers = {k.lower(): v for k, v in r.getheaders() if k.lower() != "set-cookie"}
                if method != "HEAD" and not (html_only and resp.content_type not in HTML_TYPES):
                    resp.body, resp.truncated = _read(r, max_bytes, start + seconds)
                resp.status = r.status  # last: a body that fails part-way is no response
                return resp
            finally:
                conn.close()
        resp.final_url, resp.error = current, f"more than {MAX_REDIRECTS} redirects"
    except Refused as e:
        resp.final_url, resp.error, resp.refused = current, f"refused: {e}", True
    except ssl.SSLCertVerificationError as e:
        resp.final_url, resp.error = current, f"invalid TLS certificate ({e.verify_message})"
    except TimeoutError:
        resp.final_url, resp.error = current, "timed out"
    except (OSError, http.client.HTTPException, zlib.error, ValueError) as e:
        resp.final_url, resp.error = current, f"{type(e).__name__}: {e}"
    finally:
        resp.seconds = time.monotonic() - start
    return resp


def _hostport(target: str, default: int) -> tuple[str, int]:
    parts = urlsplit("//" + target)
    if not parts.hostname:
        raise ValueError(f"bad proxy target {target!r}")
    return parts.hostname, parts.port or default


def _pipe(a: socket.socket, b: socket.socket) -> None:
    sel = selectors.DefaultSelector()
    sel.register(a, selectors.EVENT_READ, b)
    sel.register(b, selectors.EVENT_READ, a)
    try:
        while True:
            events = sel.select(timeout=PROXY_IDLE)
            if not events:
                return
            for key, _ in events:
                data = key.fileobj.recv(65536)  # type: ignore[union-attr]
                if not data:
                    return
                key.data.sendall(data)
    except OSError:  # either side reset or dropped the connection: the tunnel is over
        return
    finally:
        sel.close()


class _ProxyHandler(socketserver.BaseRequestHandler):
    server: "_ProxyServer"

    def handle(self) -> None:
        client: socket.socket = self.request
        client.settimeout(TIMEOUT)
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = client.recv(65536)
            if not chunk or len(head) > 65536:
                return
            head += chunk
        head, _, rest = head.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        try:
            method, target, version = lines[0].split(" ", 2)
            if method == "CONNECT":
                upstream = self.server.guard.connect(*_hostport(target, 443))
                client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            else:
                parts = urlsplit(target)
                if parts.scheme != "http" or not parts.hostname:
                    raise ValueError(f"not a proxy request: {target}")
                upstream = self.server.guard.connect(parts.hostname, parts.port or 80)
                # one request per upstream connection, so a reused browser connection can't reach another host
                kept = [h for h in lines[1:] if not h.lower().startswith(("connection:", "proxy-connection:",
                                                                         "keep-alive:"))]
                path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
                upstream.sendall("\r\n".join([f"{method} {path} {version}", *kept, "Connection: close", "", ""])
                                 .encode("latin-1"))
        except Refused:
            client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            return
        except (OSError, ValueError):
            with contextlib.suppress(OSError):  # the browser may already have hung up
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            return
        with upstream:
            if rest:
                upstream.sendall(rest)
            _pipe(client, upstream)


class _SinkHandler(socketserver.BaseRequestHandler):
    server: "_ProxyServer"

    def handle(self) -> None:
        client: socket.socket = self.request
        client.settimeout(TIMEOUT)
        with contextlib.suppress(OSError, ValueError, IndexError):
            first = client.recv(65536).decode("latin-1").split("\r\n", 1)[0]
            target = first.split(" ")[1]
            host = _hostport(target, 443)[0] if first.startswith("CONNECT ") else (urlsplit(target).hostname or "")
            if host:
                self.server.asked.append(host)
            client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")


class _ProxyServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    guard: Guard              # the sink's server has none, and never uses it

    def __init__(self, guard: Guard | None, handler: type[socketserver.BaseRequestHandler] = _ProxyHandler):
        super().__init__(("127.0.0.1", 0), handler)
        if guard is not None:
            self.guard = guard
        self.asked: list[str] = []

    def handle_error(self, request: object, client_address: object) -> None:
        pass  # a browser dropping a connection mid-request is routine, not worth a traceback on the console


class GuardProxy:
    """A local HTTP proxy for the browser: every connection it opens passes the Guard. Chromium is pointed at it with
    loopback included, so no request from a rendered page reaches the network any other way."""

    def __init__(self, guard: Guard):
        self._server = _ProxyServer(guard)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> "GuardProxy":
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()


class Sink(GuardProxy):
    """A proxy that refuses everything, before any name is resolved, and notes the hosts asked for. The browser's own
    traffic (update checks, sign-in, push) goes here, while each page's goes through its context's GuardProxy."""

    def __init__(self) -> None:
        self._server = _ProxyServer(None, _SinkHandler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> "Sink":
        super().__enter__()
        return self

    @property
    def asked(self) -> list[str]:
        return sorted(set(self._server.asked))

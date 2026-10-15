"""The calibration's local pages (SITE_AUDIT_PARITY_PLAN.md, section 8): each one leans on one thing a speed metric
measures, with scripted delays. One loopback server answers for every host name under .test, which the harness
resolves to 127.0.0.1, so a page can pull files from several hosts.

With tls=True (the harness's default), front.mjs puts Node's TLS in front of it: HTTP/2 for every host but
OLD_HOST, which speaks HTTP/1.1 only, on a self-signed certificate made for the run, whose error the calibration's
browser ignores (bypass.trusting; Chromium ignores --ignore-certificate-errors-spki-list in Playwright's contexts,
and OpenPPC's own code never ignores one). The tag pages send GA4 and Adobe hits to .test hosts, whose hit patterns
match any host, so OpenPPC's lab answers them as it would a vendor's.
"""
import datetime
import json
import math
import random
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from collections.abc import Callable
from functools import cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

try:  # only the HTTPS run needs it; the unit tests that read the fixtures don't install it
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
except ImportError:
    x509 = None  # type: ignore[assignment]

HOST = "site.test"
OLD_HOST = "old.test"
OTHER_HOSTS = ("cdn.test", "frame.test", OLD_HOST, *(f"t{i}.test" for i in range(1, 9)))
TAG_FIXTURES = ("tags", "tags-chained")  # out of the gate: Lighthouse's loads send their hits, OpenPPC's answer them
HIT_MS = 300                 # how long a hit endpoint takes to answer
FRONT = Path(__file__).with_name("front.mjs")
TEXT = "".join(f"<p>Paragraph {i}: the quick brown fox jumps over the lazy dog, again and again.</p>" for i in range(12))

Origins = Callable[[str], str]  # a host's scheme, name and port, such as "https://cdn.test:51234"


def plain(port: int) -> Origins:
    return lambda host: f"http://{host}:{port}"


def tls(h2: int, h1: int) -> Origins:
    return lambda host: f"https://{host}:{h1 if host == OLD_HOST else h2}"


def busy(ms: int) -> str:
    """JavaScript that keeps the main thread busy for ms (a task of its own when run from a timer)."""
    return f"(()=>{{const e=performance.now()+{ms};while(performance.now()<e){{}}}})();"


def page(body: str, head: str = "") -> str:
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'><title>fixture</title>{head}"
            f"<style>body{{font:16px/1.5 sans-serif;margin:0 12px}}img{{display:block;max-width:100%;height:auto}}"
            f"</style></head><body>{body}</body></html>")


def _timers(*tasks: tuple[int, int]) -> str:
    """Long tasks: (start ms after the script runs, length ms)."""
    return "<script>" + "".join(f"setTimeout(()=>{{{busy(ms)}}},{at});" for at, ms in tasks) + "</script>"


def _tags(on: Origins) -> str:
    """A GA4-like tag: its library from another host, a page_view beacon, and an event whose answer starts more work."""
    collect = on("t1.test") + "/g/collect?v=2&tid=G-CALIBRATE"
    return (f"<script async src='{on('t1.test')}/r/js?ms=100&kb=30&busy=60'></script><script>"
            f"navigator.sendBeacon('{collect}&en=page_view');"
            f"fetch('{collect}&en=view_item',{{mode:'no-cors'}}).then(()=>{{{busy(150)}}});"
            f"setTimeout(()=>fetch('{collect}&en=scroll',{{mode:'no-cors'}}).then(()=>{{{busy(100)}}}),1200);"
            "</script>")


def _chained(on: Origins) -> str:
    """An Adobe-like pixel whose answer is a redirect to a GA4 hit on a third host, and a later one after a task."""
    pixel = on("t2.test") + "/b/ss/calibrate/1/JS-2.0?pageName=home"
    return (f"<script async src='{on('t2.test')}/r/js?ms=150&kb=50&busy=80'></script><script>"
            f"new Image().src='{pixel}';"
            f"setTimeout(()=>{{{busy(120)}new Image().src='{pixel}&events=event1';}},800);</script>")


def fixtures(on: Origins) -> dict[str, str]:
    """Each fixture's page, by name; the files they use come from /r/ on any host."""
    spa = ("<div id=app></div><script src='/r/js?ms=300'></script><script>"
           "fetch('/r/data?ms=500').then(r=>r.json()).then(d=>{"
           "document.getElementById('app').innerHTML='<h1>'+d.title+'</h1><img src=\"/r/img?w=412&h=260&ms=200\" "
           "width=412 height=260>'+d.text;});</script>")
    thirds = "".join(f"<script async src='{on(h)}/r/js?ms=200&busy=30'></script>" for h in OTHER_HOSTS[2:])
    return {
        "text": page("<h1>Plain text</h1>" + TEXT),
        "hero": page("<img src='/r/img?w=412&h=300&ms=300' width=412 height=300 alt=''>" + TEXT),
        "lazy-hero": page("<img loading=lazy src='/r/img?w=412&h=300&ms=300' width=412 height=300 alt=''>" + TEXT),
        "spa": page(spa),
        "blocking-css": page("<h1>Blocking CSS</h1>" + TEXT, "<link rel=stylesheet href='/r/css?ms=1200&kb=40'>"),
        "blocking-js": page("<h1>Blocking script</h1>" + TEXT, "<script src='/r/js?ms=800&kb=60'></script>"),
        "late-shift": page("<h1>Late banner</h1>" + TEXT + "<script>setTimeout(()=>{const b=document.createElement"
                           "('div');b.style.height='200px';b.style.background='#fc0';b.textContent='Offer';"
                           "document.body.prepend(b);},1500);</script>"),
        "iframe-shift": page("<h1>Frame</h1><iframe src='" + on("frame.test") + "/r/frame' width=380 height=300>"
                             "</iframe>" + TEXT),
        "tasks-60": page("<h1>Short tasks</h1>" + TEXT + _timers(*((100 * i, 60) for i in range(1, 9)))),
        "tasks-200": page("<h1>Tasks</h1>" + TEXT + _timers((100, 200), (500, 200), (900, 200))),
        "task-800": page("<h1>One long task</h1>" + TEXT + _timers((200, 800))),
        # timers fire up to 2 s late under CPU throttling: each gap stays clear of TTI's 5 s quiet window either way
        "tasks-late": page("<h1>Late tasks</h1>" + TEXT + _timers((2000, 200), (2500, 200), (5000, 300))),
        "redirect": "",   # /r/redirect, two hops to the text fixture
        "third-parties": page("<h1>Many hosts</h1>" + TEXT, thirds),
        "big-image": page("<h1>Heavy image</h1><p>Above it, a line.</p>"
                          "<img src='" + on("cdn.test") + "/r/img?w=900&h=700' width=900 height=700 alt=''>" + TEXT),
        "many-requests": page("<h1>Many files</h1>" + "".join(
            f"<img src='/r/img?w=48&h=48&ms=100&n={i}' width=48 height=48 alt=''>" for i in range(40)) + TEXT),
        # built by one script, not parsed off the throttled network, whose chunks would split the work differently
        "big-dom": page("<h1>Large page</h1><div id=rows></div><script>document.getElementById('rows').innerHTML="
                        "Array.from({length: 4000}, (_, i) => `<div class=r><span>${i}</span><span>row</span>"
                        "<span>cell</span></div>`).join('');</script>"),
        # swap: the fallback paints first, then the wider boxes of font() push the text down. Paragraphs one line wide
        # on a desktop in the fallback font and two in the web font; the font comes late enough that Chrome doesn't
        # flag its shift as following the viewport's setup (had_recent_input, 500 ms), and a slower image holds the
        # load event back so that neither side's trace ends before the swap
        "font-swap": page(
            "<h1>Web font</h1>"
            + "".join(f"<p>{'the quick brown fox jumps over the lazy dog, ' * 3}</p>" for _ in range(12))
            + "<img src='/r/img?w=4&h=4&ms=3000' width=4 height=4 alt=''>",
            "<style>@font-face{font-family:cal;src:url('/r/font?ms=1500') format('truetype');font-display:swap}"
            "h1,p{font-family:cal,sans-serif}</style>"),
        # six connections a host on HTTP/1.1, where HTTP/2 sends them all at once
        "http1-host": page("<h1>An HTTP/1.1 host</h1>" + "".join(
            f"<img src='{on(OLD_HOST)}/r/img?w=96&h=96&ms=150&n={i}' width=96 height=96 alt=''>" for i in range(18))
            + TEXT),
        "tags": page("<h1>Tags</h1>" + TEXT, _tags(on)),
        "tags-chained": page("<h1>Chained pixel</h1>" + TEXT, _chained(on)),
    }


def url(name: str, on: Origins) -> str:
    if name == "redirect":
        return f"{on(HOST)}/r/redirect?n=2&to=/f/text"
    return f"{on(HOST)}/f/{name}"


def _sum(data: bytes) -> int:
    data += b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(data) // 4}I", data)) & 0xFFFFFFFF


@cache
def font() -> bytes:
    """A TrueType font of two glyphs that maps each printable ASCII character to a box a full em wide, about twice a
    fallback's letters, so swapping it in rewraps each paragraph onto more lines and moves the text below."""
    box = (struct.pack(">5hHH", 1, 100, 0, 500, 700, 3, 0) + bytes([1] * 4)   # one contour of 4 on-curve points
           + struct.pack(">4h", 100, 400, 0, -400) + struct.pack(">4h", 0, 0, 700, 0))
    names = {1: "Calibrate", 2: "Regular", 3: "Calibrate", 4: "Calibrate", 6: "Calibrate-Regular"}
    strings = [s.encode("utf-16-be") for s in names.values()]
    records, at = b"", 0
    for (nid, _), s in zip(names.items(), strings):
        records += struct.pack(">6H", 3, 1, 0x409, nid, len(s), at)
        at += len(s)
    seg = struct.pack(">2H", 0x7E, 0xFFFF) + b"\0\0" + struct.pack(">2H", 0x20, 0xFFFF) + struct.pack(">2h", 0, 1) \
        + struct.pack(">2H", 4, 0) + struct.pack(">95H", *[1] * 95)
    cmap4 = struct.pack(">7H", 4, 14 + len(seg), 0, 4, 4, 1, 0) + seg
    tables = {
        "OS/2": struct.pack(">HhHHH11h10s4I4s3H3h2H2I", 1, 1000, 400, 5, 0, 650, 700, 0, 140, 650, 700, 0, 480, 50,
                            250, 0, b"\0" * 10, 1, 0, 0, 0, b"OPPC", 0x40, 0x20, 0x7E, 800, -200, 0, 800, 200, 1, 0),
        "cmap": struct.pack(">HHHHI", 0, 1, 3, 1, 12) + cmap4,
        "glyf": box,
        "head": struct.pack(">IIIIHHqqhhhhHHhhh", 0x10000, 0x10000, 0, 0x5F0F3CF5, 0x000B, 1000, 0, 0, 100, 0, 500,
                            700, 0, 8, 2, 1, 0),
        "hhea": struct.pack(">IhhhHhhhhhh4hhH", 0x10000, 800, -200, 0, 1000, 0, 100, 500, 1, 0, 0, 0, 0, 0, 0, 0, 2),
        "hmtx": struct.pack(">HhHh", 1000, 0, 1000, 100),
        "loca": struct.pack(">3I", 0, 0, len(box)),
        "maxp": struct.pack(">I14H", 0x10000, 2, 4, 1, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0),
        "name": struct.pack(">3H", 0, len(names), 6 + len(records)) + records + b"".join(strings),
        "post": struct.pack(">IIhhIIIII", 0x30000, 0, -100, 50, 0, 0, 0, 0, 0),
    }
    n = len(tables)
    power = 2 ** int(math.log2(n))
    directory, body = struct.pack(">IHHHH", 0x10000, n, power * 16, int(math.log2(n)), n * 16 - power * 16), b""
    offset = 12 + 16 * n
    for tag in sorted(tables):
        data = tables[tag]
        directory += struct.pack(">4sIII", tag.encode(), _sum(data), offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    out = bytearray(directory + body)
    head = offset + body.index(tables["head"])
    out[head + 8:head + 12] = struct.pack(">I", (0xB1B0AFBA - _sum(bytes(out))) & 0xFFFFFFFF)
    return bytes(out)


def certificate(folder: Path) -> tuple[Path, Path]:
    """A self-signed certificate for the fixtures' hosts, valid for two days, and its key, as PEM files in folder."""
    if x509 is None:
        raise RuntimeError("the calibration's HTTPS pages need pip install cryptography")
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OpenPPC calibration")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(hours=1))
            .not_valid_after(now + datetime.timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(h) for h in (HOST, *OTHER_HOSTS)]), False)
            .sign(key, hashes.SHA256()))
    keyfile, certfile = folder / "key.pem", folder / "cert.pem"
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return keyfile, certfile


@cache
def png(w: int, h: int, seed: int = 0) -> bytes:
    """A w x h PNG of noise that doesn't compress, so its size is about 3 bytes a pixel."""
    rng = random.Random(seed * 7919 + w * 31 + h)
    raw = b"".join(b"\x00" + rng.randbytes(w * 3) for _ in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


FRAME = page("<p>Inside the frame</p><script>setTimeout(()=>{const b=document.createElement('div');"
             "b.style.height='120px';b.style.background='#09f';document.body.prepend(b);},1000);</script><p>More</p>")


class Server(ThreadingHTTPServer):
    """The fixtures over plain HTTP on one port, or with tls=True behind front.mjs (which needs Node and
    cryptography). `on` gives each host's origin, and `hits` the tag hits that reached it."""
    daemon_threads = True

    def __init__(self, tls: bool = False) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.port = self.server_address[1]
        self.tls = tls
        self.on: Origins = plain(self.port)
        self.hits: list[str] = []
        self.pages = fixtures(self.on)
        self._front: subprocess.Popen[str] | None = None
        self._folder: tempfile.TemporaryDirectory[str] | None = None
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    def __enter__(self) -> "Server":
        self._thread.start()
        if self.tls:
            try:
                self._start_front()
            except BaseException:
                self.__exit__()
                raise
        return self

    def _start_front(self) -> None:
        node = shutil.which("node")
        if not node:
            raise RuntimeError("the calibration's HTTPS pages need Node.js")
        self._folder = tempfile.TemporaryDirectory(prefix="openppc-calibration-")
        key, cert = certificate(Path(self._folder.name))
        self._front = subprocess.Popen([node, str(FRONT), str(key), str(cert), str(self.port)],
                                       stdout=subprocess.PIPE, text=True)
        assert self._front.stdout is not None
        line = self._front.stdout.readline().split()
        if len(line) != 2 or not all(p.isdigit() for p in line):
            raise RuntimeError("front.mjs didn't start")
        self.on = tls(int(line[0]), int(line[1]))
        self.pages = fixtures(self.on)

    def __exit__(self, *exc: object) -> None:
        if self._front:
            self._front.terminate()
            self._front.wait(10)
        if self._folder:
            self._folder.cleanup()
        self.shutdown()
        self.server_close()

    def handle_error(self, request: Any, client_address: Any) -> None:
        if not isinstance(sys.exc_info()[1], ConnectionError):  # front.mjs's kept-alive connections, as it stops
            super().handle_error(request, client_address)

    def get_request(self) -> tuple[socket.socket, Any]:
        conn, address = super().get_request()
        if sys.platform == "win32":  # as net._ProxyHandler does: Windows drops unread bytes when a socket closes
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 0)
        return conn, address


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: Server

    def log_message(self, *args: object) -> None:
        pass

    def _send(self, status: int, kind: str, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Timing-Allow-Origin", "*")  # each file's protocol readable by the page, for the tests
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 (a beacon is a POST)
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802 (http.server's name)
        parts = urlsplit(self.path)
        q = {k: v[0] for k, v in parse_qs(parts.query).items()}
        time.sleep(int(q.get("ms", "0")) / 1000)
        pad = int(q.get("kb", "0")) * 1024
        if parts.path.startswith("/f/") and (body := self.server.pages.get(parts.path[3:])):
            self._send(200, "text/html; charset=utf-8", body.encode())
        elif parts.path == "/r/css":
            self._send(200, "text/css", (b"h1{color:#123}" + b"/*" + b"x" * pad + b"*/"))
        elif parts.path == "/r/js":
            code = busy(int(q.get("busy", "0"))) if q.get("busy") else ""
            self._send(200, "text/javascript", (code + "/*" + "x" * pad + "*/").encode())
        elif parts.path == "/r/img":
            self._send(200, "image/png", png(int(q.get("w", "100")), int(q.get("h", "100")), int(q.get("n", "0"))))
        elif parts.path == "/r/font":
            self._send(200, "font/ttf", font())
        elif parts.path in ("/g/collect", "/b/ss/calibrate/1/JS-2.0"):
            self.server.hits.append(self.path)
            time.sleep(HIT_MS / 1000)
            if parts.path.startswith("/b/ss/"):
                to = self.server.on("t3.test") + "/g/collect?v=2&tid=G-CALIBRATE&en=chained"
                self._send(302, "text/plain", b"", {"Location": to})
            else:
                self._send(204, "text/plain", b"")
        elif parts.path == "/r/data":
            self._send(200, "application/json", json.dumps({"title": "Rendered by script", "text": TEXT}).encode())
        elif parts.path == "/r/frame":
            self._send(200, "text/html; charset=utf-8", FRAME.encode())
        elif parts.path == "/r/redirect":
            n = int(q.get("n", "0"))
            to = q.get("to", "/f/text")
            nxt = f"/r/redirect?n={n - 1}&to={to}" if n > 1 else to
            self._send(302, "text/plain", b"", {"Location": nxt})
        else:
            self._send(404, "text/plain", b"not found")

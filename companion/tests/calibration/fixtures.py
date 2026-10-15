"""The calibration's local pages (SITE_AUDIT_PARITY_PLAN.md, section 8): each one leans on one thing a speed metric
measures, with scripted delays. One loopback server answers for every host name under .test, which the harness
resolves to 127.0.0.1, so a page can pull files from several hosts.

Not yet here, against the plan: HTTPS with HTTP/2 (the server speaks HTTP/1.1), a web font, an HTTP/1.1-only host
beside HTTP/2 ones, and the tag pages (their hits would go to vendor names on port 443).
"""
import json
import random
import socket
import struct
import sys
import threading
import time
import zlib
from functools import cache
from typing import Any
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HOST = "site.test"
OTHER_HOSTS = ("cdn.test", "frame.test", *(f"t{i}.test" for i in range(1, 9)))
TEXT = "".join(f"<p>Paragraph {i}: the quick brown fox jumps over the lazy dog, again and again.</p>" for i in range(12))


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


def fixtures(port: int) -> dict[str, str]:
    """Each fixture's page, by name; the files they use come from /r/ on any host."""
    def on(host: str) -> str:
        return f"http://{host}:{port}"
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
    }


def url(name: str, port: int) -> str:
    if name == "redirect":
        return f"http://{HOST}:{port}/r/redirect?n=2&to=/f/text"
    return f"http://{HOST}:{port}/f/{name}"


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
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.port = self.server_address[1]
        self.pages = fixtures(self.port)
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    def __enter__(self) -> "Server":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.shutdown()
        self.server_close()

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
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

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

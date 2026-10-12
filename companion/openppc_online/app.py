"""`openppc-online app`: the OpenPPC web app, served from this computer.

It is the app at openppc.si, and audits and checks still run in the browser tab. Later versions add what a tab can't
do on its own, run by this process for the page.

The server answers only on 127.0.0.1, and only to its own Host name, which shuts out DNS rebinding. Its API needs
the token written into the page it serves, sent in a header: another website open in the browser can't read the
page, and sending that header from elsewhere takes a CORS preflight this server never allows. It serves a fixed
list of files read at start, so no path reaches anything else on disk. THREAT_MODEL.md has the rest.
"""
import json
import re
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import openppc

from . import __version__

PACKAGE = Path(__file__).resolve().parent
PACKAGED_WEB = PACKAGE / "web"            # the wheel's copy (tools/stage_companion_web.py)
CLONE_WEB = PACKAGE.parent.parent / "web"  # a clone of the repository serves its own web/
LOCAL = PACKAGE / "local"                 # what only this copy of the app has
PORT = 8766
TIMEOUT = 30  # seconds a connection may sit idle: a slow client can't hold a thread for good
CHUNK = 65_536  # bytes per socket write: one ~1 MB write on Windows loopback can stall the reader for good
HOSTED_CONNECT = "connect-src https://cdn.jsdelivr.net"  # web/index.html's policy
LOCAL_CONNECT = "connect-src 'self' https://cdn.jsdelivr.net"
POLICY = re.compile(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">')
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
TOKEN_HEADER = "X-OpenPPC-Token"


def web_root() -> Path:
    for web in (PACKAGED_WEB, CLONE_WEB):
        if (web / "index.html").is_file():
            return web
    raise ValueError("this install has no copy of the web app. Reinstall openppc-online, or in a clone of the "
                     "repository run it from there.")


def _once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"web/index.html changed: expected one {old!r}. Update openppc_online/app.py to match.")
    return text.replace(old, new)


def page(web: Path, token: str) -> tuple[bytes, str]:
    """(web/index.html with the token and local.js in it, and its policy): the hosted page, allowed to call this
    server. A change to the hosted page's policy stops the server rather than serve a page that half works."""
    html = (web / "index.html").read_text(encoding="utf-8")
    html = _once(html, HOSTED_CONNECT + ";", LOCAL_CONNECT + ";")
    html = _once(html, '<meta charset="utf-8">', f'<meta charset="utf-8">\n<meta name="openppc-local" content="{token}">')
    html = _once(html, '<script defer src="app.js"></script>',
                 '<script defer src="app.js"></script>\n<script defer src="local.js"></script>')
    policy = POLICY.search(html)
    if policy is None:
        raise RuntimeError("web/index.html has no Content-Security-Policy. Update openppc_online/app.py to match.")
    return html.encode("utf-8"), policy[1] + "; frame-ancestors 'none'"


def files(web: Path) -> dict[str, tuple[bytes, str]]:
    """Every file the page may load, by address, read once: nothing else on disk can be asked for."""
    found = [p for p in web.iterdir() if p.is_file() and p.suffix in TYPES and p.name != "index.html"]
    found.append(LOCAL / "local.js")
    return {f"/{p.name}": (p.read_bytes(), TYPES[p.suffix]) for p in found}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = sys.platform != "win32"  # on Windows it would let a second server share a taken port

    def __init__(self, port: int, web: Path):
        super().__init__(("127.0.0.1", port), Handler)
        self.token = secrets.token_urlsafe(32)
        self.port = self.server_address[1]
        self.hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        self.index, self.policy = page(web, self.token)
        self.files = files(web)


class Handler(BaseHTTPRequestHandler):
    server: Server
    server_version = "openppc-online"
    sys_version = ""
    timeout = TIMEOUT

    def log_message(self, format: str, *args: Any) -> None:
        pass  # the terminal says the app is running; a line per file would bury that

    def _send(self, code: int, body: bytes, kind: str, cache: str = "no-cache", policy: bool = False) -> None:
        self.send_response(code)
        for name, value in (("Content-Type", kind), ("Content-Length", str(len(body))), ("Cache-Control", cache),
                            ("Referrer-Policy", "no-referrer"), ("X-Content-Type-Options", "nosniff"),
                            ("Cross-Origin-Resource-Policy", "same-origin")):
            self.send_header(name, value)
        if policy:  # the page's only: a worker takes its policy from its own script, and openppc.si sends it none
            self.send_header("Content-Security-Policy", self.server.policy)
        self.end_headers()
        if self.command != "HEAD":
            for at in range(0, len(body), CHUNK):
                self.wfile.write(body[at:at + CHUNK])

    def _text(self, code: int, text: str) -> None:
        self._send(code, text.encode("utf-8"), "text/plain; charset=utf-8")

    def do_GET(self) -> None:
        if self.headers.get("Host", "") not in self.server.hosts:
            self._text(421, "This server answers only at its own address, 127.0.0.1.")
            return
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, self.server.index, TYPES[".html"], cache="no-store", policy=True)
        elif path.startswith("/api/"):
            self._api(path)
        elif path in self.server.files:
            self._send(200, *self.server.files[path])
        else:
            self._text(404, "Not found.")

    do_HEAD = do_GET

    def _api(self, path: str) -> None:
        given = self.headers.get(TOKEN_HEADER, "").encode("latin-1", "replace")
        if not secrets.compare_digest(given, self.server.token.encode("ascii")):
            self._json(403, {"ok": False, "error": "This page isn't the one openppc-online app is serving now. "
                                                   "Reload it."})
        elif path == "/api/info":
            self._json(200, {"ok": True, "version": __version__, "openppc": openppc.__version__})
        else:
            self._json(404, {"ok": False, "error": "openppc-online has no such address. Reload the page."})

    def _json(self, code: int, obj: dict[str, Any]) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")


def serve(port: int = PORT, open_browser: bool = True) -> int:
    web = web_root()
    try:
        server = Server(port, web)
    except OSError:
        server = Server(0, web)  # the port is taken, by another copy perhaps: any free one will do
    url = f"http://127.0.0.1:{server.port}/"
    print(f"OpenPPC is running on this computer at {url}\nKeep this window open while you use it; Ctrl-C stops it.",
          file=sys.stderr)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("openppc-online: stopped", file=sys.stderr)
    finally:
        server.server_close()
    return 0

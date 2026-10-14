import http.client
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from sites import PSI_HOST, PUBLIC

from openppc_online import app


@pytest.fixture
def public(monkeypatch):
    """Names resolve to a public address, and connecting to it reaches this computer: the guard sees a public site,
    so --psi accepts it, and nothing leaves the computer. Every name looked up is recorded."""
    seen = []
    real_lookup = socket.getaddrinfo

    def lookup(host, port, *args, **kw):
        seen.append(host)
        if host == PUBLIC:
            return real_lookup("127.0.0.1", port, *args, **kw)
        if host in ("shop.test", PSI_HOST):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC, port))]
        raise socket.gaierror(f"{host} isn't resolved in this test")
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    return seen


@pytest.fixture
def server():
    """`openppc-online app` on a free port, serving this clone's web/."""
    s = app.Server(0, app.CLONE_WEB)
    thread = threading.Thread(target=s.serve_forever, daemon=True)
    thread.start()
    yield s
    s.shutdown()
    s.server_close()


@pytest.fixture
def serve():
    """serve(routes) starts a website on 127.0.0.1; routes(base) maps a path, with or without its query, to (status,
    headers, body). serve.asked lists every path requested, across the sites, and serve.heard their headers."""
    servers = []
    asked = []

    def start(routes, fallback=(404, {}, "<title>Not found</title>")):
        table = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.answer(True)

            def do_HEAD(self):
                self.answer(False)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                start.posted.append((self.path, dict(self.headers), self.rfile.read(length)))
                self.answer(True)

            def answer(self, with_body):
                asked.append(self.path)
                start.heard.append((self.path, dict(self.headers)))
                status, headers, body = table.get(self.path) or table.get(self.path.split("?")[0], fallback)
                data = body if isinstance(body, bytes) else body.encode()
                self.send_response(status)
                for k, v in {"Content-Type": "text/html; charset=utf-8", **headers}.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if with_body:
                    self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        base = f"http://127.0.0.1:{server.server_port}"
        table.update(routes(base))
        return base

    start.asked = asked
    start.posted = []
    start.heard = []  # (path, request headers) of every request
    yield start
    for s in servers:
        s.shutdown()
        s.server_close()


def ask(server, path, method="GET", host=None, headers=None, body=None):
    """(status, headers, body) of one request, sent as written: no path is cleaned up on the way. A body gets a
    Content-Length unless headers name one, or a Transfer-Encoding."""
    # some Windows machines drop about one loopback connection in twenty carrying more than 64 KB, with any server
    for _ in range(2):
        try:
            return _ask(server, path, method, host, headers, body)
        except OSError:
            pass
    return _ask(server, path, method, host, headers, body)


def _ask(server, path, method, host, headers, body):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    conn.putheader("Host", f"127.0.0.1:{server.port}" if host is None else host)
    headers = dict(headers or {})
    if body is not None and not {"content-length", "transfer-encoding"} & {k.lower() for k in headers}:
        headers["Content-Length"] = str(len(body))
    for name, value in headers.items():
        conn.putheader(name, value)
    conn.endheaders(body)
    res = conn.getresponse()
    body = res.read()
    conn.close()
    return res.status, dict(res.getheaders()), body

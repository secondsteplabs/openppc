import http.client
import threading

import pytest

from openppc_online import app


@pytest.fixture
def server():
    """`openppc-online app` on a free port, serving this clone's web/."""
    s = app.Server(0, app.CLONE_WEB)
    thread = threading.Thread(target=s.serve_forever, daemon=True)
    thread.start()
    yield s
    s.shutdown()
    s.server_close()


def ask(server, path, method="GET", host=None, headers=None):
    """(status, headers, body) of one request, sent as written: no path is cleaned up on the way."""
    try:
        return _ask(server, path, method, host, headers)
    except OSError:
        # some Windows machines drop a few loopback connections carrying more than 64 KB, with any server
        return _ask(server, path, method, host, headers)


def _ask(server, path, method, host, headers):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    conn.putheader("Host", f"127.0.0.1:{server.port}" if host is None else host)
    for name, value in (headers or {}).items():
        conn.putheader(name, value)
    conn.endheaders()
    res = conn.getresponse()
    body = res.read()
    conn.close()
    return res.status, dict(res.getheaders()), body

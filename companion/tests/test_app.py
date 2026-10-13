"""`openppc-online app`: what it serves, to whom, and what it never gives away (THREAT_MODEL.md)."""
import json
import socket

import openppc
import pytest
from conftest import ask

from openppc_online import __version__, app, cli

FILES = ["/app.js", "/engine.js", "/engine-worker.js", "/style.css", "/favicon.svg", "/local.js"]
OUTSIDE = ["/../pyproject.toml", "/..%2fpyproject.toml", "/%2e%2e/LICENSE", "/local/local.js", "/web/index.html",
           "//etc/passwd", "/app.js/", "/.git/config", "/app.py", "/openppc_online/app.py", "/C:/Windows/win.ini",
           "/..\\pyproject.toml", "/index.html/..", "/api"]


def _token(server):
    return {app.TOKEN_HEADER: server.token}


def test_it_listens_on_127_0_0_1_only(server):
    assert server.server_address[0] == "127.0.0.1"


def test_the_page_is_the_hosted_app_plus_the_token_and_local_js(server):
    status, headers, body = ask(server, "/")
    hosted = (app.CLONE_WEB / "index.html").read_text(encoding="utf-8")
    local = body.decode("utf-8")
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert (local.replace(f'\n<meta name="openppc-local" content="{server.token}">', "")
            .replace('\n<script defer src="local.js"></script>', "")
            .replace(app.LOCAL_CONNECT, app.HOSTED_CONNECT)) == hosted
    policy = headers["Content-Security-Policy"]
    assert app.LOCAL_CONNECT + ";" in policy and policy.endswith("; frame-ancestors 'none'")
    assert (headers["Referrer-Policy"], headers["X-Content-Type-Options"]) == ("no-referrer", "nosniff")


@pytest.mark.parametrize("host", ["evil.example:{port}", "127.0.0.1", "localhost", "127.0.0.1:1", "[::1]:{port}",
                                  "localhost.evil.example:{port}", ""])
def test_another_host_name_gets_nothing(server, host):
    # DNS rebinding: a site whose name now points at 127.0.0.1 still sends its own name
    for path, headers in (("/", None), ("/api/info", _token(server)), ("/app.js", None)):
        status, _, body = ask(server, path, host=host.format(port=server.port), headers=headers)
        assert status == 421 and server.token.encode() not in body and b"version" not in body


def test_localhost_by_name_is_the_same_server(server):
    assert ask(server, "/", host=f"localhost:{server.port}")[0] == 200


def test_the_api_needs_this_runs_token(server):
    assert ask(server, "/api/info")[0] == 403
    assert ask(server, "/api/info", headers={app.TOKEN_HEADER: server.token[:-1] + "x"})[0] == 403
    assert ask(server, "/api/info", headers={app.TOKEN_HEADER: "é€".encode("utf-8")})[0] == 403
    status, _, body = ask(server, "/api/info", headers=_token(server))
    assert status == 200
    info = json.loads(body)
    assert {k: info[k] for k in ("ok", "version", "openppc")} == {"ok": True, "version": __version__,
                                                                  "openppc": openppc.__version__}
    assert ask(server, "/api/nothing", headers=_token(server))[0] == 404


@pytest.mark.parametrize("path", FILES)
def test_the_apps_files_are_served(server, path):
    status, headers, body = ask(server, path)
    assert status == 200 and body
    assert headers["Content-Type"].startswith("image/svg+xml" if path.endswith(".svg") else
                                              "text/css" if path.endswith(".css") else "text/javascript")
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    # a worker takes its policy from its own script: the page's would block the engine, and openppc.si sends none
    assert "Content-Security-Policy" not in headers


@pytest.mark.parametrize("path", OUTSIDE)
def test_no_path_reaches_anything_else(server, path):
    status, _, body = ask(server, path)
    assert status == 404 and body == b"Not found."


@pytest.mark.parametrize("method, code", [("POST", 403), ("PUT", 501), ("DELETE", 501), ("PATCH", 501),
                                          ("OPTIONS", 501)])
def test_it_never_allows_another_origin(server, method, code):
    # POST is the job API's (test_app_jobs.py), refused here for the origin; nothing else but GET and HEAD exists
    status, headers, _ = ask(server, "/api/info", method=method,
                             headers={**_token(server), "Origin": "https://evil.example"})
    assert status == code
    assert not any(name.lower().startswith("access-control-") for name in headers)


def test_head_sends_no_body(server):
    status, headers, body = ask(server, "/", method="HEAD")
    assert status == 200 and int(headers["Content-Length"]) > 0 and body == b""


def test_the_token_is_only_ever_in_the_page(server):
    # fitness function 11, with this run's token as the sentinel: no other answer, header or error carries it
    token = server.token.encode()
    requests = [(p, m, None) for p in ["/", "/index.html", *FILES, *OUTSIDE, "/api/info", "/api/x"]
                for m in ("GET", "HEAD")]
    requests += [("/api/info", "GET", _token(server)), ("/api/x", "GET", _token(server)),
                 ("/api/info", "POST", _token(server))]
    for path, method, headers in requests:
        status, got, body = ask(server, path, method=method, headers=headers)
        assert not any(server.token in v for v in got.values()), (path, method)
        if (path, method) not in (("/", "GET"), ("/index.html", "GET")):
            assert token not in body, (path, method)


def test_a_change_to_the_hosted_policy_stops_it(tmp_path):
    index = (app.CLONE_WEB / "index.html").read_text(encoding="utf-8")
    (tmp_path / "index.html").write_text(index.replace(app.HOSTED_CONNECT, "connect-src https://example.com"),
                                         encoding="utf-8")
    with pytest.raises(RuntimeError, match="web/index.html changed"):
        app.page(tmp_path, "token")


def test_serve_says_where_without_the_token_and_takes_another_port_if_needed(monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(app.secrets, "token_urlsafe", lambda n: "SENTINEL-TOKEN")
    monkeypatch.setattr(app.webbrowser, "open", opened.append)
    monkeypatch.setattr(app.Server, "serve_forever", lambda self: (_ for _ in ()).throw(KeyboardInterrupt))
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        assert app.serve(port) == 0
    err = capsys.readouterr().err
    assert len(opened) == 1 and opened[0].startswith("http://127.0.0.1:") and opened[0] in err
    assert f":{port}/" not in opened[0]
    assert "SENTINEL-TOKEN" not in err + opened[0]


def test_the_command_line(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["--version"])
    assert stop.value.code == 0 and f"openppc-online {__version__}" in capsys.readouterr().out
    with pytest.raises(SystemExit) as stop:
        cli.main(["fetch"])
    assert stop.value.code == 1

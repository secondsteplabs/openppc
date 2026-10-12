"""The companion's boundary, fitness functions 9 and 10 (SCOPE_WIDENING_PLAN.md, section 4): each command contacts
only its declared hosts, and the companion has no HTTP client until a command that needs one lands, with the
read-only allowlist of calls it may make."""
import ast
import socket
from pathlib import Path

from conftest import ask

PACKAGE = Path(__file__).resolve().parent.parent / "openppc_online"
CLIENTS = {"urllib.request", "http.client", "ssl", "urllib3", "requests", "httpx", "aiohttp", "ftplib", "smtplib",
           "poplib", "imaplib", "telnetlib", "xmlrpc", "asyncio"}
# what each module may import from the network stack, and why
ALLOWED = {"http.server": {"app.py"},  # the app's server, bound to 127.0.0.1
           "webbrowser": {"app.py"}}   # opens the app's own address


def _imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            yield node.module


def test_the_companion_has_no_http_client_yet():
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for name in _imports(path):
            if path.name in ALLOWED.get(name, ()):
                continue
            if name in ALLOWED or name == "socket" or any(name == c or name.startswith(c + ".") for c in CLIENTS):
                found.append(f"{path.name} imports {name}")
    assert found == []


def test_the_app_contacts_only_127_0_0_1(server, monkeypatch):
    contacted = []
    connect = socket.socket.connect

    def record(self, address):
        contacted.append(address[0])
        return connect(self, address)
    monkeypatch.setattr(socket.socket, "connect", record)
    for path in ("/", "/app.js", "/api/info", "/nothing"):
        ask(server, path, headers={"X-OpenPPC-Token": server.token})
    assert contacted and set(contacted) == {"127.0.0.1"}

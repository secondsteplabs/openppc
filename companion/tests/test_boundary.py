"""The companion's boundary, fitness functions 9 and 10 (SCOPE_WIDENING_PLAN.md, section 4): each command contacts
only its declared hosts, and the network stack is imported only by the modules named for it here."""
import ast
import socket
from pathlib import Path

from conftest import ask

PACKAGE = Path(__file__).resolve().parent.parent / "openppc_online"
CLIENTS = {"urllib.request", "http.client", "ssl", "socket", "urllib3", "requests", "httpx", "aiohttp", "ftplib",
           "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc", "asyncio"}
# which files may import each part of the network stack, and why
ALLOWED = {"http.server": {"app.py"},  # the app's server, bound to 127.0.0.1
           "webbrowser": {"app.py"},   # opens the app's own address
           # the site check's guard: every connection is checked before it is made
           "http.client": {"siteaudit/net.py"}, "ssl": {"siteaudit/net.py"}, "socket": {"siteaudit/net.py"}}
# the core's stable API (ADR-2): what the companion may import from openppc, by module
STABLE = {"openppc": {"__version__"}, "openppc.facts": {"FactBook"}, "openppc.engine.trace": {"trace"},
          "openppc.ingest": {"load_report"}, "openppc.templates": {"run_template", "Template"},
          "openppc.formats": {"to_html"}}


def _imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            yield node.module


def test_the_companion_uses_only_the_cores_stable_api():
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and not node.level and (node.module or "").split(".")[0] == "openppc":
                found += [f"{path.name}: from {node.module} import {a.name}" for a in node.names
                          if a.name not in STABLE.get(node.module or "", ())]
            elif isinstance(node, ast.Import):
                found += [f"{path.name}: import {a.name}" for a in node.names
                          if a.name.split(".")[0] == "openppc" and a.name != "openppc"]
            elif (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "openppc"
                  and node.attr not in STABLE["openppc"]):
                found.append(f"{path.name}: openppc.{node.attr}")
    assert found == []


def test_only_the_named_modules_touch_the_network():
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        where = path.relative_to(PACKAGE).as_posix()
        for name in _imports(path):
            if where in ALLOWED.get(name, ()):
                continue
            if name in ALLOWED or any(name == c or name.startswith(c + ".") for c in CLIENTS):
                found.append(f"{where} imports {name}")
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

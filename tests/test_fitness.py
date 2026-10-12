"""The promises OpenPPC makes, as tests: no network in the engine, the CLI runs offline and has no command that goes
online, the core never imports the companion, the browser bundle holds only listed modules and stays within its size
budget, the promise wording stays word for word, and everything the app downloads has its license listed."""
import argparse
import ast
import importlib.util
import re
import socket
from pathlib import Path

import pytest

from openppc import mcp_server, samples
from openppc.cli import _parser, main
from openppc.templates import TEMPLATES

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "openppc"
NETWORK = {"socket", "ssl", "http", "urllib.request", "urllib3", "asyncio", "requests", "httpx", "aiohttp",
           "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc", "webbrowser"}
# The MCP SDK serves `openppc-mcp --http` (ADR-2): it is imported by the MCP server and nowhere else.
ALLOWED = {"mcp": {"openppc/mcp_server.py"}}
ENGINE_JS_BASELINE = 323_832  # bytes, 0.1.10
ENGINE_JS_BUDGET = 1.15       # growth allowed before the plan is revisited (SCOPE_WIDENING_PLAN.md, section 4)


def _modules():
    return sorted(p.relative_to(ROOT).as_posix() for p in PACKAGE.rglob("*.py"))


def _imports(path):
    for node in ast.walk(ast.parse((ROOT / path).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            yield node.module


def _build_web():
    spec = importlib.util.spec_from_file_location("build_web", ROOT / "tools" / "build_web.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_engine_imports_nothing_that_reaches_the_network():
    found = []
    for path in _modules():
        for name in _imports(path):
            top = name.split(".")[0]
            if path in ALLOWED.get(top, ()):
                continue
            if top in ALLOWED or any(name == n or name.startswith(n + ".") for n in NETWORK):
                found.append(f"{path} imports {name}")
    assert not found


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("OpenPPC tried to use the network")
    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, refuse)


def test_every_command_runs_with_the_network_switched_off(no_network, tmp_path, capsys):
    for name in TEMPLATES:
        assert main(["audit", name, "--sample", "--out", str(tmp_path / f"{name}.md")]) == 0, name
        assert "Number check" in mcp_server.audit_account(name, str(samples.path(samples.EXPORTS[name])))
    assert main(["check", "--sample"]) == 2  # the sample AI audit has wrong numbers, on purpose
    assert main(["templates"]) == 0 and main(["industries"]) == 0
    capsys.readouterr()


def test_the_core_never_imports_the_companion():
    # fitness function 8: openppc-online depends on openppc, never the reverse (ADR-7)
    assert [f"{p} imports {n}" for p in _modules() for n in _imports(p) if n.split(".")[0] == "openppc_online"] == []


def test_the_command_line_has_only_offline_commands():
    commands = next(a for a in _parser()._actions if isinstance(a, argparse._SubParsersAction)).choices
    assert set(commands) == {"templates", "industries", "audit", "check"}


@pytest.mark.parametrize("command", ["fetch", "site", "app"])
def test_a_command_that_goes_online_says_where_it_lives(no_network, command, capsys):
    assert main([command, "--port", "8766"]) == 1
    assert main(["--debug", command]) == 1
    err = capsys.readouterr().err
    assert err.count("OpenPPC never goes online") == 2 and "openppc-online" in err


def test_the_mcp_tools_only_read_files_and_text():
    # the hosted connector exposes no fetch or crawl tool: that would mean SSRF and credentials on a shared server
    tools = {t.__name__ for t in (*mcp_server.LOCAL_TOOLS, *mcp_server.WEB_TOOLS)}
    assert tools == {"list_templates", "audit_account", "check_numbers", "audit_export", "check_audit"}


def test_the_browser_bundle_holds_only_listed_modules():
    build = _build_web()
    listed = set(build.BUNDLE) | set(build.NOT_BUNDLED)
    assert not set(build.BUNDLE) & set(build.NOT_BUNDLED)
    assert set(_modules()) - listed == set(), "list each new module in BUNDLE or NOT_BUNDLED in tools/build_web.py"
    assert listed - set(_modules()) == set(), "tools/build_web.py lists a module that no longer exists"


def test_the_browser_bundle_stays_within_its_size_budget():
    size = (ROOT / "web" / "engine.js").stat().st_size
    assert size <= ENGINE_JS_BASELINE * ENGINE_JS_BUDGET, f"web/engine.js is {size:,} bytes"


PROMISES = {
    "README.md": ["Read-only Google Ads audits where every number is traced back to your own export",
                  "never connects to your account", "makes no network calls", "No API keys",
                  "## Configuration\n\nNone. No API keys, no `.env`."],
    "site/pages/index.html": ["never connects to your account"],
    "site/layout.html": ["nothing is uploaded", "connect-src"],
    "web/index.html": ["nothing is uploaded", "connect-src https://cdn.jsdelivr.net"],
    "site/pages/docs/install.html": ["The command line runs the same engine with no network calls."],
    "pyproject.toml": ['description = "Read-only Google Ads audits where every number is traced back to your own '
                       'export."', "dependencies = []"],
    "GOVERNANCE.md": ["OpenPPC makes no network calls and uploads nothing.",
                      "OpenPPC never connects to your account and never changes anything in it."],
}


@pytest.mark.parametrize("path", sorted(PROMISES))
def test_the_promises_stay_word_for_word(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert [p for p in PROMISES[path] if p not in text] == []


def test_everything_the_app_loads_from_its_cdn_is_in_the_license_list():
    loaded = set()
    for page in ("web/index.html", "web/engine-worker.js"):
        text = (ROOT / page).read_text(encoding="utf-8")
        loaded |= set(re.findall(r"cdn\.jsdelivr\.net/npm/(@?[\w.-]+(?:/[\w.-]+)?)@([\d.]+)", text))
        loaded |= {("pyodide", v) for v in re.findall(r"cdn\.jsdelivr\.net/pyodide/v([\d.]+)/", text)}
    assert len(loaded) == 6
    listed = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    assert [f"{name}@{version}" for name, version in sorted(loaded) if f"| {name} | {version} |" not in listed] == []

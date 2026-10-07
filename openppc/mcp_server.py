"""MCP server: run OpenPPC inside Claude, Cursor, ChatGPT or any MCP client.

On your computer (Claude Code, Claude Desktop, Cursor), over stdio, reading local files:

    claude mcp add openppc -- uvx --from "openppc[mcp]" openppc-mcp

As a web connector (ChatGPT, claude.ai), over streamable HTTP at /mcp:

    openppc-mcp --http --host 0.0.0.0 --port 8000

Local tools take file paths. The web connector never reads paths: its tools take the export's
contents, work in a temporary folder that is deleted when the call ends, and keep nothing. Every
tool is annotated read-only so clients know it never changes anything.
"""
import argparse
import functools
import ipaddress
import json
import os
import re
import socket
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

try:  # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as Server
except ImportError:
    try:  # MCP Python SDK 1.x
        from mcp.server.fastmcp import FastMCP as Server
    except ImportError:  # the MCP extra is optional
        Server = None
try:  # the error a tool raises on purpose: the model gets its message (SDK 2.x, then 1.x)
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:
    try:
        from mcp.server.fastmcp.exceptions import ToolError
    except ImportError:
        ToolError = None
try:
    from mcp.types import ToolAnnotations
    READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
except ImportError:
    READ_ONLY = None
try:  # which hostnames an HTTP server answers to (DNS rebinding protection)
    from mcp.server.transport_security import TransportSecuritySettings
except ImportError:
    TransportSecuritySettings = None
try:  # what a ChatGPT tool returns: text for the model, data for the results view
    from mcp.types import CallToolResult, TextContent
except ImportError:
    CallToolResult = TextContent = None

from . import __version__
from .checkfacts import facts_for_check
from .cli import explain
from .engine.trace import render_check, trace
from .templates import TEMPLATES, run_template, run_template_book

EXPORT_LIMIT = 3_500_000  # characters in one export sent to the web connector; a request is capped at 4 MB
UPLOAD_LIMIT = 25_000_000  # bytes in one export uploaded in ChatGPT, fetched from the link ChatGPT gives
RESULTS_VIEW = "ui://openppc/results-v1.html"  # the view ChatGPT shows for an audit or a check
VIEW_MIME = "text/html;profile=mcp-app"
UPLOADED_FILE = {  # a file the user attached in ChatGPT, as ChatGPT passes it to a tool
    "type": "object", "description": "The Google Ads export the user uploaded in the chat.",
    "properties": {"download_url": {"type": "string"}, "file_id": {"type": "string"},
                   "mime_type": {"type": "string"}, "file_name": {"type": "string"}},
    "required": ["download_url", "file_id"]}
INSTRUCTIONS = ("OpenPPC audits Google Ads exports read-only. Code computes every number in its reports and a "
                "checker traces each one back to the export. Quote its numbers as they are and do not add "
                "figures of your own; use check_numbers or check_audit to verify any other audit's numbers.")


def list_templates() -> str:
    """List the audit templates, the export each one reads, and what it returns."""
    return "\n".join(f"- {t.NAME} ({t.TIER}): reads a {t.INPUT}. {t.SUMMARY}" for t in TEMPLATES.values())


def audit_account(template: str, data_path: str, industry: str = "", min_cost: float | None = None,
                  brand: str = "") -> str:
    """Run an audit template on a local Google Ads export and return the report as markdown.
    Every number in the report is computed from the file and traced back to it. Pass the
    account's brand names (comma-separated) so brand terms are never flagged as waste."""
    markdown, _, _ = run_template(template, data_path, industry=industry or None, min_cost=min_cost,
                                  brand=brand or None)
    return markdown


def check_numbers(audit_text: str, data_paths: list[str], industry: str = "") -> str:
    """Check every number in an audit, written by any AI or person, against local export files.
    Reports which numbers trace to the data, which are wrong numbers (the data says otherwise; the real
    figure is given where known), which are wrong labels (a real figure on the wrong metric or row), and
    which sentences contradict their own numbers."""
    claims, contradictions = trace(audit_text, facts_for_check(audit_text, data_paths, industry or None))
    return render_check(claims, contradictions)


def _export_file(folder, text, name):
    """Write an export's contents into the call's temporary folder, under a safe name."""
    if len(text) > EXPORT_LIMIT:
        raise ValueError(f"The export is too large for the web connector ({len(text):,} characters; the limit is "
                         f"{EXPORT_LIMIT:,}). Export a shorter date range, or run OpenPPC on your computer.")
    stem = re.sub(r"[^\w.\-]+", "_", Path(name or "").name).strip("._")[:80] or "export"
    if not stem.lower().endswith((".csv", ".tsv", ".txt", ".json")):
        stem += ".json" if text.lstrip().startswith("{") else ".csv"
    path = Path(folder) / stem
    path.write_text(text, encoding="utf-8")
    return str(path)


def audit_export(template: str, export_text: str, export_name: str = "export.csv", industry: str = "",
                 min_cost: float | None = None, brand: str = "") -> str:
    """Run an audit template on the contents of a Google Ads export and return the report as markdown.
    Pass the whole file's text: a Search terms or Keywords report as CSV, or the JSON for snapshot and
    two-period templates. Every number in the report is computed from it and traced back to it. Pass the
    account's brand names (comma-separated) so brand terms are never flagged as waste."""
    with tempfile.TemporaryDirectory(prefix="openppc-") as folder:
        return audit_account(template, _export_file(folder, export_text, export_name), industry, min_cost, brand)


def check_audit(audit_text: str, export_text: str, export_name: str = "export.csv", industry: str = "") -> str:
    """Check every number in an audit, written by any AI or person, against the contents of the Google Ads
    export it was written from (pass the whole file's text). Reports which numbers trace to the data,
    which are wrong numbers (the data says otherwise; the real figure is given where known), which are wrong
    labels (a real figure on the wrong metric or row), and which sentences contradict their own numbers."""
    with tempfile.TemporaryDirectory(prefix="openppc-") as folder:
        return check_numbers(audit_text, [_export_file(folder, export_text, export_name)], industry)


def _allow_local():
    return os.environ.get("OPENPPC_ALLOW_LOCAL_UPLOADS") == "1"  # tests only: fetch from a local server


def _public_host(url):
    """Only fetch from the public internet: a link to this machine or a private network is refused, so nobody can
    use the connector to reach anything behind it."""
    parts = urlparse(url)
    if parts.scheme != "https" and not (_allow_local() and parts.scheme == "http"):
        raise ValueError("The uploaded file's link must use https.")
    if not parts.hostname:
        raise ValueError("The uploaded file's link has no host.")
    if _allow_local():
        return
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, parts.port or 443)}
    except socket.gaierror:
        raise ValueError(f"Can't reach {parts.hostname} to fetch the uploaded file.") from None
    if not addresses or not all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses):
        raise ValueError("The uploaded file's link points at a private address.")


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _public_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_upload(upload):
    """The bytes of a file the user uploaded in ChatGPT, from the short-lived link ChatGPT passes with it."""
    if not isinstance(upload, dict) or not upload.get("download_url"):
        raise ValueError("Upload the Google Ads export in the chat, or paste its contents.")
    url = str(upload["download_url"])
    _public_host(url)
    opener = urllib.request.build_opener(_CheckedRedirects)
    request = urllib.request.Request(url, headers={"User-Agent": f"openppc/{__version__}"})
    with opener.open(request, timeout=60) as response:
        data = response.read(UPLOAD_LIMIT + 1)
    if len(data) > UPLOAD_LIMIT:
        raise ValueError(f"The uploaded export is over {UPLOAD_LIMIT // 1_000_000} MB. Export a shorter date range, "
                         "or run OpenPPC on your computer.")
    return data, str(upload.get("file_name") or "")


def _export_in(folder, export_file, export_text, export_name):
    """The export for one call, as a file in the call's temporary folder: uploaded in ChatGPT, or pasted as text."""
    if export_file:
        data, name = _fetch_upload(export_file)
        path = Path(_export_file(folder, "", name or export_name))  # a safe name with a known extension
        path.write_bytes(data)  # as uploaded: the reader works out the encoding (Google's UTF-16 exports too)
        return str(path)
    if not export_text:
        raise ValueError("Upload the Google Ads export in the chat, or paste its contents.")
    return _export_file(folder, export_text, export_name)


def _json_safe(value):
    return json.loads(json.dumps(value, default=str))


def chatgpt_audit_export(template: str, export_file: dict | None = None, export_text: str = "",
                         export_name: str = "export.csv", industry: str = "", min_cost: float | None = None,
                         brand: str = ""):
    """Run an audit template on a Google Ads export the user uploaded in the chat (export_file) or pasted
    (export_text). Returns the report as markdown, with every number computed from the export and traced back
    to it. Pass the account's brand names (comma-separated) so brand terms are never flagged as waste. Call
    list_templates first if you don't know which template fits the export."""
    with tempfile.TemporaryDirectory(prefix="openppc-") as folder:
        path = _export_in(folder, export_file, export_text, export_name)
        markdown, book, passed = run_template_book(template, path, industry=industry or None, min_cost=min_cost,
                                                   brand=brand or None)
    view = {"kind": "audit", "template": template, "title": TEMPLATES[template].TITLE, "passed": passed,
            "facts": len(book.facts), "period": (book.client or {}).get("period"), "cards": _json_safe(book.cards)}
    return CallToolResult(content=[TextContent(type="text", text=markdown)], structured_content=view)


def chatgpt_check_audit(audit_text: str, export_file: dict | None = None, export_text: str = "",
                        export_name: str = "export.csv", industry: str = ""):
    """Check every number in an audit, written by any AI or person, against the Google Ads export it was written
    from: uploaded in the chat (export_file) or pasted (export_text). Reports which numbers trace to the data,
    which are wrong numbers (with the real figure where known), which are wrong labels, and which sentences
    contradict their own numbers."""
    with tempfile.TemporaryDirectory(prefix="openppc-") as folder:
        path = _export_in(folder, export_file, export_text, export_name)
        claims, contradictions = trace(audit_text, facts_for_check(audit_text, [path], industry or None))
    count = lambda verdict: sum(c.verdict == verdict for c in claims)
    view = {"kind": "check",
            "counts": {"total": len(claims), "traced": count("traced"), "mismatch": count("mismatch"),
                       "not_in_data": count("not in data"), "cant_check": count("can't check"),
                       "contradictions": len(contradictions)},
            "numbers": [{"line": c.line, "written": c.written, "verdict": c.verdict, "detail": c.detail,
                         "context": c.context[:240]} for c in claims],
            "contradictions": [{"line": n, "problem": p, "context": ctx[:240]} for n, p, ctx in contradictions]}
    return CallToolResult(content=[TextContent(type="text", text=render_check(claims, contradictions))],
                          structured_content=view)


def results_view() -> str:
    """The results view ChatGPT shows under an audit or a check."""
    return (Path(__file__).parent / "ui" / "results.html").read_text(encoding="utf-8")


def _plain_errors(tool):
    """Hand the errors a user can fix to the model as plain messages, the ones the command line prints. The SDK
    reports any other exception as only "Error executing tool <name>", which looks like OpenPPC is broken."""
    @functools.wraps(tool)
    def call(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        except (ValueError, FileNotFoundError, KeyError) as e:
            if ToolError is None:
                raise
            raise ToolError(explain(e)) from None
    return call


LOCAL_TOOLS = (list_templates, audit_account, check_numbers)
WEB_TOOLS = (list_templates, audit_export, check_audit)  # contents in, never paths
CHATGPT_TOOLS = (  # the web tools as ChatGPT runs them: an upload or pasted contents in, text and a view out
    (chatgpt_audit_export, "audit_export", "Running the audit", "Audit ready"),
    (chatgpt_check_audit, "check_audit", "Checking every number", "Numbers checked"))


def build_server(web=False):
    try:
        server = Server("openppc", instructions=INSTRUCTIONS, version=__version__)
    except TypeError:  # an SDK 1.x server takes no version
        try:
            server = Server("openppc", instructions=INSTRUCTIONS)
        except TypeError:  # an SDK without server instructions
            server = Server("openppc")
    if web and CallToolResult is not None and hasattr(server, "resource"):
        return _chatgpt_ready(server)
    for tool in WEB_TOOLS if web else LOCAL_TOOLS:
        try:
            server.tool(annotations=READ_ONLY)(_plain_errors(tool))
        except TypeError:  # an SDK too old for tool annotations
            server.tool()(_plain_errors(tool))
    return server


def _chatgpt_ready(server):
    """The web tools with what ChatGPT needs: an uploaded file as input, and a results view linked to each tool."""
    server.tool(annotations=READ_ONLY)(_plain_errors(list_templates))
    for fn, name, invoking, invoked in CHATGPT_TOOLS:
        meta = {"ui": {"resourceUri": RESULTS_VIEW}, "openai/outputTemplate": RESULTS_VIEW,
                "openai/toolInvocation/invoking": invoking, "openai/toolInvocation/invoked": invoked,
                "openai/fileParams": ["export_file"]}
        server.tool(name=name, annotations=READ_ONLY, meta=meta, structured_output=False)(_plain_errors(fn))
        params = server._tool_manager.get_tool(name).parameters
        params["properties"]["export_file"] = UPLOADED_FILE  # inline, the shape ChatGPT looks for
        params.pop("$defs", None)
    server.resource(RESULTS_VIEW, name="openppc-results", title="OpenPPC results", mime_type=VIEW_MIME,
                    meta={"ui": {"prefersBorder": True, "csp": {"connectDomains": [], "resourceDomains": []}}})(results_view)
    return server


def _trusted_hosts(hosts):
    """The public hostnames the HTTP server answers to, besides this machine. Bound to 127.0.0.1 the SDK accepts only
    localhost Host headers, so behind a proxy or tunnel (mcp.openppc.si, a Tailscale Funnel) the public name must be
    listed, or every request is refused with "Invalid Host header"."""
    if not hosts or TransportSecuritySettings is None:
        return None
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"] + [name for h in hosts for name in (h, f"{h}:*")],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*", "https://chatgpt.com"]
                        + [f"https://{h}" for h in hosts])


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="openppc-mcp",
        description="OpenPPC as an MCP server: over stdio for Claude Code, Claude Desktop and Cursor, "
                    "or over HTTP (--http) as a connector for ChatGPT and claude.ai.")
    parser.add_argument("--http", action="store_true",
                        help="serve streamable HTTP at /mcp; the tools then take file contents, never paths")
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on with --http (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on with --http (default 8000)")
    parser.add_argument("--allow-host", action="append", default=[], metavar="HOST",
                        help="a public hostname the HTTP server answers to, such as mcp.openppc.si (repeatable; "
                             "OPENPPC_ALLOWED_HOSTS takes a comma-separated list too)")
    args = parser.parse_args(argv)
    hosts = [h.strip() for h in args.allow_host + os.environ.get("OPENPPC_ALLOWED_HOSTS", "").split(",") if h.strip()]
    security = _trusted_hosts(hosts)
    if Server is None:
        raise SystemExit('The MCP server needs the optional extra: uv pip install "openppc[mcp]"')
    server = build_server(web=args.http)
    if not args.http:
        server.run()
        return
    extra = {"transport_security": security} if security else {}
    try:  # SDK 2.x takes the HTTP options as arguments
        server.run("streamable-http", host=args.host, port=args.port, stateless_http=True, json_response=True, **extra)
    except TypeError:  # SDK 1.x reads them from settings
        server.settings.host, server.settings.port = args.host, args.port
        server.settings.stateless_http, server.settings.json_response = True, True
        if security:
            server.settings.transport_security = security
        server.run(transport="streamable-http")


if __name__ == "__main__":
    main()

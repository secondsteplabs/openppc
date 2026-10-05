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
import re
import tempfile
from pathlib import Path

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

from . import __version__
from .checkfacts import facts_for_paths
from .cli import explain
from .engine.trace import render_check, trace
from .templates import TEMPLATES, run_template

EXPORT_LIMIT = 3_500_000  # characters in one export sent to the web connector; a request is capped at 4 MB
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
    Reports which numbers trace to the data, which are attached to the wrong metric or row,
    which are not in the data at all, and which sentences contradict their own numbers."""
    claims, contradictions = trace(audit_text, facts_for_paths(data_paths, industry or None))
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
    which are attached to the wrong metric or row, which are not in the data at all, and which sentences
    contradict their own numbers."""
    with tempfile.TemporaryDirectory(prefix="openppc-") as folder:
        return check_numbers(audit_text, [_export_file(folder, export_text, export_name)], industry)


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


def build_server(web=False):
    try:
        server = Server("openppc", instructions=INSTRUCTIONS, version=__version__)
    except TypeError:  # an SDK 1.x server takes no version
        try:
            server = Server("openppc", instructions=INSTRUCTIONS)
        except TypeError:  # an SDK without server instructions
            server = Server("openppc")
    for tool in WEB_TOOLS if web else LOCAL_TOOLS:
        try:
            server.tool(annotations=READ_ONLY)(_plain_errors(tool))
        except TypeError:  # an SDK too old for tool annotations
            server.tool()(_plain_errors(tool))
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="openppc-mcp",
        description="OpenPPC as an MCP server: over stdio for Claude Code, Claude Desktop and Cursor, "
                    "or over HTTP (--http) as a connector for ChatGPT and claude.ai.")
    parser.add_argument("--http", action="store_true",
                        help="serve streamable HTTP at /mcp; the tools then take file contents, never paths")
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on with --http (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on with --http (default 8000)")
    args = parser.parse_args(argv)
    if Server is None:
        raise SystemExit('The MCP server needs the optional extra: uv pip install "openppc[mcp]"')
    server = build_server(web=args.http)
    if not args.http:
        server.run()
        return
    try:  # SDK 2.x takes the HTTP options as arguments
        server.run("streamable-http", host=args.host, port=args.port, stateless_http=True, json_response=True)
    except TypeError:  # SDK 1.x reads them from settings
        server.settings.host, server.settings.port = args.host, args.port
        server.settings.stateless_http, server.settings.json_response = True, True
        server.run(transport="streamable-http")


if __name__ == "__main__":
    main()

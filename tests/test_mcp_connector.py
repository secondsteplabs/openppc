"""The web connector (ChatGPT, claude.ai): same answers as the local tools, from file contents, never paths."""
import asyncio
import inspect
import json
from pathlib import Path

import pytest

from openppc import mcp_server

EXAMPLES = Path(__file__).parent.parent / "examples"
CSV = EXAMPLES / "search_terms_acme.csv"
SAMPLE = EXAMPLES / "ai_audit_sample.md"


def _tools(server):
    tools = server.list_tools()
    return asyncio.run(tools) if inspect.isawaitable(tools) else tools


def test_contents_give_the_same_report_as_the_file():
    by_path = mcp_server.audit_account("search-term-waste", str(CSV), "home-services")
    by_text = mcp_server.audit_export("search-term-waste", CSV.read_text(), "search_terms_acme.csv", "home-services")
    assert by_text == by_path
    assert mcp_server.check_audit(SAMPLE.read_text(), CSV.read_text()) == mcp_server.check_numbers(SAMPLE.read_text(), [str(CSV)])


def test_an_export_name_can_never_point_outside_the_call_folder():
    report = mcp_server.audit_export("search-term-waste", CSV.read_text(), "../../etc/passwd")
    assert "Source: `passwd.csv`" in report
    assert "Source: `export.csv`" in mcp_server.audit_export("search-term-waste", CSV.read_text(), "")


def test_an_export_that_is_too_large_is_refused():
    with pytest.raises(ValueError, match="too large for the web connector"):
        mcp_server.audit_export("search-term-waste", "x" * (mcp_server.EXPORT_LIMIT + 1))


def test_the_web_connector_offers_no_tool_that_reads_paths():
    pytest.importorskip("mcp")
    web = {t.name for t in _tools(mcp_server.build_server(web=True))}
    local = {t.name for t in _tools(mcp_server.build_server())}
    assert web == {"list_templates", "audit_export", "check_audit"}
    assert local == {"list_templates", "audit_account", "check_numbers"}


def test_a_chatgpt_style_client_can_check_an_audit_over_http():
    pytest.importorskip("mcp")
    testclient = pytest.importorskip("starlette.testclient")
    server = mcp_server.build_server(web=True)
    if not hasattr(server, "streamable_http_app"):
        pytest.skip("this MCP SDK has no streamable HTTP app")
    try:
        app = server.streamable_http_app(stateless_http=True, json_response=True)
    except TypeError:  # SDK 1.x reads these from settings
        server.settings.stateless_http, server.settings.json_response = True, True
        app = server.streamable_http_app()
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

    def call(client, rid, method, params):
        res = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        assert res.status_code == 200, res.text
        return res.json()["result"]

    with testclient.TestClient(app, base_url="http://127.0.0.1:8000") as client:
        init = call(client, 1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                               "clientInfo": {"name": "test", "version": "0"}})
        assert init["serverInfo"]["name"] == "openppc"
        names = {t["name"] for t in call(client, 2, "tools/list", {})["tools"]}
        assert names == {"list_templates", "audit_export", "check_audit"}
        result = call(client, 3, "tools/call", {"name": "check_audit", "arguments": {
            "audit_text": SAMPLE.read_text(), "export_text": CSV.read_text(), "industry": "home-services"}})
        text = "".join(part.get("text", "") for part in result["content"])
        assert "6 traced to your data, 1 mismatched, 3 not in your data, 1 can't be checked from an export" in text


def test_the_command_line_rejects_unknown_options():
    with pytest.raises(SystemExit):
        mcp_server.main(["--nonsense"])


def test_a_mistake_reaches_the_model_as_a_plain_message():
    if mcp_server.Server is None or mcp_server.ToolError is None:
        pytest.skip("the MCP extra is not installed")
    server = mcp_server.build_server()
    for name, args, words in (
        ("audit_account", {"template": "search-term-waste", "data_path": "/nope.csv"}, "no file at /nope.csv"),
        ("audit_account", {"template": "no-such-template", "data_path": str(CSV)}, "unknown template 'no-such-template'"),
        ("audit_account", {"template": "search-term-waste", "data_path": str(SAMPLE)}, "no header row with Clicks and Cost"),
        ("check_numbers", {"audit_text": "Spend was $500.", "data_paths": ["/nope.csv"]}, "no file at /nope.csv"),
    ):
        with pytest.raises(mcp_server.ToolError) as caught:
            asyncio.run(server.call_tool(name, args))
        assert words in str(caught.value), name   # before, the model saw only "Error executing tool <name>"

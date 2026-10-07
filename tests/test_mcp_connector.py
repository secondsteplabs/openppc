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
        assert "6 traced to your data, 3 wrong numbers, 1 wrong label, 1 can't be checked from an export" in text


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


def _http(server):
    testclient = pytest.importorskip("starlette.testclient")
    app = server.streamable_http_app(stateless_http=True, json_response=True)
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    client = testclient.TestClient(app, base_url="http://127.0.0.1:8000")

    def call(rid, method, params):
        res = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        assert res.status_code == 200, res.text
        return res.json()["result"]
    return client, call


def test_chatgpt_sees_read_only_tools_that_take_an_upload_and_show_a_results_view():
    pytest.importorskip("mcp")
    client, call = _http(mcp_server.build_server(web=True))
    with client:
        call(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})
        tools = {t["name"]: t for t in call(2, "tools/list", {})["tools"]}
        for name in ("audit_export", "check_audit"):
            meta, schema = tools[name]["_meta"], tools[name]["inputSchema"]
            assert meta["ui"]["resourceUri"] == meta["openai/outputTemplate"] == mcp_server.RESULTS_VIEW
            assert meta["openai/fileParams"] == ["export_file"]
            assert schema["properties"]["export_file"] == mcp_server.UPLOADED_FILE and "$defs" not in schema
            assert tools[name]["annotations"] == {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
        view = call(3, "resources/read", {"uri": mcp_server.RESULTS_VIEW})["contents"][0]
        assert view["mimeType"] == "text/html;profile=mcp-app" and "ui/notifications/tool-result" in view["text"]


def test_an_export_uploaded_in_chatgpt_is_fetched_audited_and_checked(monkeypatch):
    pytest.importorskip("mcp")
    import functools, http.server, threading
    monkeypatch.setenv("OPENPPC_ALLOW_LOCAL_UPLOADS", "1")  # ChatGPT's link stands in as a local server
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(EXAMPLES))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    upload = {"download_url": f"http://127.0.0.1:{httpd.server_address[1]}/search_terms_acme.csv",
              "file_id": "file_test", "mime_type": "text/csv", "file_name": "search_terms_acme.csv"}
    try:
        client, call = _http(mcp_server.build_server(web=True))
        with client:
            call(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})
            check = call(2, "tools/call", {"name": "check_audit", "arguments": {
                "audit_text": SAMPLE.read_text(), "export_file": upload, "industry": "home-services"}})
            assert check["structuredContent"]["counts"] == {"total": 11, "traced": 6, "mismatch": 1, "not_in_data": 3,
                                                             "cant_check": 1, "contradictions": 1}
            assert "6 traced to your data, 3 wrong numbers, 1 wrong label" in check["content"][0]["text"]
            audit = call(3, "tools/call", {"name": "audit_export", "arguments": {"template": "search-term-waste", "export_file": upload}})
            view = audit["structuredContent"]
            assert view["kind"] == "audit" and view["passed"] and view["cards"]["waste"]
            assert audit["content"][0]["text"] == mcp_server.audit_account("search-term-waste", str(CSV))
    finally:
        httpd.shutdown()


def test_an_upload_link_must_be_public_https(monkeypatch):
    monkeypatch.delenv("OPENPPC_ALLOW_LOCAL_UPLOADS", raising=False)
    with pytest.raises(ValueError, match="https"):
        mcp_server._public_host("http://example.com/file.csv")
    for address in ("127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.2", "::1"):
        monkeypatch.setattr(mcp_server.socket, "getaddrinfo", lambda *a, ip=address: [(0, 0, 0, "", (ip, 443))])
        with pytest.raises(ValueError, match="private address"):
            mcp_server._public_host("https://files.example.com/file.csv")
    monkeypatch.setattr(mcp_server.socket, "getaddrinfo", lambda *a: [(0, 0, 0, "", ("93.184.216.34", 443))])
    mcp_server._public_host("https://files.example.com/file.csv")  # public: allowed
    with pytest.raises(ValueError, match="Upload the Google Ads export"):
        mcp_server._export_in("/tmp", None, "", "export.csv")


def test_a_public_hostname_can_be_trusted_behind_a_proxy():
    pytest.importorskip("mcp")
    testclient = pytest.importorskip("starlette.testclient")
    security = mcp_server._trusted_hosts(["mcp.openppc.si"])
    assert mcp_server._trusted_hosts([]) is None
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    for base, status in (("https://mcp.openppc.si", 200), ("https://mcp.openppc.si:8443", 200), ("https://evil.example", 421)):
        app = mcp_server.build_server(web=True).streamable_http_app(stateless_http=True, json_response=True,
                                                                     transport_security=security)  # one run per app
        with testclient.TestClient(app, base_url=base) as client:
            assert client.post("/mcp", headers=headers, json=body).status_code == status, base

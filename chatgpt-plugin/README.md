# OpenPPC for ChatGPT

The ChatGPT plugin: the OpenPPC MCP server (`openppc-mcp --http`) as an app, plus a skill that tells ChatGPT how to use it.

- `plugin.json`: the plugin manifest (Agent Plugins schema, with OpenAI's display fields).
- `mcp.json`: where ChatGPT reaches the server, `https://mcp.openppc.si/mcp`.
- `skills/openppc/SKILL.md`: when to audit, when to check, and to never add figures of its own.
- `assets/`: icon and logo.

The server gives ChatGPT two read-only tools that take an uploaded export (`audit_export`, `check_audit`) and show
their results in a view (`ui://openppc/results-v1.html`), plus `list_templates`.

Status: the hosted server at `mcp.openppc.si` is not live yet. To try it, run `openppc-mcp --http`, expose it
over HTTPS, and add `https://<your-host>/mcp` in ChatGPT under Plugins, then the plus button, then Add custom MCP server.

# OpenPPC for ChatGPT

The ChatGPT plugin: the OpenPPC MCP server (`openppc-mcp --http`) as an app, plus a skill that tells ChatGPT how to use it.

- `plugin.json`: the plugin manifest (Agent Plugins schema, with OpenAI's display fields).
- `mcp.json`: where ChatGPT reaches the server, `https://mcp.openppc.si/mcp`.
- `skills/openppc/SKILL.md`: when to audit, when to check, and to never add figures of its own.
- `assets/`: icon and logo (square, 512 px).
- `Dockerfile`, `railway.json`: the hosted server's container, built from the repository root.

The server gives ChatGPT two read-only tools that take an uploaded export (`audit_export`, `check_audit`) and show
their results in a view (`ui://openppc/results-v1.html`), plus `list_templates`.

## Hosting

```
docker build -f chatgpt-plugin/Dockerfile -t openppc-mcp .
docker run -p 8000:8000 -e OPENPPC_ALLOWED_HOSTS=localhost openppc-mcp
```

On Railway, point the service's config file at `chatgpt-plugin/railway.json`. Settings, all optional:

- `OPENPPC_ALLOWED_HOSTS`: the public names the server answers to (default `mcp.openppc.si`). Any other Host
  header is refused.
- `OPENPPC_FAIR_USE`: each user's limit as `calls/seconds/jobs at once` (default `30/600/2`), or `off`. A ChatGPT
  user is the anonymous id ChatGPT sends with each call.
- `OPENAI_APPS_CHALLENGE`: the token OpenAI's plugin portal shows, served at `/.well-known/openai-apps-challenge`.
- `OPENPPC_WIDGET_DOMAIN`: the results view's origin (default `https://openppc.si`).

`/health` answers `ok` for the host's health check.

Status: the hosted server at `mcp.openppc.si` is not live yet. To try it, run `openppc-mcp --http`, expose it
over HTTPS, and add `https://<your-host>/mcp` in ChatGPT under Plugins, then the plus button, then Add custom MCP server.

# Threat model: `openppc-online app`

What the local server protects, from whom, and how. Each defence has a test in `tests/test_app.py` or
`tests/test_boundary.py`. Review this page, and run a security review of the diff, before each release that changes
the server.

## What it has

- **The page's token.** A new random value each run (32 bytes, URL-safe). Every call to `/api/` needs it in the
  `X-OpenPPC-Token` header. In 0.1.0 the API only says which version is running; later versions start jobs with it,
  so it is guarded as if it already did.
- **The files on this computer.** The server must never hand out anything but the app's own files.
- **Nothing else yet.** No credentials, uploads or jobs: they come with `site` and `fetch`, and this page grows
  with them.

## Who might attack it

1. **Another website open in the same browser.** It can send requests to `http://127.0.0.1:<port>/`, but can't
   read the answers without CORS, which the server never allows.
2. **A website using DNS rebinding.** Its own name, made to point at 127.0.0.1, so the browser treats the server as
   the same origin as that site.
3. **Another program or user on the same computer.** Anything local can connect to 127.0.0.1.
4. **A page that frames the app,** to trick clicks.

## Defences

| Threat | Defence | Test |
| --- | --- | --- |
| Reached from the network | Listens on 127.0.0.1 only | `test_it_listens_on_127_0_0_1_only` |
| DNS rebinding | Answers only when the Host header is `127.0.0.1:<port>` or `localhost:<port>`; anything else gets 421 and no content | `test_another_host_name_gets_nothing` |
| Another site calling the API | The token header: sending a custom header from another origin needs a CORS preflight, and the server answers `OPTIONS` (and everything but GET and HEAD) with 501 and no `Access-Control-*` header | `test_the_api_needs_this_runs_token`, `test_it_answers_get_and_head_only_and_never_allows_another_origin` |
| Another site reading the token | The token is only in the page, which another origin can't read; `Cross-Origin-Resource-Policy: same-origin` on every answer | `test_the_apps_files_are_served` |
| Guessing the token | 32 random bytes per run, compared in constant time, as bytes (a header that isn't ASCII is refused, not an error) | `test_the_api_needs_this_runs_token` |
| Token leaks | Never in a URL (the address printed and opened has none), a log line (the server logs no requests), a header, or any answer but the page; `Referrer-Policy: no-referrer`; the page is `Cache-Control: no-store` | `test_the_token_is_only_ever_in_the_page`, `test_serve_says_where_without_the_token_and_takes_another_port_if_needed` |
| Path traversal and listings | A fixed map of the app's files, read at start; any other path is 404, whatever it contains (`..`, `%2e%2e`, backslashes, drive letters) | `test_no_path_reaches_anything_else` |
| Framing | `frame-ancestors 'none'` in the page's policy header | `test_the_page_is_the_hosted_app_plus_the_token_and_local_js` |
| A weakened page policy | The page is openppc.si's with one change, `connect-src 'self'`; if the hosted policy changes, the server stops rather than serve a page that half works | `test_a_change_to_the_hosted_policy_stops_it` |
| Exhaustion | Nothing reads a request body; an idle connection is dropped after 30 seconds; threads are daemons | — |
| Contacting other hosts | The companion imports no HTTP client, and serving the app connects to nothing but 127.0.0.1 | `test_the_companion_has_no_http_client_yet`, `test_the_app_contacts_only_127_0_0_1` |

## Accepted

- **Another program or user on this computer** can load the page and so read the token. It can only do what the
  page can, and anything running as you can already read your files. On a shared computer, stop the app when you
  are done.
- **The page loads its Python runtime, two libraries and its fonts from cdn.jsdelivr.net,** as openppc.si does,
  each pinned by version. The libraries, the fonts and the runtime's entry file are checked against hashes; the
  files the runtime loads after that are not.

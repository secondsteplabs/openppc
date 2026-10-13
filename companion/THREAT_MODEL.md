# Threat model: `openppc-online`

What each command protects, from whom, and how: the local server (`app`) first, then the website check (`site`).
Each defence has a test in `tests/`. Review this page, and run a security review of the diff, before each release
that changes either.

# `openppc-online app`

## What it has

- **The page's token.** A new random value each run (32 bytes, URL-safe). Every call to `/api/` needs it in the
  `X-OpenPPC-Token` header. With it, a page can start a site audit from this computer.
- **The job API.** `POST /api/jobs` starts a site audit (`openppc-online site`, with everything in that section
  below), `GET /api/jobs/<id>` shows it, and `POST /api/jobs/<id>/stop` stops it. A job may carry a CrUX key, rule
  packs and a baseline, uploaded from the page; results stay in memory, the last 4 finished, and nothing is
  written to disk.
- **The files on this computer.** The server must never hand out anything but the app's own files.

## Who might attack it

1. **Another website open in the same browser.** It can send requests to `http://127.0.0.1:<port>/`, but can't
   read the answers without CORS, which the server never allows. A form or a simple request could still try to
   start a job (cross-site request forgery).
2. **A website using DNS rebinding.** Its own name, made to point at 127.0.0.1, so the browser treats the server as
   the same origin as that site.
3. **Another program or user on the same computer.** Anything local can connect to 127.0.0.1.
4. **A page that frames the app,** to trick clicks.

## Defences

| Threat | Defence | Test |
| --- | --- | --- |
| Reached from the network | Listens on 127.0.0.1 only | `test_it_listens_on_127_0_0_1_only` |
| DNS rebinding | Answers only when the Host header is `127.0.0.1:<port>` or `localhost:<port>`; anything else gets 421 and no content | `test_another_host_name_gets_nothing` |
| Another site calling the API | The token header: sending a custom header from another origin needs a CORS preflight, and the server answers `OPTIONS` (and PUT, DELETE and PATCH) with 501 and no `Access-Control-*` header | `test_the_api_needs_this_runs_token`, `test_it_never_allows_another_origin` |
| Another site starting a job | POST needs the token and `Content-Type: application/json`, each of which takes a preflight from another origin; an `Origin` header that isn't this server's own is refused as well. Only `/api/jobs` and `/api/jobs/<id>/stop` take a POST | `test_a_post_is_read_only_from_this_page_as_json_of_a_bounded_size`, `test_a_post_to_another_name_or_address_gets_nothing` |
| A body from someone without the token | The Host name, the `Origin`, the token, the content type and a `Content-Length` of at most 20 MB are checked first; a request that fails one is answered and its connection closed with the body unread (chunked bodies are refused) | `test_a_post_is_read_only_from_this_page_as_json_of_a_bounded_size` |
| A job doing what the form didn't say | Every field is checked before a job starts: known names only, types and the command's limits; `--post-to` and `--screenshots` aren't offered, so a job sends no result to a third host and writes no file | `test_every_field_is_checked_before_anything_runs` |
| Uploaded file names | Base name only, at most 100 characters, without control characters or backticks; the file is read from memory, never saved, so no path reaches the report or an error | `test_a_site_audit_runs_as_a_job_and_comes_back_in_every_format` |
| The CrUX key leaking | It arrives in the request body and goes to the run only; no job view, progress line, error or report carries it | `test_the_crux_key_goes_to_the_run_and_never_comes_back` |
| Another site reading the token | The token is only in the page, which another origin can't read; `Cross-Origin-Resource-Policy: same-origin` on every answer | `test_the_apps_files_are_served` |
| Guessing the token | 32 random bytes per run, compared in constant time, as bytes (a header that isn't ASCII is refused, not an error) | `test_the_api_needs_this_runs_token` |
| Token leaks | Never in a URL (the address printed and opened has none), a log line (the server logs no requests), a header, or any answer but the page; `Referrer-Policy: no-referrer`; the page is `Cache-Control: no-store` | `test_the_token_is_only_ever_in_the_page`, `test_serve_says_where_without_the_token_and_takes_another_port_if_needed` |
| Path traversal and listings | A fixed map of the app's files, read at start; any other path is 404, whatever it contains (`..`, `%2e%2e`, backslashes, drive letters) | `test_no_path_reaches_anything_else` |
| Framing | `frame-ancestors 'none'` in the page's policy header | `test_the_page_is_the_hosted_app_plus_the_token_and_local_js` |
| A weakened page policy | The page is openppc.si's with one change, `connect-src 'self'`; if the hosted policy changes, the server stops rather than serve a page that half works | `test_a_change_to_the_hosted_policy_stops_it` |
| Exhaustion | Bodies up to 20 MB, read only from the token's holder; one job at a time (another gets 409) and the last 4 finished kept; an idle connection is dropped after 30 seconds; threads are daemons | `test_one_run_at_a_time_and_stop_keeps_what_was_crawled`, `test_the_last_four_finished_runs_are_kept` |
| Contacting other hosts | Only `app.py` imports the HTTP server, and serving the app connects to nothing but 127.0.0.1. A job connects as `openppc-online site` does, through its guard | `test_only_the_named_modules_touch_the_network`, `test_the_app_contacts_only_127_0_0_1` |

## Accepted

- **Another program or user on this computer** can load the page and so read the token. It can only do what the
  page can, which now includes starting a site audit from this computer (with "allow private addresses", of your
  network), and see the last 4 results. Anything running as you can already do both. On a shared computer, stop
  the app when you are done.
- **Stop is not instant.** It takes effect at the run's next progress line, so a page that is slow to answer
  finishes first.
- **The page loads its Python runtime, two libraries and its fonts from cdn.jsdelivr.net,** as openppc.si does,
  each pinned by version. The libraries, the fonts and the runtime's entry file are checked against hashes; the
  files the runtime loads after that are not.

# `openppc-online site`

The crawler fetches pages a stranger controls, from your computer, inside your network; with `--render`, a real
browser runs their JavaScript. The tests are in `tests/test_net.py`, `tests/test_crawl.py`, `tests/test_site.py`,
`tests/test_checks.py`, `tests/test_packs.py`, `tests/test_render.py` and, in Chromium, `tests/test_render_e2e.py`.

## What it has

- **Your network.** The crawler runs inside it, so a site could try to point it at your router, a staging server
  or a cloud machine's metadata service, which hands out credentials.
- **Your CrUX API key** (`--crux-key`) and **your webhook's URL** (`--post-to`), whose path is often its secret.
- **Your computer's resources.** Memory, disk and time.
- **Whoever reads the report.** It quotes URLs and some text from the site, and the HTML report opens in a
  browser.

## Who might attack it

1. **The site being checked,** or any site it links to: its pages, headers, redirects, robots.txt and sitemaps.
2. **Its DNS,** answering with a private address, or a public one first and a private one later (DNS rebinding).
3. **A rule pack or baseline file** from someone else. They are files you choose, so they are trusted to say what
   to check, but not to run code or slow the check down.

## Defences

| Threat | Defence | Test |
| --- | --- | --- |
| Reaching your network | Every address a name resolves to is checked; private, loopback and unique-local ones need `--allow-private`; link-local, cloud metadata, CGNAT, multicast, reserved and tunnelled ones (6to4 and IPv4-mapped are checked as the IPv4 inside) never open | `test_which_addresses_open_and_when`, `test_localhost_needs_allow_private`, `test_this_computer_needs_allow_private` |
| A name with one private address among public ones | Refused as a whole | `test_a_name_with_one_private_address_among_public_ones_is_refused` |
| DNS rebinding | Each connection resolves the name once and connects to the checked address, not the name | `test_a_name_is_resolved_once_per_connection_and_connected_by_the_checked_address` |
| A redirect into your network | Redirects are followed by hand, at most 10, http and https only, each hop checked the same way | `test_a_redirect_to_the_metadata_address_is_refused`, `test_too_many_redirects_and_other_schemes_are_no_response` |
| Contacting hosts it doesn't declare | Only `siteaudit/net.py` makes connections, and only `siteaudit/crux.py` uses `urllib`; a run looks up the site, the hosts it links to, CrUX's host only with `--crux-key` and the webhook's only with `--post-to` | `test_only_the_named_modules_touch_the_network`, `test_the_command_contacts_only_its_declared_hosts` |
| A compressed bomb or an endless body | Bodies are cut off at 5 MB after decompression, 30 seconds per response, 15 seconds of silence; only HTML bodies are read when the crawler asks for pages | `test_a_compressed_bomb_is_cut_off`, `test_only_html_bodies_are_read_when_asked`, `test_a_body_that_fails_part_way_is_no_response` |
| XML attacks in sitemaps | A sitemap with a document type declaration (entities) is not read; sitemaps are capped in size and number | `test_a_sitemap_with_a_document_type_declaration_is_not_read` |
| An endless site | Pages per URL pattern and per query string are capped, and `--max-pages` and `--max-time` stop it; Ctrl-C keeps what was crawled | `test_the_page_limit_and_a_429_retried_once`, `test_ctrl_c_keeps_what_was_crawled` |
| Being turned against the site | robots.txt is read first and obeyed, Crawl-delay included; two requests at a time, half a second apart, unless `--fast`; a 429 is retried once, then left | `test_robots_txt_is_read_as_rfc_9309_says`, `test_robots_txt_is_read_before_the_start_page`, `test_a_failing_robots_txt_stops_the_crawl` |
| Sessions and tracking | No cookies are kept or sent; the user agent says who asks | `test_cookies_are_never_kept_and_the_user_agent_says_who_asks` |
| The site's text as markup | URLs are percent-encoded; anything else from the site (a rule pack's quoted field, an error) goes in a code span with its backticks replaced, so it can't close the span; the HTML report escapes all text | `test_the_sites_own_text_never_becomes_markup_in_the_report` |
| Leaking the CrUX key or the webhook's path | The key is read from the flag or `OPENPPC_CRUX_KEY` and only sent to CrUX; reports and messages name the webhook's host only; secret-looking query values (tokens, emails) are masked in every format | `test_secrets_never_show`, `test_field_data_is_read_and_the_key_stays_out_of_sight`, `test_fingerprints_ignore_the_origin_and_secrets_are_masked` |
| A webhook that sends the result on | `https://`, or `http://` only to this computer (which also needs `--allow-private`); one POST through the guard, no redirect followed | `test_which_webhook_addresses_are_taken`, `test_the_webhook_follows_no_redirect_and_needs_allow_private_for_this_computer` |
| A hostile rule pack | Plain JSON, every key and value checked as it loads; a rule compares a field with a literal (no regular expressions, no code), and page globs use `fnmatch`, so a pack can't run anything or hang the check | `test_a_pack_mistake_names_the_place`, `test_the_example_rule_packs_match_the_schema_and_load` |
| A slow failure | Every input (packs, baseline, key, webhook, limits, `--render-url`, the screenshots folder, the browser starting) is read before the crawl | `test_bad_input_fails_before_the_crawl` |
| The browser reaching your network | Chromium's only route out is a proxy on 127.0.0.1 that opens each connection through the same guard, loopback included; a refused one answers 403 | `test_the_browsers_proxy_applies_the_same_rules`, `test_the_browsers_proxy_never_opens_the_metadata_address`, `test_the_browser_is_held_to_the_same_address_rules` |
| The browser going around the proxy | QUIC off, WebRTC's non-proxied UDP off, service workers blocked, downloads refused, a new profile per page | `test_the_browser_pass_sees_tags_consent_accessibility_and_vitals` (the only names resolved are the site's and its pages' hosts) |
| A proxied connection reused for another host | One request per upstream connection for plain HTTP; a `CONNECT` tunnel is opened to the checked address only | `test_the_browsers_proxy_applies_the_same_rules` |
| A tampered axe-core | The vendored file is pinned by its SHA-256, the one npm publishes; it runs through the DevTools protocol, so the page's policy can't block it, and only its results come back | `test_the_vendored_axe_core_is_the_published_file_with_its_license` |
| `--render-url` pointing elsewhere | Must be a page of the site you named | `test_bad_input_fails_before_the_crawl` |

## Accepted

- **The site sees your IP address,** as with any visit, and so does each host it links to (once per link). Use
  `--no-external` to skip those.
- **`--allow-private` trusts the names you check.** With it, a public site's link or redirect may reach your own
  network; use it only on hosts you trust.
- **`--fast` ignores the polite pace,** not robots.txt. It is for your own site.
- **The CrUX key goes to Google,** as the API needs. Use a key restricted to the Chrome UX Report API.
- **The browser runs the site's JavaScript,** in Chromium's sandbox, with a fresh profile per page. A Chromium
  exploit is out of scope; keep Playwright's Chromium updated (`playwright install chromium`).
- **The proxy has no password.** While the browser pass runs, another program on this computer could connect to
  it, but it reaches only what the guard allows, which that program could reach directly.
- **Screenshots show what the page shows,** which may include personal data on a logged-out page. They are saved
  only with `--screenshots`, where you say.

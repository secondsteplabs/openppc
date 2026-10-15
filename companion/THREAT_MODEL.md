# Threat model: `openppc-online`

What each part protects, from whom, and how: the local server (`app`) first, then the website check (`site`), the
downloads (`fetch`), the Tag Inspector browser extension and the WordPress plugin. Each defence has a test in `tests/`. Review this page, and run a security
review of the diff, before each release that changes any of them.

# `openppc-online app`

## What it has

- **The page's token.** A new random value each run (32 bytes, URL-safe). Every call to `/api/` needs it in the
  `X-OpenPPC-Token` header. With it, a page can start a site audit or a download from this computer.
- **The job API.** `POST /api/jobs` starts a site audit (`openppc-online site`, with everything in that section
  below) or a download (`openppc-online fetch`, likewise), `GET /api/jobs/<id>` shows it, and
  `POST /api/jobs/<id>/stop` stops it. A site audit may carry a CrUX key, rule packs and a baseline, uploaded from
  the page; results stay in memory, the last 4 finished, and nothing is written to disk.
- **Ad platform credentials.** A download's API credentials, typed into the page, are in the request and in that
  job's memory while it runs.
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
| A job doing what the form didn't say | Every field is checked before a job starts: known names only, types and the command's limits; `--post-to`, `--screenshots`, `--out` and `--force` aren't offered, so a job sends no result to a third host and writes no file; a download's credentials must be its platform's own names | `test_every_field_is_checked_before_anything_runs`, `test_every_download_field_is_checked_before_anything_runs` |
| Uploaded file names | Base name only, at most 100 characters, without control characters or backticks; the file is read from memory, never saved, so no path reaches the report or an error | `test_a_site_audit_runs_as_a_job_and_comes_back_in_every_format` |
| The audited site's text in the app's page | The Site and Download views (`local/site.js`, `local/fetch.js`) build their page as text nodes and write no markup themselves; the report goes through the app's own renderer, which shows any HTML in it as text and sanitizes the rest (DOMPurify), and the site's text is in code spans or escaped already | `test_the_view_writes_no_markup_of_its_own`, `test_the_sites_own_text_never_becomes_markup_in_the_report` |
| The CrUX key leaking | It arrives in the request body and goes to the run only; no job view, progress line, error or report carries it | `test_the_crux_key_goes_to_the_run_and_never_comes_back` |
| The PageSpeed Insights key leaking | The same: the request body, then the run only | `test_psi_and_one_page_only_reach_the_run_and_the_psi_key_never_comes_back` |
| Asking Google without meaning to | The quick check's two buttons decide each run on their own and change no tick, so a PageSpeed run never carries over; "Check on this computer only" drops a typed PSI key, since a key alone would ask Google. Re-check repeats the last run exactly as sent | `test_the_quick_check_with_pagespeed_shows_its_score_on_the_summary` |
| The agency name on the summary | Typed into the page and never sent to the server or kept; at most 80 characters, control characters removed, written as a text node | `test_the_site_view_audits_downloads_stops_and_steps_aside`, `test_the_view_writes_no_markup_of_its_own` |
| The summary misreporting the report | It is built from the run's own JSON and adds no number; Performance is a gauge only when it is a Lighthouse speed score, never the rough estimate from lab loads here | `test_the_site_view_audits_downloads_stops_and_steps_aside`, `test_the_quick_check_with_pagespeed_shows_its_score_on_the_summary` |
| A download's credentials leaking or staying | They arrive in the request body and go to that job only, never to the environment; no job view, progress line, error or result carries them, and they are cleared when the job ends, finished, failed or stopped | `test_a_download_comes_back_as_the_files_and_their_templates`, `test_a_failure_is_explained_without_any_credential`, `test_the_credentials_are_dropped_when_the_download_ends` |
| Another site reading the token | The token is only in the page, which another origin can't read; `Cross-Origin-Resource-Policy: same-origin` on every answer | `test_the_apps_files_are_served` |
| Guessing the token | 32 random bytes per run, compared in constant time, as bytes (a header that isn't ASCII is refused, not an error) | `test_the_api_needs_this_runs_token` |
| Token leaks | Never in a URL (the address printed and opened has none), a log line (the server logs no requests), a header, or any answer but the page; `Referrer-Policy: no-referrer`; the page is `Cache-Control: no-store` | `test_the_token_is_only_ever_in_the_page`, `test_serve_says_where_without_the_token_and_takes_another_port_if_needed` |
| Path traversal and listings | A fixed map of the app's files, read at start; any other path is 404, whatever it contains (`..`, `%2e%2e`, backslashes, drive letters) | `test_no_path_reaches_anything_else` |
| Framing | `frame-ancestors 'none'` in the page's policy header | `test_the_page_is_the_hosted_app_plus_the_token_and_local_js` |
| A weakened page policy | The page is openppc.si's with one change, `connect-src 'self'`; if the hosted policy changes, the server stops rather than serve a page that half works | `test_a_change_to_the_hosted_policy_stops_it` |
| Exhaustion | Bodies up to 20 MB, read only from the token's holder; one job at a time (another gets 409) and the last 4 finished kept; an idle connection is dropped after 30 seconds; threads are daemons | `test_one_run_at_a_time_and_stop_keeps_what_was_crawled`, `test_one_job_at_a_time_and_stop_ends_a_download_with_nothing`, `test_the_last_four_finished_runs_are_kept` |
| Contacting other hosts | Only `app.py` imports the HTTP server, and serving the app connects to nothing but 127.0.0.1. A job connects as `openppc-online site` or `openppc-online fetch` does, through its guard or its allowlist | `test_only_the_named_modules_touch_the_network`, `test_the_app_contacts_only_127_0_0_1` |

## Accepted

- **Another program or user on this computer** can load the page and so read the token. It can only do what the
  page can, which now includes starting a site audit from this computer (with "allow private addresses", of your
  network), and see the last 4 results. Anything running as you can already do both. A download needs
  credentials, which the page's form keeps only until a download succeeds or the page closes, and a finished job
  no longer has. On a shared
  computer, stop the app when you are done.
- **Re-check keeps the last run in the page's memory,** keys included, until the page closes or reloads, as the
  form's own fields do. Nothing is written to the browser's storage.
- **Credentials typed into a page** can be read by what runs in that browser: its extensions, and a password
  manager that offers to save them. Use a browser profile you trust, or the command with environment variables.
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
- **Your CrUX API key** (`--crux-key` or `OPENPPC_CRUX_KEY`), **your PageSpeed Insights key** (`--psi-key` or
  `OPENPPC_PSI_KEY`) and **your webhook's URL** (`--post-to`), whose path is often its secret.
- **The addresses of the pages you measure with `--psi`,** which go to Google.
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
| Contacting hosts it doesn't declare | Only `siteaudit/net.py` makes connections, CrUX's and PageSpeed Insights' included, so they all pass the guard and its size and time limits; a run looks up the site, the hosts it links to, CrUX's host only with `--crux`, PageSpeed Insights' only with `--psi` and the webhook's only with `--post-to` | `test_only_the_named_modules_touch_the_network`, `test_the_command_contacts_only_its_declared_hosts`, `test_psi_contacts_only_its_declared_host_and_the_key_never_shows` |
| Sending Google a page it shouldn't see | `--psi` checks every page before anything is sent: it refuses `--allow-private`, a host that doesn't resolve to public addresses only, an address with a secret-looking query value (refused, not stripped, since PSI would measure another page), and more than 5 pages. It asks Google only once robots.txt is read and the start page has answered, and leaves out any page robots.txt keeps OpenPPC out of | `test_psi_refuses_what_it_cant_measure_before_sending_anything`, `test_psi_is_never_sent_a_page_robots_txt_keeps_openppc_out_of` |
| A huge or slow answer from PageSpeed Insights | Its own limits: 20 MB and 120 seconds a call, at most 2 calls at a time; an answer that isn't a Lighthouse report is an error on that page, not the run. After a stop, no call starts and none is retried; the at most 2 already sent finish on their own | `test_psi_is_asked_through_the_guard_with_the_key_in_a_header`, `test_a_stop_starts_no_more_psi_calls`, `test_a_malformed_answer_is_an_error_on_that_page` |
| A key quoted in an error | A PSI or CrUX key with anything but letters, digits, `-` and `_` is refused before anything is sent, so an error can't quote it in an escaped form the redaction misses | `test_a_key_with_a_line_break_is_refused` |
| A compressed bomb or an endless body | Bodies are cut off at 5 MB after decompression, 30 seconds per response, 15 seconds of silence; only HTML bodies are read when the crawler asks for pages | `test_a_compressed_bomb_is_cut_off`, `test_only_html_bodies_are_read_when_asked`, `test_a_body_that_fails_part_way_is_no_response` |
| XML attacks in sitemaps | A sitemap with a document type declaration (entities) is not read; sitemaps are capped in size and number | `test_a_sitemap_with_a_document_type_declaration_is_not_read` |
| An endless site | Pages per URL pattern and per query string are capped, and `--max-pages` and `--max-time` stop it; Ctrl-C keeps what was crawled | `test_the_page_limit_and_a_429_retried_once`, `test_ctrl_c_keeps_what_was_crawled` |
| Being turned against the site | robots.txt is read first and obeyed, Crawl-delay included; two requests at a time, half a second apart, unless `--fast`; a 429 is retried once, then left | `test_robots_txt_is_read_as_rfc_9309_says`, `test_robots_txt_is_read_before_the_start_page`, `test_a_failing_robots_txt_stops_the_crawl` |
| Sessions and tracking | No cookies are kept or sent; the user agent says who asks | `test_cookies_are_never_kept_and_the_user_agent_says_who_asks` |
| The site's text as markup | URLs are percent-encoded; anything else from the site (a rule pack's quoted field, an error) goes in a code span with its backticks replaced, so it can't close the span; the HTML report escapes all text | `test_the_sites_own_text_never_becomes_markup_in_the_report` |
| Leaking the CrUX key or the webhook's path | The key is read from `--crux-key` or `OPENPPC_CRUX_KEY` and sent only to CrUX, in a header that never follows a redirect; reports and messages name the webhook's host only; secret-looking query values (tokens, emails) are masked in every format | `test_secrets_never_show`, `test_field_data_is_read_through_the_guard_and_the_key_stays_out_of_sight`, `test_a_call_carries_its_own_headers_and_body_to_its_first_address_only`, `test_fingerprints_ignore_the_origin_and_secrets_are_masked` |
| Leaking the PageSpeed Insights key | Read from `--psi-key` or `OPENPPC_PSI_KEY`, sent only to PageSpeed Insights in the `X-Goog-Api-Key` header, never in a URL, with no redirect followed; an error that quotes it shows `<key>` instead | `test_psi_is_asked_through_the_guard_with_the_key_in_a_header`, `test_psi_contacts_only_its_declared_host_and_the_key_never_shows` |
| A webhook that sends the result on | `https://`, or `http://` only to this computer (which also needs `--allow-private`); one POST through the guard, no redirect followed | `test_which_webhook_addresses_are_taken`, `test_the_webhook_follows_no_redirect_and_needs_allow_private_for_this_computer` |
| A hostile rule pack | Plain JSON, every key and value checked as it loads; a rule compares a field with a literal (no regular expressions, no code), and page globs use `fnmatch`, so a pack can't run anything or hang the check | `test_a_pack_mistake_names_the_place`, `test_the_example_rule_packs_match_the_schema_and_load` |
| A slow failure | Every input (packs, baseline, key, webhook, limits, `--render-url`, the screenshots folder, the browser starting) is read before the crawl | `test_bad_input_fails_before_the_crawl` |
| The browser reaching your network | Chromium's only route out is a proxy on 127.0.0.1 that opens each connection through the same guard, loopback included; a refused one answers 403 | `test_the_browsers_proxy_applies_the_same_rules`, `test_the_browsers_proxy_never_opens_the_metadata_address`, `test_the_browser_is_held_to_the_same_address_rules` |
| The browser going around the proxy | QUIC off, WebRTC's non-proxied UDP off, service workers blocked, downloads refused, a new profile per page | `test_the_browser_pass_sees_tags_consent_accessibility_and_vitals` (the only names resolved are the site's and its pages' hosts) |
| Chromium calling home from your computer | Its own traffic (update checks, sign-in, push) goes to a sink on 127.0.0.1 that refuses every request before resolving a name and lists the hosts; each page's proxy is set per profile. The calls a profile makes to Google itself are turned off (the search preconnect) or sent to a name under `.invalid` (the AI Mode check), which the guard refuses without a lookup | `test_the_browser_pass_sees_tags_consent_accessibility_and_vitals`, `test_a_name_under_invalid_is_refused_without_a_lookup` |
| Measuring pollutes the site's analytics | The Web Vitals loads answer every tag hit `signatures.json` knows with an empty 204 on this computer (Chrome's `Fetch` domain, patterns built from the signatures, decided by `is_hit`); a page's own document is never answered, and any error lets the request through rather than hang the load. Only the page's own requests: another site's frame and workers are other targets, so a tag in one still sends its hit, and the report says so | `test_every_tag_hit_is_caught_during_speed_loads`, `test_ordinary_files_and_tag_scripts_load_untouched`, `test_the_browser_pass_sees_tags_consent_accessibility_and_vitals` |
| A page reaching the browser's DevTools port | Opened only when Lighthouse attaches to OpenPPC's browser (the calibration and `--lighthouse`), on 127.0.0.1, a port Chrome picks, never with `--remote-allow-origins`. The guard refuses that port on loopback even with `--allow-private`, so no page reaches it through the proxy. Lighthouse's load goes through the page's proxy like OpenPPC's own, but it fires the page's tags | `test_a_closed_port_is_refused_on_loopback_even_with_allow_private`, `test_lighthouse_measures_through_the_guard_and_the_devtools_port_stays_shut`, `test_the_lighthouse_switch_measures_the_page_on_a_phone_and_a_desktop_and_checks_budgets`, `test_the_calibrations_way_around_the_guard_stays_in_the_tests` |
| `--lighthouse` running for an hour, or not being Lighthouse | At most 5 pages, two runs each, one at a time, each stopped after 300 seconds; the folder must hold a package named `lighthouse` at major version 13 with its `core/index.js`, checked before the crawl, along with Node and the browser | `test_lighthouse_needs_its_folder_and_isnt_mixed_with_psi`, `test_a_failed_run_says_why_and_closes_its_context` |
| A budget in a rule pack doing more than compare | A budget is numbers against named lines; an unknown line, a negative number or a score over 100 is refused with its place in the file | `test_a_budget_mistake_names_the_place` |
| Starting another program | Only `lab/lighthouse.py` starts one: Node itself (a `.cmd` or `.bat` shim is refused, since cmd.exe re-reads its arguments), with a list of arguments and no shell, for at most 300 seconds | `test_only_the_named_modules_touch_the_network`, `test_a_node_script_is_refused`, `test_a_run_attaches_to_a_marked_page_behind_the_proxy` |
| A proxied connection reused for another host | One request per upstream connection for plain HTTP; a `CONNECT` tunnel is opened to the checked address only | `test_the_browsers_proxy_applies_the_same_rules` |
| A tampered axe-core | The vendored file is pinned by its SHA-256, the one npm publishes; it runs through the DevTools protocol, so the page's policy can't block it, and only its results come back | `test_the_vendored_axe_core_is_the_published_file_with_its_license` |
| A tampered trace engine, or one that reaches out | The vendored file is pinned by its SHA-256, and the calibration workflow rebuilds it from the lockfile and compares; it runs in a blank page of its own with no site loaded and no proxy of its own, so anything it fetched would go to the sink that refuses everything; it gets the trace of one load and gives back each insight's result (titles, savings, file addresses) and each file's cost, which the report redacts as it does everything else | `test_the_vendored_trace_engine_is_the_pinned_build_with_its_licences`, `test_the_engines_answer_becomes_insights_failing_first`, `test_the_engines_costs_come_back_per_tag` |
| A page's script errors carrying markup or a secret into the report | At most 10 a page, each on one line and cut to 200 characters; shown in a code span whose backticks are replaced, so it can't close or carry markup; secret-looking values in any URL in it are masked in the report and the JSON, as everywhere else. Accepted: other text a page's own script prints in an error is the site's, shown as it is | `test_what_a_browser_pass_saw_becomes_findings`, `test_the_browser_pass_sees_tags_consent_accessibility_and_vitals` |
| `--render-url` pointing elsewhere | Must be a page of the site you named | `test_bad_input_fails_before_the_crawl` |

## Accepted

- **The site sees your IP address,** as with any visit, and so does each host it links to (once per link). Use
  `--no-external` to skip those.
- **`--allow-private` trusts the names you check.** With it, a public site's link or redirect may reach your own
  network; use it only on hosts you trust.
- **`--fast` ignores the polite pace,** not robots.txt. It is for your own site.
- **The ad-parameter check looks like an ad click to the server.** The start page is asked for once with `gclid`
  and the other click IDs set to `OPENPPC-TEST`, so the site's logs, and a CRM that reads them on the server, may
  record that value. No browser runs it, so no tag fires and no ad platform sees it. With `--render`, Chromium loads
  it too: there the tags run, and their hits, and every request from any frame or worker that carries the test value
  to a host other than the site's, are answered on this computer (`test_a_script_that_drops_the_click_id_and_a_banner_that_pushes_the_page_are_found`).
  Accepted: a server-side tag endpoint on the site's own host that `signatures.json` doesn't know gets the value,
  like the rest of the site's server, and could pass it on.
- **The CrUX key goes to Google,** as the API needs. Use a key restricted to the Chrome UX Report API.
- **`--psi` tells Google which pages you measure,** and Google loads them from its servers, as pagespeed.web.dev
  does; their tag hits are real visits from Google's machines, which this check can't answer for it. A PSI key
  goes to Google too: restrict it to the PageSpeed Insights API.
- **`--lighthouse` runs the Lighthouse in the folder you give,** as Node, with your account's rights: OpenPPC checks
  it is named and versioned as Lighthouse 13, not what its code does. Install it from npm yourself. Its loads are
  real visits from your computer: the page's tag hits reach its analytics and ad accounts, as PageSpeed Insights'
  do from Google's.
- **PageSpeed Insights' answer is trusted as Google's.** It is read as data only (numbers, titles and links shown
  as text or in code spans), never run, so a wrong answer can mislead the report but not reach your computer.
- **The browser runs the site's JavaScript,** in Chromium's sandbox, with a fresh profile per page. A Chromium
  exploit is out of scope; keep Playwright's Chromium updated (`playwright install chromium`).
- **The proxy has no password.** While the browser pass runs, another program on this computer could connect to
  it, but it reaches only what the guard allows, which that program could reach directly.
- **Screenshots show what the page shows,** which may include personal data on a logged-out page. They are saved
  only with `--screenshots`, where you say.

# `openppc-online fetch`

Downloads an ad account's reports through Google's, Microsoft's or Meta's API, with credentials you made, and
writes them as the files `openppc audit` reads. The same code runs for the app's Download view. The tests are in
`tests/test_fetch_http.py`, `tests/test_fetch_google.py`, `tests/test_fetch_microsoft.py`,
`tests/test_fetch_meta.py` and `tests/test_fetch_command.py`, against fakes of each API built from its
documentation.

## What it has

- **Your API credentials.** Developer tokens, OAuth client secrets and refresh tokens, and Meta access tokens. Most
  can change the account as well as read it, so they matter more than the reports.
- **The account's numbers:** spend, conversions, search terms, campaign names.
- **Your files.** It writes into the `--out` folder.

## Who might attack it

1. **An API answer,** or a fault in one: an error that quotes what was sent, a redirect, a download address
   elsewhere, a next page on another list, an answer too big, or a zip that isn't one report.
2. **Anyone who sees what the command prints** or what it writes: a terminal shared on a call, a CI log, a
   ticket the files are attached to.
3. **A mistyped or crafted argument:** an account ID or conversion name that would change a query or a path.

## Defences

| Threat | Defence | Test |
| --- | --- | --- |
| Calling anything else, or changing the account | Each platform has a list of the method, host and path of every call it may make, checked before connecting, https on port 443 only; Google's queries are SELECTs on searchStream, Microsoft's calls only submit and poll reports, and Meta's are GETs | `test_each_platform_may_make_only_its_reviewed_calls`, `test_anything_else_is_refused_before_connecting`, `test_every_query_only_reads_and_none_mixes_keywords_into_performance_max` |
| Contacting hosts it doesn't declare | Of fetch's modules, only `fetch/http.py` imports `urllib.request`, and every call goes through its one opener, which follows no redirect | `test_only_the_named_modules_touch_the_network`, `test_no_redirect_is_followed` |
| Microsoft's download address | Microsoft names a new one per report, so it is let through once, for one GET, only if it is https on port 443 on a host name (not an IP address) without a user name; it carries no credential | `test_a_download_address_must_be_https_on_a_host_name`, `test_a_download_address_the_api_gave_is_called_once_with_get`, `test_the_download_carries_no_credential_and_is_made_once`, `test_a_download_address_that_isnt_https_on_a_host_name_is_never_called` |
| Meta's next page | Followed only on the same list's path, through the allowlist, with any `access_token` taken out of its address | `test_a_next_page_on_another_list_is_not_followed`, `test_a_next_page_on_another_host_is_refused_by_the_gate` |
| A token in an address | Meta's token goes in the `Authorization` header, never the URL, so it stays out of proxy and server logs | `test_every_call_is_a_get_with_the_token_in_a_header_never_the_address` |
| Credentials leaking | Read from environment variables (or the app's request), never from flags or shell history; never in a file, the output or an error; an API's error shows only its codes (names like `RESOURCE_EXHAUSTED`), never its free text, which could quote the request | `test_no_credential_reaches_the_files` (each platform), `test_a_failure_shows_no_credential_and_writes_nothing`, `test_only_error_codes_are_shown_never_free_text`, `test_a_failure_keeps_its_body_out_of_the_message`, the three `..._errors_say_what_to_do_without_echoing_the_answer` |
| An argument changing a query or path | Account IDs must be digits (Google's 10, with or without dashes; Meta's with or without `act_`), Microsoft's customer ID too, and Meta's conversion a name like `lead` (letters, digits, `_` and `.`), all before any call | `test_anything_else_is_not_a_customer_id`, `test_anything_else_is_not_an_account_id` (Microsoft and Meta), `test_a_customer_id_that_isnt_digits_is_refused_before_any_call`, `test_a_conversion_that_isnt_an_action_type_is_refused_before_any_call` |
| An answer too big, or a zip bomb | Answers are read up to 200 MB and error bodies up to 64 KB; Microsoft's zip must hold one file, whose size is checked before it is unzipped | `test_a_report_too_big_unzipped_is_never_read`, `test_a_download_that_isnt_one_zipped_report_is_refused` |
| A run that never ends | 120 seconds per call; Microsoft's polls wait 2 seconds, then longer, to 30, and give up after 10 minutes; Meta reads at most 200 pages of a list | `test_polls_wait_longer_each_time`, `test_a_report_that_never_finishes_is_given_up_on` |
| Writing elsewhere, or half a set | Fixed file names only, inside `--out`, which is checked before connecting; nothing is written until every report is in; each file is written whole, then renamed; a file already there is replaced only with `--force` | `test_files_are_written_only_under_their_names_and_whole`, `test_a_failure_part_way_writes_none_of_the_files`, `test_files_already_in_out_stop_it_before_connecting` |
| An API version past its sunset | Each version and its sunset date are in `fetch/versions.py`; the command warns within 60 days of it, and a test fails within 60 days, so a release can't ship an expiring one | `test_a_version_near_its_sunset_is_said_after_the_files`, `test_no_api_version_is_near_its_sunset` |

## Accepted

- **The credentials can do more than it does.** Google's and Microsoft's OAuth scopes and Meta's `ads_read` are
  the narrowest the APIs offer for reports, but Google's and Microsoft's also allow changes. The code never makes
  one; a token you create for this alone limits what a leak could do.
- **The files hold what searchers typed.** A search term can start with `=` or `+`, which a spreadsheet may read
  as a formula, as in the platform's own exports. `openppc audit` reads them as text; open them in a spreadsheet
  with that in mind.
- **The fakes are built from each API's documentation,** not recorded from real accounts. A change in an API that
  its documentation doesn't show yet surfaces as an error that names its codes.
- **Meta's Bearer header** rests on Graph API practice and its SDKs rather than a page of Meta's that says so in
  words; the token in the address would also work, but would reach logs.

# The Tag Inspector extension

It runs in your browser, on pages you are already looking at, and reads one when you click it. The tests are in
`tests/test_extension.py` (which runs `tests/js/extension.test.mjs` in Node), `tests/test_tag_cases.py` and, in
Chromium, `tests/test_extension_e2e.py`.

## What it has

- **The page you're on,** which may be private (an account page), and the addresses it loaded, which may carry
  IDs.
- **Your browser.** An extension with broad permissions could read every site you visit.
- **Whoever reads the popup.**

## Who might attack it

1. **The page being read.** Its scripts share the world the dataLayer is read from, so they can answer with
   anything, including text meant to become markup.
2. **A later change to the extension** that gains a way to send data or to read more than you asked it to.

## Defences

| Threat | Defence | Test |
| --- | --- | --- |
| Reading pages you didn't ask it to | `activeTab` and `scripting` only: no host permissions, content scripts or background worker. It reads a tab only when you click, and only that tab's page, not its frames | `test_the_extension_asks_for_the_least` |
| Sending what it reads | No network permission, and no XHR, beacon, WebSocket, EventSource or outside `fetch` in its code; its pages may load only their own files; it stores nothing | `test_the_extension_has_no_way_to_send_or_inject_anything`, `test_the_inspector_reads_a_shop_and_sends_nothing` (every request the browser made was the page's own) |
| A page answering with nonsense or too much | Strings only, each cut to size; at most 3,000 addresses, 200 events and 20 consent commands | `a reading keeps what a page sends back in shape and in size`, `a page whose world can't be read, or that answers nonsense, still gives a reading` (Node) |
| The page's text as markup | The popup builds text nodes only, with no `innerHTML` or `eval`, and its HTML runs `popup.js` alone | `test_the_popup_runs_only_its_own_scripts`, `test_the_inspector_reads_a_shop_and_sends_nothing` (a page event that is an `<img>` tag shows as text) |
| A page changing the reading code | The addresses and page basics are read in the extension's isolated world, whose functions page scripts can't replace | Chrome's isolated worlds |
| Rules drifting from the crawler's | The same `signatures.json`, and one set of cases both matchers must pass | `test_the_extension_knows_the_crawlers_tags`, `test_tag_cases.py`, `the matcher gives tags.py's answers` (Node) |

## Accepted

- **A page can misreport itself.** It can clear its list of addresses or fake its dataLayer, so a reading is the
  page's own account. `openppc-online site --render` watches the traffic instead.
- **Not everything shows:** the first 250 addresses unless the page asks the browser to keep more, nothing from
  other sites' frames, and no events that only a POST body names.
- **It isn't in a store yet.** Load it from this folder, so the code you run is the code you can read here.

# The WordPress plugin

OpenPPC Site Check runs inside a WordPress site, as PHP with the site's own rights, and adds five checks to Site
Health. The tests are in `tests/php/site_check_test.php` (WordPress stubbed out; `tests/test_wordpress.py` runs
it), `tests/test_tag_cases.py`, and the CI job that runs WordPress's coding standards.

## What it has

- **The site's rights.** Any plugin's code runs with them, so a flaw in it is a flaw in the site.
- **The home page and robots.txt,** as the site serves them.
- **Whoever reads Site Health,** usually an administrator.

## Who might attack it

1. **Whoever controls the site's pages:** an author, another plugin or a compromised theme can put any text in the
   HTML the plugin reads, including markup meant for the admin screen.
2. **Someone without admin rights** asking for the checks through REST, to make the site fetch pages for them.
3. **A redirect** that sends the plugin's request somewhere else.

## Defences

| Threat | Defence | Test |
| --- | --- | --- |
| Fetching anything but its own site | Two addresses only, the home page and `/robots.txt` from `home_url()`, each once per request, at most 10 seconds and 2 MB, and no redirect followed (a redirect is reported, not taken) | `each page is fetched once, only from this site, following no redirect, at most 2 MB`, the `redirect` case |
| Others running the checks | The four checks that read a page answer over REST only to users who can `view_site_health_checks`; the other runs inside Site Health | `answers whoever may see Site Health`, `refuses whoever may not see Site Health` |
| The page's text as markup | Every description and action is escaped with `esc_html` before Site Health shows it, and the address a redirect names too | `descriptions are escaped`, the `redirect` case |
| A page made to stall a pattern | PCRE's backtracking limit applies; a pattern that gives up counts as no match | `a pattern that gives up counts as no match` |
| Rules drifting from the crawler's | The same `signatures.json`, read the way PHP's PCRE reads it (ASCII), and the `in_text` cases both must pass | `test_the_plugin_knows_the_crawlers_tags`, `test_in_text`, `in_text(...)` (PHP) |
| A change that slips past WordPress's rules | WordPress-Extra and PHPCompatibility for PHP 7.4 and later in CI, with every package pinned; Plugin Check 2.1.0 found no errors | the `wordpress` CI job |

## Accepted

- **Certificates on its own address** are checked only as Site Health checks them: `sslverify` follows core's
  `https_local_ssl_verify` filter, off by default. The plugin talks only to the site it runs on.
- **It reads HTML, not a browser.** Tags a page adds with JavaScript, and whether any tag waits for consent, show
  only in `openppc-online site --render`, which each check names.
- **It reads one page.** Other pages may differ.

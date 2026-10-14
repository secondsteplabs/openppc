"""`openppc-online app`'s job API: a site audit started by its own page, and nothing read from anyone else
(THREAT_MODEL.md, "The job API")."""
import json
import time

import pytest
from conftest import ask
from sites import acme, page

from openppc_online import app, site

SUPPRESS = {"openppc_site": 1, "suppress": [{"rule": "site-broken-internal", "reason": "Known."}]}


def _post(server, path, body, headers=None):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    status, got, out = ask(server, path, method="POST", body=raw,
                           headers={app.TOKEN_HEADER: server.token, "Content-Type": "application/json",
                                    "Origin": f"http://127.0.0.1:{server.port}", **(headers or {})})
    return status, got, json.loads(out) if out.startswith(b"{") else out


def _job(server, job_id, until=lambda v: v["state"] != "running", seconds=60):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        status, _, out = ask(server, f"/api/jobs/{job_id}", headers={app.TOKEN_HEADER: server.token})
        view = json.loads(out)
        if status != 200 or until(view):
            return view
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} still running")


def _site(base, **more):
    return {"kind": "site", "url": base, "allow_private": True, "fast": True, "external": False, **more}


def test_a_site_audit_runs_as_a_job_and_comes_back_in_every_format(server, serve):
    base = serve(acme)
    pack = {"name": "C:\\Users\\me\\rules`\x07.json", "text": json.dumps(SUPPRESS)}
    baseline = {"name": "../last.json", "text": json.dumps({"findings": []})}
    status, _, view = _post(server, "/api/jobs", _site(base, configs=[pack], baseline=baseline))
    assert status == 202 and view["state"] == "running"
    done = _job(server, view["id"])
    assert done["state"] == "done", done
    result = done["result"]
    assert set(result["texts"]) == {"md", "html", "json", "sarif"}
    assert result["origin"] == base and result["passed"] and result["inconclusive"] == ""
    assert result["findings"] == len(json.loads(result["texts"]["json"])["findings"])
    md = result["texts"]["md"]
    assert "`rules.json`" in md and "Users" not in md and "Against `last.json`" in md  # names only, no paths
    assert "from `rules.json`): Known." in md


@pytest.mark.parametrize("change, message", [
    ({"url": ""}, "give the address"),
    ({"url": 5}, "url must be text"),
    ({"fast": "yes"}, "fast must be true or false"),
    ({"max_pages": 0}, "max_pages must be a number above 0"),
    ({"max_pages": 2.5}, "whole number"),
    ({"max_pages": True}, "max_pages must be a number"),
    ({"max_time": -1}, "max_time must be a number above 0"),
    ({"render_urls": "/x"}, "render_urls must be a list"),
    ({"configs": [{"name": "a.json"}]}, "without its name and contents"),
    ({"baseline": "last.json"}, "without its name and contents"),
    ({"post_to": "https://hook.example"}, "unknown field 'post_to'"),
    ({"screenshots": "C:\\"}, "unknown field 'screenshots'"),
    ({"kind": "deploy"}, "site audits and downloads only"),
    ({"kind": "fetch"}, "unknown field 'allow_private'"),
])
def test_every_field_is_checked_before_anything_runs(server, change, message):
    status, _, view = _post(server, "/api/jobs", {**_site("https://example.com"), **change})
    assert status == 400 and message in view["error"] and not view["ok"]
    assert server.jobs == {}


def test_a_mistake_found_by_the_run_itself_fails_the_job_with_its_words(server, serve):
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    status, _, view = _post(server, "/api/jobs", _site(base, render_urls=["https://elsewhere.example/x"]))
    assert status == 202
    done = _job(server, view["id"])
    assert done["state"] == "failed" and "must be a page of" in done["error"] and "result" not in done


def test_one_run_at_a_time_and_stop_keeps_what_was_crawled(server, serve):
    base = serve(acme)
    status, _, view = _post(server, "/api/jobs", _site(base, fast=False))  # polite: about 0.5 s a page
    assert status == 202
    _job(server, view["id"], until=lambda v: "pages" in v["progress"])
    status, _, busy = _post(server, "/api/jobs", _site(base))
    assert status == 409 and busy["id"] == view["id"] and busy["kind"] == "site"
    assert busy["error"] == "A site audit is already running; one at a time."
    status, _, stopping = _post(server, f"/api/jobs/{view['id']}/stop", {})
    assert status == 200 and stopping["stopping"]
    done = _job(server, view["id"])
    assert done["state"] == "done" and "stopped with the Stop button" in done["result"]["texts"]["md"]
    assert _post(server, "/api/jobs/nope/stop", {})[0] == 404


def test_the_last_four_finished_runs_are_kept(server):
    ids = []
    for _ in range(app.KEEP_JOBS + 2):
        job, started = server.start(lambda job: {})
        assert started
        job.thread.join(5)
        ids.append(job.id)
    assert list(server.jobs) == ids[-app.KEEP_JOBS:]
    status, _, out = ask(server, f"/api/jobs/{ids[0]}", headers={app.TOKEN_HEADER: server.token})
    assert status == 404 and b"keeps the last 4" in out


def test_the_crux_key_goes_to_the_run_and_never_comes_back(server, serve, monkeypatch):
    key = "SENTINEL-CRUX-KEY-41aa"
    given = []
    monkeypatch.setattr(site, "field_data", lambda origin, url, k, guard: given.append(k) or [])
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    status, _, view = _post(server, "/api/jobs", _site(base, crux_key=f" {key} "))
    seen = [json.dumps(view)]
    done = _job(server, view["id"], until=lambda v: seen.append(json.dumps(v)) or v["state"] != "running")
    assert done["state"] == "done" and given == [key]
    assert key not in "".join(seen)


def _status(server, headers=None, body=b"{}", host=None):
    return ask(server, "/api/jobs", method="POST", body=body, host=host,
               headers={app.TOKEN_HEADER: server.token, "Content-Type": "application/json", **(headers or {})})


@pytest.mark.parametrize("headers, body, code", [
    ({"Origin": "https://evil.example"}, b"{}", 403),
    ({"Origin": "null"}, b"{}", 403),
    ({app.TOKEN_HEADER: "wrong"}, b"{}", 403),
    ({"Content-Type": "text/plain"}, b"{}", 415),
    ({"Content-Type": "application/x-www-form-urlencoded"}, b"kind=site", 415),
    ({"Transfer-Encoding": "chunked"}, b"2\r\n{}\r\n0\r\n\r\n", 411),
    ({"Content-Length": str(app.MAX_BODY + 1)}, b"", 413),
    ({}, b"[1, 2]", 400),
    ({}, b"\xff{", 400),
])
def test_a_post_is_read_only_from_this_page_as_json_of_a_bounded_size(server, headers, body, code):
    status, got, _ = _status(server, headers, body)
    assert status == code
    assert not any(name.lower().startswith("access-control-") for name in got)
    assert server.jobs == {}


def test_a_post_to_another_name_or_address_gets_nothing(server):
    assert _status(server, host="evil.example")[0] == 421
    assert _status(server, host=f"evil.example:{server.port}")[0] == 421
    assert ask(server, "/", method="POST", body=b"{}")[0] == 404
    assert ask(server, "/api/info", method="POST", body=b"{}",
               headers={app.TOKEN_HEADER: server.token, "Content-Type": "application/json"})[0] == 404


def test_info_says_whether_the_browser_pass_is_installed(server, monkeypatch):
    status, _, out = ask(server, "/api/info", headers={app.TOKEN_HEADER: server.token})
    assert status == 200 and json.loads(out)["render"] == app.installed()
    monkeypatch.setattr(app, "installed", lambda: False)
    info = json.loads(ask(server, "/api/info", headers={app.TOKEN_HEADER: server.token})[2])
    assert info["render"] is False and "playwright install chromium" in info["render_install"]

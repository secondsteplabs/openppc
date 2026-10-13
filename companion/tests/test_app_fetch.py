"""`openppc-online app`'s Download panel: a `fetch` run as a job, its credentials taken from the request only, never
sent back, and dropped when it ends (THREAT_MODEL.md, "The job API" and `openppc-online fetch`)."""
import json

import pytest
from test_app_jobs import _job, _post
from test_fetch_command import ACCOUNTS, ENVS, FAKES, _secrets
from test_fetch_google import FakeGoogle
from test_fetch_meta import FakeGraph
from test_fetch_microsoft import FakeMicrosoft

from openppc_online import app
from openppc_online.fetch import command, http


@pytest.fixture
def platform_api(monkeypatch):
    """Route the job's gate to a fake platform, with no credential in the environment: the request brings them."""
    def use(platform, fake=None):
        fake = fake or FAKES[platform]()
        monkeypatch.setattr(command, "Gate", lambda p, send=None: http.Gate(p, fake))
        for env in ENVS.values():
            for name in env:
                monkeypatch.delenv(name, raising=False)
        return fake
    return use


def _fetch(platform, **more):
    return {"kind": "fetch", "platform": platform, "account": ACCOUNTS[platform], "credentials": dict(ENVS[platform]),
            **({"conversion": "lead"} if platform == "meta" else {}), **more}


def _run(server, body):
    status, _, view = _post(server, "/api/jobs", body)
    seen = [json.dumps(view)]
    assert status == 202, view
    done = _job(server, view["id"], until=lambda v: seen.append(json.dumps(v)) or v["state"] != "running")
    return done, "".join(seen)


@pytest.mark.parametrize("platform", command.PLATFORMS)
def test_a_download_comes_back_as_the_files_and_their_templates(platform, server, platform_api):
    platform_api(platform)
    done, seen = _run(server, _fetch(platform))
    assert done["state"] == "done", done
    result = done["result"]
    assert result["platform"] == platform and done["kind"] == "fetch"
    assert list(result["files"]) == list(command.NAMES[platform])
    assert result["templates"] == {name: command.TEMPLATE[name] for name in command.NAMES[platform]}
    assert all(text.strip() for text in result["files"].values())
    assert all(s not in seen for s in _secrets(platform))


def test_the_credentials_are_dropped_when_the_download_ends(server, platform_api):
    platform_api("google")
    work = app.fetch_job(_fetch("google"))
    held = [c.cell_contents for c in work.__closure__ or () if isinstance(c.cell_contents, dict)]
    assert held and any(set(d) == set(ENVS["google"]) for d in held)
    job, started = server.start(work, "fetch")
    assert started
    job.thread.join(30)
    assert job.state == "done", job.error
    assert all(d == {} for d in held)


@pytest.mark.parametrize("platform, fake", [
    ("google", lambda: FakeGoogle(token_answer=(400, {"error": "invalid_grant",
                                                      "error_description": "SENTINEL refresh-SENTINEL-4"}))),
    ("microsoft", lambda: FakeMicrosoft(submit_answer=(400, {"OperationErrors": [
        {"Code": 105, "ErrorCode": "InvalidCredentials", "Message": "dev-SENTINEL-1 is bad"}]}))),
    ("meta", lambda: FakeGraph(error=(400, {"error": {"code": 190, "message": "token EAAB-SENTINEL-1 expired"}}))),
])
def test_a_failure_is_explained_without_any_credential(platform, fake, server, platform_api):
    platform_api(platform, fake())
    done, seen = _run(server, _fetch(platform))
    assert done["state"] == "failed" and done["error"] and "hit a bug" not in done["error"]
    assert "result" not in done
    assert all(s not in seen for s in _secrets(platform))


def test_a_missing_credential_is_named(server, platform_api):
    platform_api("meta")
    done, _ = _run(server, _fetch("meta", credentials={}))
    assert done["state"] == "failed" and "META_ACCESS_TOKEN" in done["error"]


@pytest.mark.parametrize("change, message", [
    ({"platform": "tiktok"}, "platform must be one of google, microsoft, meta"),
    ({"platform": 3}, "platform must be text"),
    ({"account": ""}, "give the account's ID"),
    ({"days": 0}, "days must be a whole number from 1 to 365"),
    ({"days": 400}, "from 1 to 365"),
    ({"days": True}, "from 1 to 365"),
    ({"days": "30"}, "from 1 to 365"),
    ({"credentials": "token"}, "credentials must be names and values"),
    ({"credentials": {"GOOGLE_ADS_DEVELOPER_TOKEN": 5}}, "credentials must be names and values"),
    ({"credentials": {"GOOGLE_ADS_DEVELOPER_TOKEN": "x" * 4001}}, "at most 4000 characters"),
    ({"credentials": {"META_ACCESS_TOKEN": "x"}}, "'META_ACCESS_TOKEN' isn't a Google Ads credential"),
    ({"credentials": {"PATH": "C:\\"}}, "'PATH' isn't a Google Ads credential"),
    ({"out": "C:\\Users"}, "unknown field 'out'"),
    ({"force": True}, "unknown field 'force'"),
])
def test_every_download_field_is_checked_before_anything_runs(server, change, message):
    status, _, view = _post(server, "/api/jobs", {**_fetch("google"), **change})
    assert status == 400 and message in view["error"] and not view["ok"]
    assert server.jobs == {}


def test_one_job_at_a_time_and_stop_ends_a_download_with_nothing(server, platform_api):
    platform_api("microsoft", FakeMicrosoft(pending=10_000))
    status, _, view = _post(server, "/api/jobs", _fetch("microsoft"))
    assert status == 202
    _job(server, view["id"], until=lambda v: "build the report" in v["progress"])
    status, _, busy = _post(server, "/api/jobs", _fetch("google"))
    assert status == 409 and busy["kind"] == "fetch" and busy["error"] == "A download is already running; one at a time."
    assert _post(server, f"/api/jobs/{view['id']}/stop", {})[0] == 200
    done = _job(server, view["id"], seconds=5)
    assert done["state"] == "failed" and done["error"] == "Stopped with the Stop button; nothing was downloaded."

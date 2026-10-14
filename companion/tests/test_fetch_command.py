"""`openppc-online fetch`, the command: the files it writes feed `openppc audit`, --out is checked before connecting,
nothing is written unless every answer came, and no credential reaches a file, stdout, stderr or an error
(fitness function 11)."""
import datetime as dt
import json

import pytest
from test_fetch_google import SECRETS as GOOGLE_ENV
from test_fetch_google import FakeGoogle
from test_fetch_meta import ENV as META_ENV
from test_fetch_meta import TODAY, FakeGraph
from test_fetch_microsoft import SECRETS as MICROSOFT_ENV
from test_fetch_microsoft import FakeMicrosoft

from openppc import cli as core_cli
from openppc_online.cli import main
from openppc_online.fetch import command, google, http

ACCOUNTS = {"google": "123-456-7890", "microsoft": "149123456", "meta": "act_123456789"}
ENVS = {"google": GOOGLE_ENV, "microsoft": MICROSOFT_ENV, "meta": META_ENV}
FAKES = {"google": FakeGoogle, "microsoft": lambda: FakeMicrosoft(pending=0), "meta": FakeGraph}
EXTRA = {"meta": ["--conversion", "lead"]}


@pytest.fixture
def platform_api(monkeypatch):
    """Route the command's gate to a fake platform, and set its credentials. The fakes answer only for the date
    windows ending on TODAY, so the command runs on that date."""
    def use(platform, fake=None):
        fake = fake or FAKES[platform]()
        monkeypatch.setattr(command, "Gate", lambda p, send=None: http.Gate(p, fake))
        contents = command.contents
        monkeypatch.setattr(command, "contents", lambda *a, **k: contents(*a, **{**k, "today": k.get("today") or TODAY}))
        for name in {*GOOGLE_ENV, *MICROSOFT_ENV, *META_ENV}:
            monkeypatch.delenv(name, raising=False)
        for name, value in ENVS[platform].items():
            monkeypatch.setenv(name, value)
        return fake
    return use


def _run(args, capsys):
    try:
        code = main(args)
    except SystemExit as e:
        code = e.code
    out = capsys.readouterr()
    return code, out.out, out.err


def _secrets(platform):
    return [v for v in ENVS[platform].values() if "SENTINEL" in v] + ["SENTINEL"]


@pytest.mark.parametrize("platform", command.PLATFORMS)
def test_fetch_writes_files_that_openppc_audit_reads(platform, platform_api, tmp_path, capsys):
    platform_api(platform)
    code, out, err = _run(["fetch", platform, ACCOUNTS[platform], "--out", str(tmp_path / "exports"),
                           *EXTRA.get(platform, [])], capsys)
    assert code == 0, err
    commands = out.splitlines()
    assert len(commands) == len(command.NAMES[platform]) and all(c.startswith("openppc audit ") for c in commands)
    assert all(f"wrote {tmp_path / 'exports' / n}" in err for n in command.NAMES[platform])
    for line in commands:
        _, _, template, path = line.split(" ", 3)
        assert core_cli.main(["audit", template, path]) == 0, line
        report = capsys.readouterr().out
        assert report.startswith("#") and "Number check FAILED" not in report
    for text in [out, err, *((tmp_path / "exports" / n).read_text(encoding="utf-8")
                             for n in command.NAMES[platform])]:
        assert all(s not in text for s in _secrets(platform))


@pytest.mark.parametrize("platform, fake", [
    ("google", lambda: FakeGoogle(token_answer=(400, {"error": "invalid_grant",
                                                      "error_description": "SENTINEL refresh-SENTINEL-4"}))),
    ("microsoft", lambda: FakeMicrosoft(submit_answer=(400, {"OperationErrors": [
        {"Code": 105, "ErrorCode": "InvalidCredentials", "Message": "dev-SENTINEL-1 is bad"}]}))),
    ("meta", lambda: FakeGraph(error=(400, {"error": {"code": 190, "message": "token EAAB-SENTINEL-1 expired"}}))),
])
def test_a_failure_shows_no_credential_and_writes_nothing(platform, fake, platform_api, tmp_path, capsys):
    platform_api(platform, fake())
    code, out, err = _run(["fetch", platform, ACCOUNTS[platform], "--out", str(tmp_path / "exports"),
                           *EXTRA.get(platform, [])], capsys)
    assert code == 1 and out == "" and err.startswith("openppc-online: ")
    assert all(s not in err for s in _secrets(platform))
    assert not (tmp_path / "exports").exists()


def test_a_failure_part_way_writes_none_of_the_files(platform_api, tmp_path, capsys):
    class FailsOnKeywords(FakeGoogle):
        def __call__(self, req, timeout):
            if b"keyword_view" in (req.data or b""):
                return 500, b"{}"
            return super().__call__(req, timeout)
    platform_api("google", FailsOnKeywords())
    code, _, err = _run(["fetch", "google", ACCOUNTS["google"], "--out", str(tmp_path)], capsys)
    assert code == 1 and "answered HTTP 500" in err
    assert list(tmp_path.iterdir()) == []


def test_files_already_in_out_stop_it_before_connecting(platform_api, tmp_path, capsys):
    fake = platform_api("google")
    (tmp_path / "keywords.csv").write_text("mine", encoding="utf-8")
    code, _, err = _run(["fetch", "google", ACCOUNTS["google"], "--out", str(tmp_path)], capsys)
    assert code == 1 and "keywords.csv already in" in err and "--force" in err
    assert fake.requests == [] and (tmp_path / "keywords.csv").read_text(encoding="utf-8") == "mine"
    code, _, _ = _run(["fetch", "google", ACCOUNTS["google"], "--out", str(tmp_path), "--force"], capsys)
    assert code == 0 and (tmp_path / "keywords.csv").read_text(encoding="utf-8").startswith("Search keyword report")


@pytest.mark.parametrize("args, says", [
    (["fetch", "google", "123-456-7890", "--out", "{file}"], "is a file"),
    (["fetch", "google", "123-456-7890", "--out", "{dir}", "--conversion", "lead"], "--conversion is for fetch meta"),
    (["fetch", "google", "123-456-7890", "--out", "{dir}", "--days", "400"], "--days is 1 to 365"),
    (["fetch", "google", "123-456-7890", "--out", "{dir}", "--days", "0"], "must be at least 1"),
    (["fetch", "tiktok", "123", "--out", "{dir}"], "invalid choice"),
    (["fetch", "google", "123-456-7890"], "--out"),
    (["fetch", "google", "12345", "--out", "{dir}"], "not a Google Ads customer ID"),
])
def test_bad_input_exits_1_before_connecting(args, says, platform_api, tmp_path, capsys):
    fake = platform_api("google")
    (tmp_path / "a-file").write_text("x", encoding="utf-8")
    values = {"file": str(tmp_path / "a-file"), "dir": str(tmp_path / "exports")}
    code, _, err = _run([a.format(**values) for a in args], capsys)
    assert code == 1 and says in err
    assert fake.requests == [] and not (tmp_path / "exports").exists()


def test_missing_credentials_exit_1_naming_them(platform_api, tmp_path, monkeypatch, capsys):
    fake = platform_api("google")
    monkeypatch.delenv("GOOGLE_ADS_REFRESH_TOKEN")
    code, _, err = _run(["fetch", "google", "123-456-7890", "--out", str(tmp_path)], capsys)
    assert code == 1 and "set GOOGLE_ADS_REFRESH_TOKEN first" in err and fake.requests == []


def test_a_version_near_its_sunset_is_said_after_the_files():
    sunset = command.VERSIONS["google"].sunset
    assert command.sunset_note("google", sunset - dt.timedelta(days=command.WARN_DAYS + 1)) is None
    note = command.sunset_note("google", sunset - dt.timedelta(days=10))
    assert note and "update openppc-online" in note and google.GOOGLE.name in note
    assert command.sunset_note("microsoft", dt.date(2030, 1, 1)) is None
    _, notes = command.contents("google", "1234567890", GOOGLE_ENV, send=FakeGoogle(),
                                today=sunset - dt.timedelta(days=10))
    assert notes == [note]


def test_meta_without_a_conversion_lists_its_action_types(platform_api, tmp_path, capsys):
    platform_api("meta")
    code, _, err = _run(["fetch", "meta", "act_123456789", "--out", str(tmp_path)], capsys)
    assert code == 1 and "add --conversion" in err and "lead (71)" in err
    assert list(tmp_path.iterdir()) == []


def test_meta_says_which_files_it_leaves_out(platform_api, tmp_path, capsys):
    platform_api("meta")
    code, _, err = _run(["fetch", "meta", "act_123456789", "--conversion", "lead", "--out", str(tmp_path)], capsys)
    assert code == 0 and "note: Meta has no search terms or keywords" in err
    assert json.loads((tmp_path / "account.json").read_text(encoding="utf-8"))["meta"]["conversion"] == "lead"

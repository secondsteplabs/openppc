"""fetch's one way out (fitness function 10): each platform's allowlist, checked before connecting, no redirects,
and the version calendar."""
import datetime as dt
import urllib.request

import pytest

from openppc_online.fetch import files, http
from openppc_online.fetch.versions import VERSIONS, WARN_DAYS

# Every call fetch may make. A new entry here is a reviewed change: none may write to an account.
REVIEWED = {
    "google": {("POST", "oauth2.googleapis.com", r"/token"),
               ("POST", "googleads.googleapis.com", r"/v25/customers/\d{10}/googleAds:searchStream")},
    "microsoft": {("POST", "login.microsoftonline.com", r"/common/oauth2/v2\.0/token"),
                  ("POST", "reporting.api.bingads.microsoft.com", r"/Reporting/v13/GenerateReport/(Submit|Poll)")},
    "meta": {("GET", "graph.facebook.com", r"/v25\.0/act_\d+(/(insights|campaigns|adsets|ads))?")},
}


def _gate(platform):
    sent = []

    def send(req, timeout):
        sent.append((req.get_method(), req.full_url))
        return 200, b"{}"
    gate = http.Gate(platform, send)
    gate.sent = sent
    return gate


def test_each_platform_may_make_only_its_reviewed_calls():
    assert {p: {(r.method, r.host, r.path) for r in rules} for p, rules in http.ALLOWED.items()} == REVIEWED


@pytest.mark.parametrize("platform, method, url", [
    ("google", "POST", "https://oauth2.googleapis.com/token"),
    ("google", "POST", "https://googleads.googleapis.com/v25/customers/1234567890/googleAds:searchStream"),
    ("microsoft", "POST", "https://login.microsoftonline.com/common/oauth2/v2.0/token"),
    ("microsoft", "POST", "https://reporting.api.bingads.microsoft.com/Reporting/v13/GenerateReport/Submit"),
    ("microsoft", "POST", "https://reporting.api.bingads.microsoft.com/Reporting/v13/GenerateReport/Poll"),
    ("meta", "GET", "https://graph.facebook.com/v25.0/act_123?fields=name,currency"),
    ("meta", "GET", "https://graph.facebook.com/v25.0/act_123/ads?limit=500&after=QVFI"),
])
def test_the_reviewed_calls_go_through(platform, method, url):
    gate = _gate(platform)
    assert gate.call(method, url) == b"{}"
    assert gate.sent == [(method, url)]


@pytest.mark.parametrize("platform, method, url", [
    # what would change an account
    ("google", "POST", "https://googleads.googleapis.com/v25/customers/1234567890/googleAds:mutate"),
    ("google", "POST", "https://googleads.googleapis.com/v25/customers/1234567890/campaigns:mutate"),
    ("microsoft", "POST", "https://campaign.api.bingads.microsoft.com/CampaignManagement/v13/Campaigns"),
    ("meta", "POST", "https://graph.facebook.com/v25.0/act_123/campaigns"),
    ("meta", "DELETE", "https://graph.facebook.com/v25.0/act_123"),
    # another version, host, scheme, port, user or path
    ("google", "POST", "https://googleads.googleapis.com/v19/customers/1234567890/googleAds:searchStream"),
    ("google", "POST", "https://googleads.googleapis.com.evil.example/v25/customers/1234567890/googleAds:searchStream"),
    ("google", "POST", "http://oauth2.googleapis.com/token"),
    ("google", "POST", "https://oauth2.googleapis.com:8443/token"),
    ("google", "POST", "https://user@oauth2.googleapis.com/token"),
    ("google", "POST", "https://googleads.googleapis.com/v25/customers/123/../1234567890/googleAds:searchStream"),
    ("meta", "GET", "https://graph.facebook.com/v25.0/me/adaccounts"),
    ("meta", "GET", "https://graph.facebook.com/v25.0/act_123/ads/../../me"),
    # another platform's call
    ("meta", "POST", "https://oauth2.googleapis.com/token"),
    ("google", "GET", "https://graph.facebook.com/v25.0/act_123"),
])
def test_anything_else_is_refused_before_connecting(platform, method, url):
    gate = _gate(platform)
    with pytest.raises(http.Refused):
        gate.call(method, url)
    assert gate.sent == []


def test_a_download_address_the_api_gave_is_called_once_with_get():
    gate = _gate("microsoft")
    url = "https://reports.storage.example/r/123.zip?sig=abc"
    with pytest.raises(http.Refused):
        gate.call("GET", url)
    gate.allow_download(url)
    with pytest.raises(http.Refused):
        gate.call("POST", url)
    gate.call("GET", url)
    with pytest.raises(http.Refused):
        gate.call("GET", url)
    assert gate.sent == [("GET", url)]


@pytest.mark.parametrize("url", ["http://reports.example/r.zip", "https://10.0.0.5/r.zip", "https://[::1]/r.zip",
                                 "https://reports.example:8443/r.zip", "https://u:p@reports.example/r.zip",
                                 "file:///etc/passwd"])
def test_a_download_address_must_be_https_on_a_host_name(url):
    with pytest.raises(http.Refused):
        _gate("microsoft").allow_download(url)


def test_a_failure_keeps_its_body_out_of_the_message():
    def send(req, timeout):
        return 400, b'{"error": "secret-looking text"}'
    with pytest.raises(http.HttpError) as caught:
        http.Gate("google", send).call("POST", "https://oauth2.googleapis.com/token")
    assert (caught.value.status, str(caught.value)) == (400, "HTTP 400")


def test_an_unreachable_host_is_said_in_words():
    def send(req, timeout):
        raise TimeoutError("timed out")
    with pytest.raises(ValueError, match="couldn't reach oauth2.googleapis.com"):
        http.Gate("google", send).call("POST", "https://oauth2.googleapis.com/token")


def test_no_redirect_is_followed(serve):
    base = serve(lambda b: {"/from": (302, {"Location": f"{b}/to"}, ""), "/to": (200, {}, "followed")})
    status, _ = http._send(urllib.request.Request(f"{base}/from"), 10)
    assert status == 302 and serve.asked == ["/from"]


def test_only_error_codes_are_shown_never_free_text():
    assert http.codes(["RESOURCE_EXHAUSTED", "InvalidCredentials", "your token abc123 is bad", "x", "190"]) \
        == ["RESOURCE_EXHAUSTED", "InvalidCredentials"]


@pytest.mark.parametrize("platform", sorted(VERSIONS))
def test_no_api_version_is_near_its_sunset(platform):
    version = VERSIONS[platform]
    if version.sunset is None:
        return
    left = (version.sunset - dt.date.today()).days
    assert left > WARN_DAYS, (f"{platform} {version.name} is turned off in {left} days ({version.sunset}): move to "
                              f"a newer version and update fetch/versions.py ({version.source})")


def test_the_allowlists_name_the_versions_in_the_calendar():
    for platform, rules in http.ALLOWED.items():
        name = VERSIONS[platform].name.replace(".", r"\.")
        assert any(name in r.path for r in rules), platform


def test_files_are_written_only_under_their_names_and_whole(tmp_path):
    out = files.folder(tmp_path / "exports", ["account.json"], force=False)
    assert files.save(out, {"account.json": "{}\n"}) == [out / "account.json"]
    with pytest.raises(ValueError, match="already in"):
        files.folder(out, ["account.json"], force=False)
    files.folder(out, ["account.json"], force=True)
    with pytest.raises(ValueError, match="not a file fetch writes"):
        files.save(out, {"../escape.json": "{}"})
    assert sorted(p.name for p in out.iterdir()) == ["account.json"]
    (tmp_path / "a-file").write_text("x")
    with pytest.raises(ValueError, match="is a file"):
        files.folder(tmp_path / "a-file", ["account.json"], force=False)


def test_the_window_is_the_last_full_days_and_as_many_before():
    assert files.window(7, dt.date(2026, 10, 13)) == (dt.date(2026, 10, 6), dt.date(2026, 10, 12),
                                                     dt.date(2026, 9, 29), dt.date(2026, 10, 5))

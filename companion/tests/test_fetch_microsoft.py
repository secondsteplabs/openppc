"""fetch microsoft against answers shaped like Microsoft's documentation: the identity platform's token endpoint,
the Reporting service's Submit and Poll (ApiFaultDetail on failure), and the zipped CSV at the address Poll gives."""
import csv
import datetime as dt
import io
import json
import urllib.parse
import zipfile

import pytest

from openppc.templates import run_template
from openppc_online.fetch import files, http, microsoft

SECRETS = {"MICROSOFT_ADS_DEVELOPER_TOKEN": "dev-SENTINEL-1", "MICROSOFT_ADS_CLIENT_ID": "client-SENTINEL-2",
           "MICROSOFT_ADS_REFRESH_TOKEN": "refresh-SENTINEL-3", "MICROSOFT_ADS_CUSTOMER_ID": "251000001"}
ACCESS = "EwB-SENTINEL-4"
ACCOUNT = "149123456"
TODAY = dt.date(2026, 10, 13)
STORAGE = "https://bingadsappsstorageprod.blob.core.windows.net/downloads/{}.zip?sv=2025-01-05&sig=SENTINEL-5"

REPORTS = {
    "AccountPerformanceReport": {
        "2026-09-13": [{"AccountName": "Acme Shoes", "CurrencyCode": "GBP", "Clicks": "180", "Impressions": "4,100",
                        "Spend": "290.40", "Conversions": "9"}],
        "2026-08-14": [{"AccountName": "Acme Shoes", "CurrencyCode": "GBP", "Clicks": "150", "Impressions": "3,900",
                        "Spend": "250.00", "Conversions": "11"}]},
    "SearchQueryPerformanceReport": [
        {"SearchQuery": "free shoes", "DeliveredMatchType": "Broad", "CampaignName": "Search - Shoes",
         "CampaignType": "Search & content", "AdGroupName": "Running shoes", "Clicks": "35", "Impressions": "800",
         "Spend": "52.10", "Conversions": "0"},
        {"SearchQuery": "running shoes sale", "DeliveredMatchType": "Exact", "CampaignName": "Search - Shoes",
         "CampaignType": "Search & content", "AdGroupName": "Running shoes", "Clicks": "20", "Impressions": "300",
         "Spend": "31.00", "Conversions": "5"},
        {"SearchQuery": "shoe shop", "DeliveredMatchType": "Broad", "CampaignName": "PMax - All",
         "CampaignType": "Performance max", "AdGroupName": "", "Clicks": "22", "Impressions": "600",
         "Spend": "29.75", "Conversions": "0"}],
    "KeywordPerformanceReport": [
        {"Keyword": "running shoes", "BidMatchType": "Broad", "CampaignName": "Search - Shoes",
         "AdGroupName": "Running shoes", "Clicks": "55", "Impressions": "1100", "Spend": "83.10", "Conversions": "5",
         "QualityScore": "4"},
        {"Keyword": "trail shoes", "BidMatchType": "Phrase", "CampaignName": "Search - Shoes",
         "AdGroupName": "Running shoes", "Clicks": "0", "Impressions": "40", "Spend": "0", "Conversions": "0",
         "QualityScore": "--"}],
}


def _zip(rows, members=1):
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=list(rows[0]), quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for i in range(members):
            z.writestr(f"report{i}.csv", "\ufeff" + text.getvalue())
    return out.getvalue()


def _fault(code, error_code, message="Invalid client data. SENTINEL-free-text"):
    return {"TrackingId": "65602e3d", "Type": "ApiFaultDetail", "BatchErrors": [],
            "OperationErrors": [{"Code": code, "Details": None, "ErrorCode": error_code, "Message": message}]}


class FakeMicrosoft:
    """The token endpoint, Submit, Poll (pending `pending` times, then done) and the storage download."""

    def __init__(self, token_answer=(200, {"token_type": "Bearer", "scope": microsoft.SCOPE, "expires_in": 3599,
                                           "access_token": ACCESS, "refresh_token": "new-refresh"}),
                 pending=1, status="Success", url=STORAGE, submit_answer=None, download=None, empty=()):
        self.token_answer, self.pending, self.status, self.url = token_answer, pending, status, url
        self.submit_answer, self.download, self.empty = submit_answer, download, empty
        self.requests, self.submitted, self.polls = [], {}, {}

    def __call__(self, req, timeout):
        body = req.data.decode() if req.data else ""
        self.requests.append((req.get_method(), req.full_url, dict(req.header_items()), body))
        if req.full_url == microsoft.TOKEN_URL:
            status, doc = self.token_answer
            return status, json.dumps(doc).encode()
        if req.full_url == microsoft.REPORTING.format("Submit"):
            if self.submit_answer:
                status, doc = self.submit_answer
                return status, json.dumps(doc).encode()
            request = json.loads(body)["ReportRequest"]
            rid = f"rid{len(self.submitted)}"
            self.submitted[rid] = request
            return 200, json.dumps({"ReportRequestId": rid}).encode()
        if req.full_url == microsoft.REPORTING.format("Poll"):
            rid = json.loads(body)["ReportRequestId"]
            self.polls[rid] = self.polls.get(rid, 0) + 1
            if self.polls[rid] <= self.pending:
                return 200, json.dumps({"ReportRequestStatus": {"ReportDownloadUrl": None,
                                                                "Status": "Pending"}}).encode()
            kind = self.submitted[rid]["Type"].removesuffix("Request")
            url = None if kind in self.empty else self.url.format(rid) if self.url else None
            return 200, json.dumps({"ReportRequestStatus": {"ReportDownloadUrl": url,
                                                            "Status": self.status}}).encode()
        rid = req.full_url.split("/downloads/")[1].split(".zip")[0]
        if self.download is not None:
            return 200, self.download
        request = self.submitted[rid]
        rows = REPORTS[request["Type"].removesuffix("Request")]
        if isinstance(rows, dict):
            start = request["Time"]["CustomDateRangeStart"]
            rows = rows[f"{start['Year']}-{start['Month']:02}-{start['Day']:02}"]
        return 200, _zip(rows)


def _download(fake, env=SECRETS, account=ACCOUNT, sleeps=None):
    return microsoft.download(account, env, http.Gate("microsoft", fake), today=TODAY,
                              sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_the_three_files_are_ones_the_audits_read(tmp_path):
    contents, notes = _download(FakeMicrosoft())
    assert sorted(contents) == sorted(microsoft.NAMES) and notes == []
    by_name = {p.name: p for p in files.save(tmp_path, contents)}
    for template, name in (("search-term-waste", "search_terms.csv"), ("keyword-audit", "keywords.csv"),
                           ("account-read", "account.json")):
        markdown, facts, passed = run_template(template, by_name[name])
        assert markdown.startswith("#") and facts and passed, template
    waste, _, _ = run_template("search-term-waste", by_name["search_terms.csv"])
    search, automated = waste.split("### In Performance Max and other automated campaigns")
    assert "| free shoes |" in search and "| shoe shop |" in automated


def test_the_files_carry_the_reports_numbers():
    contents, _ = _download(FakeMicrosoft())
    account = json.loads(contents["account.json"])
    assert account["meta"]["account"] == "Acme Shoes" and account["meta"]["currency"] == "GBP"
    assert account["current"] == {"spend": 290.4, "impressions": 4100, "clicks": 180, "conversions": 9.0}
    assert account["prior"]["spend"] == 250.0
    assert "free shoes,Broad match,Search - Shoes,Search,Running shoes,35,800,52.1,0.0,GBP" \
        in contents["search_terms.csv"].splitlines()
    assert "trail shoes,Phrase match,Search - Shoes,Running shoes,0,40,0.0,0.0,,GBP" \
        in contents["keywords.csv"].splitlines()


def test_each_report_is_asked_for_as_microsoft_documents():
    fake = FakeMicrosoft()
    _download(fake)
    for method, url, headers, body in fake.requests:
        if url.startswith(microsoft.REPORTING.format("")):
            assert method == "POST" and headers["Content-type"] == "application/json"
            assert headers["Authorization"] == f"Bearer {ACCESS}"
            assert (headers["Developertoken"], headers["Customerid"], headers["Customeraccountid"]) \
                == (SECRETS["MICROSOFT_ADS_DEVELOPER_TOKEN"], "251000001", ACCOUNT)
    kinds = [r["Type"] for r in fake.submitted.values()]
    assert kinds == ["AccountPerformanceReportRequest"] * 2 + ["SearchQueryPerformanceReportRequest",
                                                               "KeywordPerformanceReportRequest"]
    first = fake.submitted["rid0"]
    assert first["Scope"] == {"AccountIds": [149123456]} and first["Aggregation"] == "Summary"
    assert first["Time"] == {"CustomDateRangeStart": {"Day": 13, "Month": 9, "Year": 2026},
                             "CustomDateRangeEnd": {"Day": 12, "Month": 10, "Year": 2026}}


def test_the_token_request_names_the_scope_and_a_secret_only_when_set():
    fake = FakeMicrosoft()
    _download(fake)
    sent = urllib.parse.parse_qs(fake.requests[0][3])
    assert sent["scope"] == [microsoft.SCOPE] and "client_secret" not in sent
    fake = FakeMicrosoft()
    _download(fake, env={**SECRETS, microsoft.SECRET_ENV: "web-SENTINEL-6"})
    assert urllib.parse.parse_qs(fake.requests[0][3])["client_secret"] == ["web-SENTINEL-6"]


def test_the_download_carries_no_credential_and_is_made_once():
    fake = FakeMicrosoft()
    _download(fake)
    downloads = [(m, u, h) for m, u, h, _ in fake.requests if u.startswith("https://bingadsappsstorageprod")]
    assert len(downloads) == 4 and len({u for _, u, _ in downloads}) == 4
    assert all(m == "GET" and h == {} for m, _, h in downloads)


def test_polls_wait_longer_each_time():
    sleeps = []
    _download(FakeMicrosoft(pending=3), sleeps=sleeps)
    assert sleeps == [2.0, 4.0, 8.0] * 4


def test_a_report_that_never_finishes_is_given_up_on():
    sleeps = []
    with pytest.raises(ValueError, match="wasn't ready after 10 minutes"):
        _download(FakeMicrosoft(pending=10_000), sleeps=sleeps)
    assert sum(sleeps) >= microsoft.WAIT_TOTAL and max(sleeps) == microsoft.WAIT_MOST


def test_a_failed_report_says_so_by_its_status():
    with pytest.raises(ValueError, match=r"couldn't build the AccountPerformanceReport \(status Error\)"):
        _download(FakeMicrosoft(pending=0, status="Error"))


@pytest.mark.parametrize("url", ["http://bingadsappsstorageprod.blob.core.windows.net/downloads/{}.zip",
                                 "https://10.1.2.3/downloads/{}.zip", "https://storage.example:8443/downloads/{}.zip",
                                 "file:///downloads/{}.zip"])
def test_a_download_address_that_isnt_https_on_a_host_name_is_never_called(url):
    fake = FakeMicrosoft(pending=0, url=url)
    with pytest.raises(http.Refused):
        _download(fake)
    assert not any("/downloads/" in u for _, u, _, _ in fake.requests)


def test_days_without_data_give_empty_files_and_say_so():
    contents, notes = _download(FakeMicrosoft(empty=("SearchQueryPerformanceReport",)))
    assert contents["search_terms.csv"].count("\n") == 3
    assert notes == ["Microsoft Advertising had no search terms for September 13, 2026 to October 12, 2026, so "
                     "search_terms.csv has no rows"]


@pytest.mark.parametrize("download, says", [
    (b"<html>not a zip</html>", "wasn't the zipped CSV"),
    (_zip(REPORTS["KeywordPerformanceReport"], members=2), "isn't one report"),
])
def test_a_download_that_isnt_one_zipped_report_is_refused(download, says):
    with pytest.raises(ValueError, match=says):
        _download(FakeMicrosoft(pending=0, download=download))


def test_a_report_too_big_unzipped_is_never_read(monkeypatch):
    monkeypatch.setattr(microsoft, "MOST", 100)
    with pytest.raises(ValueError, match="isn't one report under"):
        _download(FakeMicrosoft(pending=0))


def test_no_credential_reaches_the_files():
    contents, _ = _download(FakeMicrosoft(), env={**SECRETS, microsoft.SECRET_ENV: "web-SENTINEL-6"})
    for text in contents.values():
        assert "SENTINEL" not in text


def test_missing_credentials_are_named_before_any_call():
    fake = FakeMicrosoft()
    with pytest.raises(ValueError) as caught:
        _download(fake, env={"MICROSOFT_ADS_CLIENT_ID": "x"})
    named = str(caught.value).split("first")[0]
    assert all(n in named for n in microsoft.CREDENTIALS if n != "MICROSOFT_ADS_CLIENT_ID")
    assert fake.requests == []


@pytest.mark.parametrize("text, digits", [("149123456", "149123456"), ("149-123-456", "149123456")])
def test_an_account_id_is_digits(text, digits):
    assert microsoft.account_id(text) == digits


@pytest.mark.parametrize("text", ["F149123456", "", "149123456/../1", "1" * 20])
def test_anything_else_is_not_an_account_id(text):
    with pytest.raises(ValueError, match="not a Microsoft Advertising account ID"):
        microsoft.account_id(text)


def test_a_customer_id_that_isnt_digits_is_refused_before_any_call():
    fake = FakeMicrosoft()
    with pytest.raises(ValueError, match="MICROSOFT_ADS_CUSTOMER_ID"):
        _download(fake, env={**SECRETS, "MICROSOFT_ADS_CUSTOMER_ID": "251000001\r\nX-Evil: 1"})
    assert fake.requests == []


@pytest.mark.parametrize("token_answer, submit_answer, says", [
    ((400, {"error": "invalid_grant", "error_description": "AADSTS70008: SENTINEL expired due to inactivity",
            "error_codes": [70008]}), None, "unused for 90 days"),
    ((401, {"error": "invalid_client", "error_description": "AADSTS7000215: SENTINEL"}), None,
     "check MICROSOFT_ADS_CLIENT_ID"),
    (None, (401, _fault(105, "InvalidCredentials")), "refused the credentials"),
    (None, (400, _fault(109, "AuthenticationTokenExpired")), "refused the credentials"),
    (None, (400, _fault(106, "UserIsNotAuthorized")), "set MICROSOFT_ADS_CUSTOMER_ID"),
    (None, (400, _fault(117, "CallRateExceeded")), "wait a minute"),
    (None, (400, _fault(100, "NullRequest")), "answered HTTP 400 (NullRequest)"),
    (None, (503, "Service Unavailable SENTINEL"), "answered HTTP 503"),
])
def test_microsoft_errors_say_what_to_do_without_echoing_the_answer(token_answer, submit_answer, says):
    fake = FakeMicrosoft(**{k: v for k, v in (("token_answer", token_answer), ("submit_answer", submit_answer))
                            if v})
    with pytest.raises(ValueError) as caught:
        _download(fake)
    assert says in str(caught.value) and "SENTINEL" not in str(caught.value)

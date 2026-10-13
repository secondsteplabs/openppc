"""fetch google against answers shaped like Google's documentation: the OAuth token endpoint, and searchStream's
array of batches (int64 metrics as strings, fields at their default left out, errors inside a GoogleAdsFailure)."""
import datetime as dt
import json
import re
import urllib.parse

import pytest

from openppc.templates import run_template
from openppc_online.fetch import files, google, http

SECRETS = {"GOOGLE_ADS_DEVELOPER_TOKEN": "dev-SENTINEL-1", "GOOGLE_ADS_CLIENT_ID": "client-SENTINEL-2",
           "GOOGLE_ADS_CLIENT_SECRET": "secret-SENTINEL-3", "GOOGLE_ADS_REFRESH_TOKEN": "refresh-SENTINEL-4"}
ACCESS = "ya29.SENTINEL-5"
TODAY = dt.date(2026, 10, 13)


def _batches(*rows_per_batch):
    return [{"results": rows, "fieldMask": "x", "requestId": f"r{i}"} if rows else {"fieldMask": "x"}
            for i, rows in enumerate(rows_per_batch)]


def _metrics(clicks, impressions, cost, conversions=0.0):
    m = {"clicks": str(clicks), "impressions": str(impressions), "costMicros": str(int(cost * 1_000_000))}
    if conversions:
        m["conversions"] = conversions
    return m


SEARCH = {"name": "Search - Shoes", "advertisingChannelType": "SEARCH"}
PMAX = {"name": "PMax - All", "advertisingChannelType": "PERFORMANCE_MAX"}
GROUP = {"name": "Running shoes"}

ANSWERS = {
    "customer": _batches([{"customer": {"resourceName": "customers/1234567890", "descriptiveName": "Acme Shoes",
                                        "currencyCode": "EUR"}}]),
    "search_term_view": _batches(
        [{"searchTermView": {"searchTerm": "free shoes", "status": "NONE"},
          "segments": {"searchTermMatchType": "BROAD"}, "campaign": SEARCH, "adGroup": GROUP,
          "metrics": _metrics(40, 900, 61.5)}],
        [{"searchTermView": {"searchTerm": "running shoes sale", "status": "ADDED"},
          "segments": {"searchTermMatchType": "EXACT"}, "campaign": SEARCH, "adGroup": GROUP,
          "metrics": _metrics(30, 400, 45.0, 6.0)}]),
    "campaign_search_term_view": _batches(
        [{"campaignSearchTermView": {"searchTerm": "shoe repair near me"}, "campaign": PMAX,
          "metrics": _metrics(25, 700, 38.25)}]),
    "keyword_view": _batches(
        [{"adGroupCriterion": {"keyword": {"text": "running shoes", "matchType": "BROAD"},
                               "qualityInfo": {"qualityScore": 4}},
          "campaign": SEARCH, "adGroup": GROUP, "metrics": _metrics(70, 1300, 106.5, 6.0)}]),
    "campaign": _batches(
        [{"campaign": {"id": "11", "status": "ENABLED", "biddingStrategyType": "MAXIMIZE_CONVERSIONS",
                       "networkSettings": {"targetContentNetwork": True},
                       "geoTargetTypeSetting": {"positiveGeoTargetType": "PRESENCE_OR_INTEREST"},
                       "primaryStatusReasons": ["BUDGET_CONSTRAINED"], **SEARCH},
          "campaignBudget": {"amountMicros": "50000000"}},
         {"campaign": {"id": "12", "status": "ENABLED", "biddingStrategyType": "MAXIMIZE_CONVERSION_VALUE",
                       **PMAX},
          "campaignBudget": {"amountMicros": "80000000"}}]),
    "ad_group": _batches([{"adGroup": {"id": "21", "status": "ENABLED", **GROUP}, "campaign": {"id": "11"}}]),
    "ad_group_criterion": _batches(
        [{"adGroup": {"id": "21"},
          "adGroupCriterion": {"keyword": {"text": "running shoes", "matchType": "BROAD"}, "status": "ENABLED",
                               "systemServingStatus": "ELIGIBLE", "approvalStatus": "APPROVED",
                               "qualityInfo": {"qualityScore": 4, "searchPredictedCtr": "BELOW_AVERAGE",
                                               "creativeQualityScore": "AVERAGE",
                                               "postClickQualityScore": "BELOW_AVERAGE"}}},
         {"adGroup": {"id": "21"},
          "adGroupCriterion": {"negative": True, "keyword": {"text": "jobs", "matchType": "PHRASE"},
                               "status": "ENABLED"}}]),
    "campaign_criterion": _batches(
        [{"campaign": {"id": "11"}, "campaignCriterion": {"keyword": {"text": "free", "matchType": "BROAD"}}}]),
    "ad_group_ad": _batches(
        [{"adGroup": {"id": "21"},
          "adGroupAd": {"status": "ENABLED", "adStrength": "POOR",
                        "policySummary": {"approvalStatus": "APPROVED"},
                        "ad": {"type": "RESPONSIVE_SEARCH_AD", "responsiveSearchAd": {
                            "headlines": [{"text": "Running Shoes", "pinnedField": "HEADLINE_1"},
                                          {"text": "Free Delivery"}, {"text": "Shop Now"}],
                            "descriptions": [{"text": "Shoes for every run."}, {"text": "Order today."}]}}}}]),
    "campaign_asset": _batches(
        [{"campaign": {"id": "11"}, "campaignAsset": {"fieldType": "SITELINK", "status": "ENABLED"}}]),
    "customer_asset": _batches([]),
}
TOTALS = {"2026-09-13": _metrics(260, 5200, 410.0, 12.0), "2026-08-14": _metrics(240, 5000, 380.0, 15.0)}


class FakeGoogle:
    """Google's two endpoints, answering by the query's FROM clause. Records each request as sent."""

    def __init__(self, token_answer=(200, {"access_token": ACCESS, "expires_in": 3599, "token_type": "Bearer"}),
                 search_answer=None):
        self.token_answer, self.search_answer, self.requests = token_answer, search_answer, []

    def __call__(self, req, timeout):
        body = req.data.decode()
        self.requests.append((req.get_method(), req.full_url, dict(req.header_items()), body))
        if req.full_url == google.TOKEN_URL:
            status, doc = self.token_answer
            return status, json.dumps(doc).encode()
        if self.search_answer:
            status, doc = self.search_answer
            return status, json.dumps(doc).encode()
        query = json.loads(body)["query"]
        source = re.search(r"\bFROM\s+(\w+)", query)[1]
        if source == "customer" and "segments.date" in query:
            start = re.search(r"BETWEEN '([\d-]+)'", query)[1]
            metrics = TOTALS.get(start, _metrics(100, 2000, 150.0, 5.0))
            return 200, json.dumps(_batches([{"metrics": metrics}])).encode()
        return 200, json.dumps(ANSWERS[source]).encode()

    def queries(self):
        return [json.loads(body)["query"] for _, url, _, body in self.requests if url != google.TOKEN_URL]


def _download(fake, env=SECRETS, customer="123-456-7890"):
    return google.download(customer, env, http.Gate("google", fake), today=TODAY)


def test_the_four_files_are_ones_the_audits_read(tmp_path):
    contents, notes = _download(FakeGoogle())
    assert sorted(contents) == sorted(google.NAMES) and notes == []
    paths = files.save(tmp_path, contents)
    by_name = {p.name: p for p in paths}
    for template, name in (("search-term-waste", "search_terms.csv"), ("keyword-audit", "keywords.csv"),
                           ("account-structure", "account_structure.json"), ("account-read", "account.json")):
        markdown, facts, passed = run_template(template, by_name[name])
        assert markdown.startswith("#") and facts and passed, template
    waste, _, _ = run_template("search-term-waste", by_name["search_terms.csv"])
    search, automated = waste.split("### In Performance Max and other automated campaigns")
    assert "| free shoes |" in search and "| shoe repair near me |" in automated


def test_performance_max_search_terms_are_in_the_search_terms_file():
    contents, _ = _download(FakeGoogle())
    rows = contents["search_terms.csv"].splitlines()
    assert any(r.startswith("shoe repair near me,,None,PMax - All,Performance Max,,25,700,38.25,0") for r in rows)
    assert any(r.startswith("free shoes,Broad match,None,Search - Shoes,Search,Running shoes,40,900,61.5,0")
               for r in rows)


def test_the_files_say_what_they_cover():
    contents, _ = _download(FakeGoogle())
    assert contents["search_terms.csv"].startswith("Search terms report\n")
    account = json.loads(contents["account.json"])
    assert account["meta"]["account"] == "Acme Shoes" and account["meta"]["currency"] == "EUR"
    assert account["current"] == {"spend": 410.0, "impressions": 5200, "clicks": 260, "conversions": 12.0}
    assert account["prior"]["spend"] == 380.0
    snapshot = json.loads(contents["account_structure.json"])
    assert snapshot["campaigns"][0]["budget"] == 50.0 and snapshot["campaigns"][0]["budget_limited"] is True
    assert snapshot["campaigns"][1]["display_network"] is False


def test_every_query_only_reads_and_none_mixes_keywords_into_performance_max():
    fake = FakeGoogle()
    _download(fake)
    queries = fake.queries()
    assert queries and all(q.lstrip().startswith("SELECT") for q in queries)
    pmax = [q for q in queries if "FROM campaign_search_term_view" in q]
    assert len(pmax) == 1 and "PERFORMANCE_MAX" in pmax[0] and "keyword" not in pmax[0]


def test_the_requests_carry_what_google_asks_for():
    fake = FakeGoogle()
    _download(fake, env={**SECRETS, google.LOGIN_ENV: "987-654-3210"})
    method, url, headers, body = fake.requests[0]
    assert (method, url, headers["Content-type"]) == ("POST", google.TOKEN_URL, "application/x-www-form-urlencoded")
    assert urllib.parse.parse_qs(body) == {"grant_type": ["refresh_token"],
                                           "refresh_token": [SECRETS["GOOGLE_ADS_REFRESH_TOKEN"]],
                                           "client_id": [SECRETS["GOOGLE_ADS_CLIENT_ID"]],
                                           "client_secret": [SECRETS["GOOGLE_ADS_CLIENT_SECRET"]]}
    for method, url, headers, _ in fake.requests[1:]:
        assert (method, url) == ("POST", google.API.format(customer="1234567890"))
        assert headers["Authorization"] == f"Bearer {ACCESS}"
        assert headers["Developer-token"] == SECRETS["GOOGLE_ADS_DEVELOPER_TOKEN"]
        assert headers["Login-customer-id"] == "9876543210"


def test_no_login_customer_header_without_a_manager_account():
    fake = FakeGoogle()
    _download(fake)
    assert all("Login-customer-id" not in headers for _, _, headers, _ in fake.requests)


def test_no_credential_reaches_the_files():
    contents, _ = _download(FakeGoogle())
    for text in contents.values():
        for secret in [*SECRETS.values(), ACCESS]:
            assert secret not in text


def test_missing_credentials_are_named_before_any_call():
    fake = FakeGoogle()
    with pytest.raises(ValueError) as caught:
        _download(fake, env={"GOOGLE_ADS_CLIENT_ID": "x"})
    message = str(caught.value)
    assert all(name in message for name in google.CREDENTIALS if name != "GOOGLE_ADS_CLIENT_ID")
    assert "GOOGLE_ADS_CLIENT_ID" not in message.split("first")[0]
    assert fake.requests == []


@pytest.mark.parametrize("text, digits", [("123-456-7890", "1234567890"), ("123 456 7890", "1234567890"),
                                          ("1234567890", "1234567890")])
def test_a_customer_id_is_read_with_or_without_dashes(text, digits):
    assert google.customer_id(text) == digits


@pytest.mark.parametrize("text", ["12345", "123-456-789O", "1234567890/../1", ""])
def test_anything_else_is_not_a_customer_id(text):
    with pytest.raises(ValueError, match="not a Google Ads customer ID"):
        google.customer_id(text)


def _failure(code, status, error_code, message="Request contains an invalid argument. SENTINEL-free-text"):
    return [{"error": {"code": code, "message": message, "status": status, "details": [
        {"@type": "type.googleapis.com/google.ads.googleads.v25.errors.GoogleAdsFailure",
         "errors": [{"errorCode": error_code, "message": message}], "requestId": "abc"}]}}]


@pytest.mark.parametrize("token_answer, search_answer, says", [
    ((400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}), None,
     "Testing status expire after 7 days"),
    ((401, {"error": "invalid_client", "error_description": "The OAuth client was not found."}), None,
     "check GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET"),
    (None, (403, _failure(403, "PERMISSION_DENIED", {"authorizationError": "DEVELOPER_TOKEN_NOT_APPROVED"})),
     "only has test access"),
    (None, (403, _failure(403, "PERMISSION_DENIED", {"authorizationError": "USER_PERMISSION_DENIED"})),
     "set GOOGLE_ADS_LOGIN_CUSTOMER_ID"),
    (None, (429, _failure(429, "RESOURCE_EXHAUSTED", {"quotaError": "RESOURCE_EXHAUSTED"})), "daily limit"),
    (None, (401, {"error": {"code": 401, "message": "Request had invalid authentication credentials.",
                            "status": "UNAUTHENTICATED"}}), "refused the credentials"),
    (None, (500, _failure(500, "INTERNAL", {"internalError": "INTERNAL_ERROR"})),
     "answered HTTP 500 (INTERNAL, INTERNAL_ERROR)"),
    (None, (502, "<html>Bad Gateway</html>"), "answered HTTP 502"),
])
def test_google_errors_say_what_to_do_without_echoing_the_answer(token_answer, search_answer, says):
    fake = FakeGoogle(**{k: v for k, v in (("token_answer", token_answer), ("search_answer", search_answer)) if v})
    with pytest.raises(ValueError) as caught:
        _download(fake)
    message = str(caught.value)
    assert says in message
    assert "SENTINEL" not in message and "expired or revoked" not in message


def test_a_token_answer_without_an_access_token_stops_before_any_search():
    fake = FakeGoogle(token_answer=(200, {"token_type": "Bearer"}))
    with pytest.raises(ValueError, match="gave no access token"):
        _download(fake)
    assert len(fake.requests) == 1

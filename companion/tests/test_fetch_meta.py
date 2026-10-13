"""fetch meta against answers shaped like the Graph API's documentation: GET only, lists in pages (data, paging.next),
insights with actions, and errors as {"error": {"code", "type", "message", "fbtrace_id"}}."""
import datetime as dt
import json
import urllib.parse

import pytest

from openppc.templates import run_template
from openppc_online.fetch import files, http, meta

TOKEN = "EAAB-SENTINEL-1"
ENV = {meta.TOKEN_ENV: TOKEN}
TODAY = dt.date(2026, 10, 13)
INSIGHTS = {
    "2026-09-13": {"spend": "512.30", "impressions": "48000", "inline_link_clicks": "910",
                   "actions": [{"action_type": "link_click", "value": "910"}, {"action_type": "lead", "value": "31"},
                               {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "4"}]},
    "2026-08-14": {"spend": "470.00", "impressions": "45000", "inline_link_clicks": "860",
                   "actions": [{"action_type": "lead", "value": "40"},
                               {"action_type": "custom <script>SENTINEL</script>", "value": "2"}]},
}
LISTS = {
    "campaigns": [{"id": "1201", "name": "Leads - UK", "status": "ACTIVE"},
                  {"id": "1202", "name": "Retargeting", "status": "PAUSED"}],
    "adsets": [{"id": "2301", "name": "UK 25-54", "campaign_id": "1201", "status": "ACTIVE"}],
    "ads": [{"id": "3401", "name": "Video A", "adset_id": "2301", "status": "ACTIVE", "effective_status": "ACTIVE"},
            {"id": "3402", "name": "Carousel B", "adset_id": "2301", "status": "ACTIVE",
             "effective_status": "DISAPPROVED",
             "ad_review_feedback": {"global": {"Unacceptable Business Practices": "SENTINEL review text"}}}],
}


class FakeGraph:
    """graph.facebook.com for one account. Lists come one item a page, so every next link is followed."""

    def __init__(self, error=None, next_link=None):
        self.error, self.next_link, self.requests = error, next_link, []

    def __call__(self, req, timeout):
        self.requests.append((req.get_method(), req.full_url, dict(req.header_items())))
        if self.error:
            status, doc = self.error
            return status, json.dumps(doc).encode()
        parts = urllib.parse.urlsplit(req.full_url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        path = parts.path.removeprefix(f"/{meta.META.name}/")
        if path == "act_123456789":
            return 200, json.dumps({"name": "Acme Leads", "currency": "EUR", "id": "act_123456789"}).encode()
        if path == "act_123456789/insights":
            since = json.loads(query["time_range"])["since"]
            return 200, json.dumps({"data": [INSIGHTS[since]], "paging": {"cursors": {}}}).encode()
        edge = path.split("/")[1]
        at = int(query.get("after", "0"))
        page = {"data": LISTS[edge][at:at + 1]}
        if at + 1 < len(LISTS[edge]):
            nxt = self.next_link or (f"{meta.GRAPH}act_123456789/{edge}?access_token={TOKEN}"
                                     f"&fields={urllib.parse.quote(query['fields'])}&limit=500&after={at + 1}")
            page["paging"] = {"cursors": {"after": str(at + 1)}, "next": nxt}
        return 200, json.dumps(page).encode()


def _download(fake, conversion="lead", env=ENV, account="act_123456789"):
    return meta.download(account, env, http.Gate("meta", fake), today=TODAY, conversion=conversion)


def test_the_two_files_are_ones_the_audits_read(tmp_path):
    contents, notes = _download(FakeGraph())
    assert sorted(contents) == sorted(meta.NAMES) and "no search terms" in notes[0]
    by_name = {p.name: p for p in files.save(tmp_path, contents)}
    for template, name in (("account-read", "account.json"), ("account-structure", "account_structure.json")):
        markdown, facts, passed = run_template(template, by_name[name])
        assert markdown.startswith("#") and facts and passed, template


def test_the_files_carry_the_accounts_numbers_and_every_page():
    contents, _ = _download(FakeGraph())
    account = json.loads(contents["account.json"])
    assert account["meta"]["account"] == "Acme Leads" and account["meta"]["conversion"] == "lead"
    assert account["current"] == {"spend": 512.3, "impressions": 48000, "clicks": 910, "conversions": 31.0}
    assert account["prior"]["conversions"] == 40.0
    snapshot = json.loads(contents["account_structure.json"])
    assert [c["status"] for c in snapshot["campaigns"]] == ["ENABLED", "PAUSED"]
    assert [(a["approval"], a["policy"]) for a in snapshot["ads"]] \
        == [("APPROVED", []), ("DISAPPROVED", ["Unacceptable Business Practices"])]


def test_every_call_is_a_get_with_the_token_in_a_header_never_the_address():
    fake = FakeGraph()
    _download(fake)
    assert fake.requests and all(m == "GET" for m, _, _ in fake.requests)
    assert all(h == {"Authorization": f"Bearer {TOKEN}"} for _, _, h in fake.requests)
    assert all(TOKEN not in url for _, url, _ in fake.requests)
    assert sum("after=1" in url for _, url, _ in fake.requests) == 2  # campaigns and ads have a second page


@pytest.mark.parametrize("link", ["https://graph.facebook.com/v25.0/act_999/campaigns?after=1",
                                  "https://graph.facebook.com/v25.0/me/adaccounts?after=1"])
def test_a_next_page_on_another_list_is_not_followed(link):
    fake = FakeGraph(next_link=link)
    with pytest.raises(ValueError, match="pointed somewhere else"):
        _download(fake)
    assert not any(url.startswith(link.split("?")[0]) for _, url, _ in fake.requests)


def test_a_next_page_on_another_host_is_refused_by_the_gate():
    fake = FakeGraph(next_link="https://graph.evil.example/v25.0/act_123456789/campaigns?after=1")
    with pytest.raises(ValueError):
        _download(fake)
    assert not any("evil" in url for _, url, _ in fake.requests)


def test_without_a_conversion_the_error_lists_the_action_types_by_name_only():
    with pytest.raises(ValueError) as caught:
        _download(FakeGraph(), conversion=None)
    message = str(caught.value)
    assert "add --conversion" in message and "link_click (910), lead (71), offsite_conversion" in message
    assert "SENTINEL" not in message and "<script>" not in message


@pytest.mark.parametrize("conversion", ["lead; drop", "a", "<x>"])
def test_a_conversion_that_isnt_an_action_type_is_refused_before_any_call(conversion):
    fake = FakeGraph()
    with pytest.raises(ValueError, match="not a Meta action type"):
        _download(fake, conversion=conversion)
    assert fake.requests == []


def test_no_credential_reaches_the_files():
    contents, _ = _download(FakeGraph())
    assert all(TOKEN not in text for text in contents.values())


def test_a_missing_token_is_named_before_any_call():
    fake = FakeGraph()
    with pytest.raises(ValueError, match=f"set {meta.TOKEN_ENV} first"):
        _download(fake, env={})
    assert fake.requests == []


@pytest.mark.parametrize("text, act", [("act_123456789", "act_123456789"), ("123456789", "act_123456789"),
                                       (" 123-456-789 ", "act_123456789")])
def test_an_account_id_is_digits_with_or_without_act(text, act):
    assert meta.account_id(text) == act


@pytest.mark.parametrize("text", ["act_", "me", "act_123/../me", "act_12x"])
def test_anything_else_is_not_an_account_id(text):
    with pytest.raises(ValueError, match="not a Meta ad account ID"):
        meta.account_id(text)


def _error(code, subcode=None):
    error = {"message": "Error validating access token: SENTINEL free text", "type": "OAuthException", "code": code,
             "fbtrace_id": "AbC123"}
    if subcode:
        error["error_subcode"] = subcode
    return {"error": error}


@pytest.mark.parametrize("status, doc, says", [
    (400, _error(190, 463), "expired or was revoked"),
    (403, _error(10), "needs the ads_read permission"),
    (403, _error(200), "needs the ads_read permission"),
    (400, _error(17), "rate limit"),
    (400, _error(80000), "rate limit"),
    (400, _error(100, 33), "check the account ID"),
    (500, _error(1), "answered HTTP 500 (code 1)"),
    (502, "<html>SENTINEL</html>", "answered HTTP 502"),
])
def test_meta_errors_say_what_to_do_without_echoing_the_answer(status, doc, says):
    with pytest.raises(ValueError) as caught:
        _download(FakeGraph(error=(status, doc)))
    assert says in str(caught.value) and "SENTINEL" not in str(caught.value)

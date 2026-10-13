"""Google Ads through its API (GoogleAdsService.SearchStream, GAQL SELECT only), with your own developer token and
OAuth client, read from the environment variables Google's client libraries use.

Four files, each one the templates read: search_terms.csv (search-term-waste), keywords.csv (keyword-audit),
account.json (account-read: totals, these days vs the days before) and account_structure.json (account-structure:
campaigns, ad groups, keywords, negatives, ads with their review status, assets).
"""
import datetime as dt
import json
import re
import urllib.parse
from collections.abc import Mapping
from typing import Any

from . import files
from .http import Gate, HttpError, codes
from .versions import GOOGLE

API = f"https://googleads.googleapis.com/{GOOGLE.name}/customers/{{customer}}/googleAds:searchStream"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CREDENTIALS = ("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
               "GOOGLE_ADS_REFRESH_TOKEN")
LOGIN_ENV = "GOOGLE_ADS_LOGIN_CUSTOMER_ID"
NAMES = ["search_terms.csv", "keywords.csv", "account.json", "account_structure.json"]
MICROS = 1_000_000

MATCH = {"EXACT": "Exact match", "PHRASE": "Phrase match", "BROAD": "Broad match",
         "NEAR_EXACT": "Exact match (close variant)", "NEAR_PHRASE": "Phrase match (close variant)"}
CHANNEL = {"SEARCH": "Search", "PERFORMANCE_MAX": "Performance Max", "DISPLAY": "Display", "SHOPPING": "Shopping",
           "VIDEO": "Video", "DEMAND_GEN": "Demand Gen", "SMART": "Smart", "LOCAL": "Local"}
STATUS = {"ADDED": "Added", "EXCLUDED": "Excluded", "ADDED_EXCLUDED": "Added/Excluded"}
METRICS = "metrics.clicks, metrics.impressions, metrics.cost_micros, metrics.conversions"
ASSET_TYPES = "('SITELINK', 'CALLOUT', 'STRUCTURED_SNIPPET')"

Row = dict[str, Any]


def credentials(env: Mapping[str, str]) -> dict[str, str]:
    missing = [name for name in CREDENTIALS if not env.get(name)]
    if missing:
        raise ValueError(f"set {', '.join(missing)} first: fetch google uses your own Google Ads API access (a "
                         "developer token and an OAuth client with a refresh token). Without them, download the "
                         "reports from the Google Ads website and audit those files instead.")
    found = {name: env[name] for name in CREDENTIALS}
    if env.get(LOGIN_ENV):
        found[LOGIN_ENV] = customer_id(env[LOGIN_ENV])
    return found


def customer_id(text: str) -> str:
    digits = re.sub(r"[\s-]", "", str(text))
    if not re.fullmatch(r"\d{10}", digits):
        raise ValueError(f"{text!r} is not a Google Ads customer ID: it has 10 digits, like 123-456-7890")
    return digits


def field(row: Row, path: str, default: Any = None) -> Any:
    """row['campaignBudget']['amountMicros'] for 'campaign_budget.amount_micros'. The API's JSON leaves out fields at
    their default (0, false, empty), so a missing one is the default."""
    value: Any = row
    for part in path.split("."):
        key = re.sub(r"_([a-z0-9])", lambda m: m[1].upper(), part)
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def explain(status: int, body: bytes) -> str:
    """Google's error, in words that say what to do. Only code names come from the answer."""
    try:
        doc: Any = json.loads(body)
    except ValueError:
        doc = {}
    if isinstance(doc, list):  # searchStream sends its error inside the stream's array
        doc = doc[0] if doc and isinstance(doc[0], dict) else {}
    if not isinstance(doc, dict):
        doc = {}
    if doc.get("error") == "invalid_grant":
        return ("Google refused the refresh token: it was revoked or has expired. Refresh tokens of an OAuth app "
                "still in Testing status expire after 7 days: publish the app, or create a new refresh token")
    if doc.get("error") in ("invalid_client", "unauthorized_client"):
        return "Google refused the OAuth client: check GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET"
    error = doc.get("error") if isinstance(doc.get("error"), dict) else {}
    found = [str(c) for d in error.get("details") or [] if isinstance(d, dict)
             for e in d.get("errors") or [] if isinstance(e, dict)
             for c in (e.get("errorCode") or {}).values()]
    if "DEVELOPER_TOKEN_NOT_APPROVED" in found:
        return ("your developer token only has test access, which reaches test accounts only. Apply for Basic "
                "access in the API Center of your Google Ads manager account")
    if "USER_PERMISSION_DENIED" in found:
        return (f"this login can't read that account. For an account under a manager account, set {LOGIN_ENV} to "
                "the manager's customer ID")
    if status == 429 or "RESOURCE_EXHAUSTED" in found or error.get("status") == "RESOURCE_EXHAUSTED":
        return ("Google's daily limit for your API project is reached. Try again tomorrow, or download the reports "
                "from the Google Ads website")
    if status == 401:
        return "Google refused the credentials: check the developer token and the refresh token"
    shown = codes([str(error.get("status") or ""), *found])
    return f"the Google Ads API answered HTTP {status}" + (f" ({', '.join(shown)})" if shown else "")


class Client:
    def __init__(self, creds: dict[str, str], gate: Gate):
        self.creds, self.gate, self.token = creds, gate, ""

    def _json(self, url: str, headers: dict[str, str], body: bytes) -> Any:
        try:
            return json.loads(self.gate.call("POST", url, headers, body))
        except HttpError as e:
            raise ValueError(explain(e.status, e.body)) from None

    def authorize(self) -> None:
        body = urllib.parse.urlencode({
            "grant_type": "refresh_token", "refresh_token": self.creds["GOOGLE_ADS_REFRESH_TOKEN"],
            "client_id": self.creds["GOOGLE_ADS_CLIENT_ID"],
            "client_secret": self.creds["GOOGLE_ADS_CLIENT_SECRET"]}).encode()
        answer = self._json(TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, body)
        self.token = str(answer.get("access_token") or "")
        if not self.token:
            raise ValueError("Google's token endpoint gave no access token")

    def search(self, customer: str, query: str) -> list[Row]:
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                   "developer-token": self.creds["GOOGLE_ADS_DEVELOPER_TOKEN"]}
        if self.creds.get(LOGIN_ENV):
            headers["login-customer-id"] = self.creds[LOGIN_ENV]
        batches = self._json(API.format(customer=customer), headers, json.dumps({"query": query}).encode())
        return [row for batch in batches or [] for row in batch.get("results", [])]


def _between(start: dt.date, end: dt.date) -> str:
    return f"segments.date BETWEEN '{start}' AND '{end}'"


def _money(row: Row, path: str = "metrics.cost_micros") -> float:
    return round(int(field(row, path, 0)) / MICROS, 2)


def _performance(row: Row) -> list[Any]:
    return [int(field(row, "metrics.clicks", 0)), int(field(row, "metrics.impressions", 0)), _money(row),
            round(float(field(row, "metrics.conversions", 0)), 2)]


def search_terms(client: Client, customer: str, start: dt.date, end: dt.date, currency: str) -> list[list[Any]]:
    rows = client.search(customer, f"""
        SELECT search_term_view.search_term, search_term_view.status, segments.search_term_match_type,
               campaign.name, campaign.advertising_channel_type, ad_group.name, {METRICS}
        FROM search_term_view WHERE {_between(start, end)}""")
    return [[field(r, "search_term_view.search_term", ""),
             MATCH.get(field(r, "segments.search_term_match_type"), ""),
             STATUS.get(field(r, "search_term_view.status"), "None"), field(r, "campaign.name", ""),
             CHANNEL.get(field(r, "campaign.advertising_channel_type"), "Search"), field(r, "ad_group.name", ""),
             *_performance(r), currency] for r in rows]


def pmax_terms(client: Client, customer: str, start: dt.date, end: dt.date, currency: str) -> list[list[Any]]:
    """Performance Max search terms, which search_term_view leaves out. A keyword segment here would drop them."""
    rows = client.search(customer, f"""
        SELECT campaign_search_term_view.search_term, campaign.name, {METRICS}
        FROM campaign_search_term_view
        WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX' AND {_between(start, end)}""")
    return [[field(r, "campaign_search_term_view.search_term", ""), "", "None", field(r, "campaign.name", ""),
             CHANNEL["PERFORMANCE_MAX"], "", *_performance(r), currency] for r in rows]


def keywords(client: Client, customer: str, start: dt.date, end: dt.date, currency: str) -> list[list[Any]]:
    rows = client.search(customer, f"""
        SELECT ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type,
               ad_group_criterion.quality_info.quality_score, campaign.name, ad_group.name, {METRICS}
        FROM keyword_view WHERE {_between(start, end)}""")
    return [[field(r, "ad_group_criterion.keyword.text", ""),
             MATCH.get(field(r, "ad_group_criterion.keyword.match_type"), ""), field(r, "campaign.name", ""),
             field(r, "ad_group.name", ""), *_performance(r),
             field(r, "ad_group_criterion.quality_info.quality_score", ""), currency] for r in rows]


def totals(client: Client, customer: str, start: dt.date, end: dt.date) -> dict[str, float]:
    rows = client.search(customer, f"SELECT {METRICS} FROM customer WHERE {_between(start, end)}")
    sums = [sum(x) for x in zip(*(_performance(r) for r in rows), strict=True)] if rows else [0, 0, 0, 0]
    return {"spend": round(sums[2], 2), "impressions": sums[1], "clicks": sums[0], "conversions": round(sums[3], 2)}


def structure(client: Client, customer: str) -> dict[str, list[Row]]:
    """The account snapshot the core's ingest/account.py reads, field for field."""
    def q(sql: str) -> list[Row]:
        return client.search(customer, sql)

    camps = [{"id": field(r, "campaign.id"), "name": field(r, "campaign.name"), "status": field(r, "campaign.status"),
              "channel": field(r, "campaign.advertising_channel_type"),
              "bidding": field(r, "campaign.bidding_strategy_type"),
              "display_network": field(r, "campaign.network_settings.target_content_network", False),
              "geo_target_type": field(r, "campaign.geo_target_type_setting.positive_geo_target_type"),
              "budget": _money(r, "campaign_budget.amount_micros") or None,
              "budget_limited": "BUDGET_CONSTRAINED" in field(r, "campaign.primary_status_reasons", [])}
             for r in q("""SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type,
                    campaign.bidding_strategy_type, campaign.network_settings.target_content_network,
                    campaign.geo_target_type_setting.positive_geo_target_type, campaign_budget.amount_micros,
                    campaign.primary_status_reasons
                    FROM campaign WHERE campaign.status != 'REMOVED'""")]
    groups = [{"id": field(r, "ad_group.id"), "campaign_id": field(r, "campaign.id"), "name": field(r, "ad_group.name"),
               "status": field(r, "ad_group.status")}
              for r in q("SELECT ad_group.id, campaign.id, ad_group.name, ad_group.status FROM ad_group "
                         "WHERE ad_group.status != 'REMOVED'")]
    criteria = q("""SELECT ad_group.id, ad_group_criterion.negative, ad_group_criterion.keyword.text,
                    ad_group_criterion.keyword.match_type, ad_group_criterion.status,
                    ad_group_criterion.system_serving_status, ad_group_criterion.quality_info.quality_score,
                    ad_group_criterion.quality_info.search_predicted_ctr,
                    ad_group_criterion.quality_info.creative_quality_score,
                    ad_group_criterion.quality_info.post_click_quality_score, ad_group_criterion.approval_status
                    FROM ad_group_criterion
                    WHERE ad_group_criterion.type = 'KEYWORD' AND ad_group_criterion.status != 'REMOVED'""")
    kws = [{"ad_group_id": field(r, "ad_group.id"), "text": field(r, "ad_group_criterion.keyword.text", ""),
            "match_type": field(r, "ad_group_criterion.keyword.match_type"),
            "status": field(r, "ad_group_criterion.status"),
            "serving": field(r, "ad_group_criterion.system_serving_status"),
            "quality_score": field(r, "ad_group_criterion.quality_info.quality_score"),
            "expected_ctr": field(r, "ad_group_criterion.quality_info.search_predicted_ctr"),
            "ad_relevance": field(r, "ad_group_criterion.quality_info.creative_quality_score"),
            "landing_page": field(r, "ad_group_criterion.quality_info.post_click_quality_score"),
            "approval": field(r, "ad_group_criterion.approval_status")}
           for r in criteria if not field(r, "ad_group_criterion.negative", False)]
    negatives = [{"level": "AD_GROUP", "owner_id": field(r, "ad_group.id"),
                  "text": field(r, "ad_group_criterion.keyword.text", ""),
                  "match_type": field(r, "ad_group_criterion.keyword.match_type"),
                  "status": field(r, "ad_group_criterion.status")}
                 for r in criteria if field(r, "ad_group_criterion.negative", False)]
    negatives += [{"level": "CAMPAIGN", "owner_id": field(r, "campaign.id"),
                   "text": field(r, "campaign_criterion.keyword.text", ""),
                   "match_type": field(r, "campaign_criterion.keyword.match_type")}
                  for r in q("""SELECT campaign.id, campaign_criterion.keyword.text,
                         campaign_criterion.keyword.match_type FROM campaign_criterion
                         WHERE campaign_criterion.type = 'KEYWORD' AND campaign_criterion.negative = TRUE""")]
    ads = [{"ad_group_id": field(r, "ad_group.id"), "type": field(r, "ad_group_ad.ad.type"),
            "status": field(r, "ad_group_ad.status"), "strength": field(r, "ad_group_ad.ad_strength"),
            "name": field(r, "ad_group_ad.ad.name", ""),
            "approval": field(r, "ad_group_ad.policy_summary.approval_status"),
            "policy": [e.get("topic", "") for e in field(r, "ad_group_ad.policy_summary.policy_topic_entries", [])],
            **{part: [{"text": a.get("text", ""), "pin": a.get("pinnedField")}
                      for a in field(r, f"ad_group_ad.ad.responsive_search_ad.{part}", [])]
               for part in ("headlines", "descriptions")}}
           for r in q("""SELECT ad_group.id, ad_group_ad.ad.type, ad_group_ad.ad.name, ad_group_ad.status,
                  ad_group_ad.ad_strength, ad_group_ad.policy_summary.approval_status,
                  ad_group_ad.policy_summary.policy_topic_entries,
                  ad_group_ad.ad.responsive_search_ad.headlines, ad_group_ad.ad.responsive_search_ad.descriptions
                  FROM ad_group_ad WHERE ad_group_ad.status != 'REMOVED'""")]
    assets = [{"level": "CAMPAIGN", "owner_id": field(r, "campaign.id"), "type": field(r, "campaign_asset.field_type"),
               "status": field(r, "campaign_asset.status")}
              for r in q(f"""SELECT campaign.id, campaign_asset.field_type, campaign_asset.status FROM campaign_asset
                     WHERE campaign_asset.field_type IN {ASSET_TYPES} AND campaign_asset.status != 'REMOVED'""")]
    assets += [{"level": "ACCOUNT", "owner_id": "", "type": field(r, "customer_asset.field_type"),
                "status": field(r, "customer_asset.status")}
               for r in q(f"""SELECT customer_asset.field_type, customer_asset.status FROM customer_asset
                      WHERE customer_asset.field_type IN {ASSET_TYPES} AND customer_asset.status != 'REMOVED'""")]
    return {"campaigns": camps, "ad_groups": groups, "keywords": kws, "negatives": negatives, "ads": ads,
            "assets": assets}


def download(customer: str, env: Mapping[str, str], gate: Gate, days: int = files.DAYS,
             today: dt.date | None = None) -> tuple[dict[str, str], list[str]]:
    """The four files' contents by name, and notes on what they leave out."""
    cid = customer_id(customer)
    client = Client(credentials(env), gate)
    client.authorize()
    account = client.search(cid, "SELECT customer.descriptive_name, customer.currency_code FROM customer")
    name = field(account[0], "customer.descriptive_name", cid) if account else cid
    currency = field(account[0], "customer.currency_code", "USD") if account else "USD"
    start, end, prior_start, prior_end = files.window(days, today)
    performance = ["Clicks", "Impr.", "Cost", "Conversions"]
    terms = search_terms(client, cid, start, end, currency) + pmax_terms(client, cid, start, end, currency)
    kws = keywords(client, cid, start, end, currency)
    current, prior = totals(client, cid, start, end), totals(client, cid, prior_start, prior_end)
    snap = structure(client, cid)
    meta = {"account": name, "currency": currency, "customer_id": cid,
            "window": files.span(start, end, prior_start, prior_end), "source": f"Google Ads API {GOOGLE.name}"}
    out = {
        "search_terms.csv": files.report(
            "Search terms report", start, end,
            ["Search term", "Match type", "Added/Excluded", "Campaign", "Campaign type", "Ad group", *performance,
             "Currency code"], terms),
        "keywords.csv": files.report(
            "Search keyword report", start, end,
            ["Keyword", "Match type", "Campaign", "Ad group", *performance, "Quality Score", "Currency code"], kws),
        "account.json": files.as_json({"meta": meta, "current": current, "prior": prior}),
        "account_structure.json": files.as_json(
            {"meta": {"account": name, "currency": currency, "captured": str(end + dt.timedelta(days=1))}, **snap}),
    }
    return out, []

"""Microsoft Advertising through the Reporting service's REST API (v13): submit a report request, ask until it's
ready, download it. With your own developer token and app registration, read from the environment.

Three files, each one the templates read: search_terms.csv (search-term-waste), keywords.csv (keyword-audit) and
account.json (account-read: totals, these days vs the days before).
"""
import csv
import datetime as dt
import io
import json
import re
import time
import urllib.parse
import zipfile
from collections.abc import Callable, Mapping
from typing import Any

from . import files
from .http import MOST, Gate, HttpError, codes
from .versions import MICROSOFT

REPORTING = f"https://reporting.api.bingads.microsoft.com/Reporting/{MICROSOFT.name}/GenerateReport/{{}}"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
SCOPE = "https://ads.microsoft.com/msads.manage offline_access"
CREDENTIALS = ("MICROSOFT_ADS_DEVELOPER_TOKEN", "MICROSOFT_ADS_CLIENT_ID", "MICROSOFT_ADS_REFRESH_TOKEN",
               "MICROSOFT_ADS_CUSTOMER_ID")
SECRET_ENV = "MICROSOFT_ADS_CLIENT_SECRET"  # only a web app registration has one
NAMES = ["search_terms.csv", "keywords.csv", "account.json"]
WAIT_FIRST, WAIT_MOST, WAIT_TOTAL = 2, 30, 600  # seconds between polls, rising; the longest a report may take
PERFORMANCE = ["Clicks", "Impressions", "Spend", "Conversions"]
MATCH = {"Exact": "Exact match", "Phrase": "Phrase match", "Broad": "Broad match"}
SEARCH_TYPES = ("Search & content", "Search")

Row = dict[str, str]


def credentials(env: Mapping[str, str]) -> dict[str, str]:
    missing = [name for name in CREDENTIALS if not env.get(name)]
    if missing:
        raise ValueError(f"set {', '.join(missing)} first: fetch microsoft uses your own Microsoft Advertising API "
                         "access (a developer token and an app registration with a refresh token). Without them, "
                         "download the reports from the Microsoft Advertising website and audit those files instead.")
    found = {name: env[name] for name in (*CREDENTIALS, SECRET_ENV) if env.get(name)}
    found["MICROSOFT_ADS_CUSTOMER_ID"] = _digits(found["MICROSOFT_ADS_CUSTOMER_ID"], "MICROSOFT_ADS_CUSTOMER_ID")
    return found


def _digits(text: str, what: str) -> str:
    digits = re.sub(r"[\s-]", "", str(text))
    if not re.fullmatch(r"\d{1,19}", digits):
        raise ValueError(f"{what} {text!r} isn't a Microsoft Advertising ID: it is all digits, like 149123456")
    return digits


def account_id(text: str) -> str:
    try:
        return _digits(text, "the account ID")
    except ValueError:
        raise ValueError(f"{text!r} is not a Microsoft Advertising account ID: it is all digits, like 149123456 "
                         "(the account number that starts with a letter is a different thing)") from None


def _values(doc: Any, key: str) -> list[str]:
    """Every value under key, anywhere in Microsoft's error JSON."""
    if isinstance(doc, dict):
        return [str(v) for k, v in doc.items() if k == key and v] + [c for v in doc.values() for c in _values(v, key)]
    if isinstance(doc, list):
        return [c for v in doc for c in _values(v, key)]
    return []


def explain(status: int, body: bytes) -> str:
    """Microsoft's error, in words that say what to do. Only code names come from the answer."""
    try:
        doc: Any = json.loads(body)
    except ValueError:
        doc = {}
    if isinstance(doc, dict) and doc.get("error") == "invalid_grant":
        return ("Microsoft refused the refresh token: it was revoked or has expired (unused for 90 days). Sign in "
                "again to get a new one")
    if isinstance(doc, dict) and doc.get("error") in ("invalid_client", "unauthorized_client"):
        return f"Microsoft refused the app registration: check MICROSOFT_ADS_CLIENT_ID (and {SECRET_ENV} for a web app)"
    found = set(_values(doc, "ErrorCode"))
    if status == 401 or {"InvalidCredentials", "AuthenticationTokenExpired"} & found:
        return "Microsoft refused the credentials: check the developer token and the refresh token"
    if {"UserIsNotAuthorized", "InvalidCustomerAccountId", "InvalidCustomerId", "InvalidAccountId"} & found:
        return ("this login can't read that account: check the account ID, and set MICROSOFT_ADS_CUSTOMER_ID to the "
                "manager account (customer) it belongs to")
    if status == 429 or {"CallRateExceeded", "ConcurrentRequestOverLimit"} & found:
        return "Microsoft Advertising is limiting calls from your developer token; wait a minute and try again"
    shown = codes(sorted(found))
    return f"Microsoft Advertising answered HTTP {status}" + (f" ({', '.join(shown)})" if shown else "")


def _day(d: dt.date) -> dict[str, int]:
    return {"Day": d.day, "Month": d.month, "Year": d.year}


def _csv(data: bytes, kind: str) -> list[Row]:
    """The one CSV in the report's zip, read whole only if it fits under the size fetch reads."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            members = [i for i in z.infolist() if not i.is_dir()]
            if len(members) != 1 or members[0].file_size > MOST:
                raise ValueError(f"Microsoft Advertising's {kind} file isn't one report under "
                                 f"{MOST // 1024 // 1024} MB; ask for fewer days")
            text = z.read(members[0]).decode("utf-8-sig")
    except (zipfile.BadZipFile, UnicodeDecodeError):
        raise ValueError(f"Microsoft Advertising's {kind} download wasn't the zipped CSV it should be") from None
    return list(csv.DictReader(io.StringIO(text)))


class Client:
    def __init__(self, creds: dict[str, str], account: str, gate: Gate,
                 sleep: Callable[[float], object] = time.sleep):
        self.creds, self.account, self.gate, self.sleep, self.token = creds, account, gate, sleep, ""

    def _call(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes | None = None) -> bytes:
        try:
            return self.gate.call(method, url, headers, body)
        except HttpError as e:
            raise ValueError(explain(e.status, e.body)) from None

    def authorize(self) -> None:
        fields = {"grant_type": "refresh_token", "refresh_token": self.creds["MICROSOFT_ADS_REFRESH_TOKEN"],
                  "client_id": self.creds["MICROSOFT_ADS_CLIENT_ID"], "scope": SCOPE}
        if self.creds.get(SECRET_ENV):
            fields["client_secret"] = self.creds[SECRET_ENV]
        answer = json.loads(self._call("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"},
                                       urllib.parse.urlencode(fields).encode()))
        self.token = str(answer.get("access_token") or "") if isinstance(answer, dict) else ""
        if not self.token:
            raise ValueError("Microsoft's token endpoint gave no access token")

    def _post(self, action: str, body: dict[str, Any]) -> Any:
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                   "DeveloperToken": self.creds["MICROSOFT_ADS_DEVELOPER_TOKEN"],
                   "CustomerId": self.creds["MICROSOFT_ADS_CUSTOMER_ID"], "CustomerAccountId": self.account}
        return json.loads(self._call("POST", REPORTING.format(action), headers, json.dumps(body).encode()))

    def report(self, kind: str, columns: list[str], start: dt.date, end: dt.date) -> list[Row]:
        """One report's rows, totalled over the days (Summary aggregation). No rows when there was no data."""
        request = {"Type": f"{kind}Request", "Format": "Csv", "ReportName": f"OpenPPC {kind}",
                   "ReturnOnlyCompleteData": False, "ExcludeReportHeader": True, "ExcludeReportFooter": True,
                   "ExcludeColumnHeaders": False, "Aggregation": "Summary", "Columns": columns,
                   "Scope": {"AccountIds": [int(self.account)]},
                   "Time": {"CustomDateRangeStart": _day(start), "CustomDateRangeEnd": _day(end)}}
        rid = (self._post("Submit", {"ReportRequest": request}) or {}).get("ReportRequestId")
        if not rid:
            raise ValueError(f"Microsoft Advertising didn't accept the {kind} request")
        waited, wait = 0.0, float(WAIT_FIRST)
        while True:
            status = (self._post("Poll", {"ReportRequestId": rid}) or {}).get("ReportRequestStatus") or {}
            if status.get("Status") == "Success":
                break
            if status.get("Status") != "Pending":
                shown = codes([str(status.get("Status") or "")])
                raise ValueError(f"Microsoft Advertising couldn't build the {kind}"
                                 + (f" (status {shown[0]})" if shown else ""))
            if waited >= WAIT_TOTAL:
                raise ValueError(f"the {kind} wasn't ready after {WAIT_TOTAL // 60} minutes; try again later")
            self.sleep(wait)
            waited, wait = waited + wait, min(wait * 2, WAIT_MOST)
        url = status.get("ReportDownloadUrl")
        if not url:
            return []  # Microsoft builds no file when the days have no data
        self.gate.allow_download(str(url))
        return _csv(self._call("GET", str(url)), kind)


def _num(row: Row, key: str) -> float:
    try:
        return float((row.get(key) or "0").replace(",", ""))
    except ValueError:
        return 0.0


def _performance(row: Row) -> list[Any]:
    return [int(_num(row, "Clicks")), int(_num(row, "Impressions")), round(_num(row, "Spend"), 2),
            round(_num(row, "Conversions"), 2)]


def _totals(rows: list[Row]) -> dict[str, float]:
    sums = [sum(x) for x in zip(*(_performance(r) for r in rows), strict=True)] if rows else [0, 0, 0, 0]
    return {"spend": round(sums[2], 2), "impressions": sums[1], "clicks": sums[0], "conversions": round(sums[3], 2)}


def download(account: str, env: Mapping[str, str], gate: Gate, days: int = files.DAYS, today: dt.date | None = None,
             sleep: Callable[[float], object] = time.sleep) -> tuple[dict[str, str], list[str]]:
    """The three files' contents by name, and notes on what they leave out."""
    aid = account_id(account)
    client = Client(credentials(env), aid, gate, sleep)
    client.authorize()
    start, end, prior_start, prior_end = files.window(days, today)
    account_columns = ["AccountName", "CurrencyCode", *PERFORMANCE]
    current = client.report("AccountPerformanceReport", account_columns, start, end)
    prior = client.report("AccountPerformanceReport", account_columns, prior_start, prior_end)
    currency = next((r["CurrencyCode"] for r in current + prior if r.get("CurrencyCode")), "USD")
    name = next((r["AccountName"] for r in current + prior if r.get("AccountName")), aid)
    terms = client.report("SearchQueryPerformanceReport", ["SearchQuery", "DeliveredMatchType", "CampaignName",
                                                           "CampaignType", "AdGroupName", *PERFORMANCE], start, end)
    kws = client.report("KeywordPerformanceReport", ["Keyword", "BidMatchType", "CampaignName", "AdGroupName",
                                                     *PERFORMANCE, "QualityScore"], start, end)
    performance = ["Clicks", "Impr.", "Cost", "Conversions"]
    meta = {"account": name, "currency": currency, "account_id": aid,
            "window": files.span(start, end, prior_start, prior_end),
            "source": f"Microsoft Advertising Reporting API {MICROSOFT.name}"}
    out = {
        "search_terms.csv": files.report(
            "Search query performance report", start, end,
            ["Search term", "Match type", "Campaign", "Campaign type", "Ad group", *performance, "Currency code"],
            [[r.get("SearchQuery", ""), MATCH.get(r.get("DeliveredMatchType", ""), r.get("DeliveredMatchType", "")),
              r.get("CampaignName", ""),
              "Search" if r.get("CampaignType", "") in SEARCH_TYPES else r.get("CampaignType", ""),
              r.get("AdGroupName", ""), *_performance(r), currency] for r in terms]),
        "keywords.csv": files.report(
            "Keyword performance report", start, end,
            ["Keyword", "Match type", "Campaign", "Ad group", *performance, "Quality Score", "Currency code"],
            [[r.get("Keyword", ""), MATCH.get(r.get("BidMatchType", ""), r.get("BidMatchType", "")),
              r.get("CampaignName", ""), r.get("AdGroupName", ""), *_performance(r),
              r.get("QualityScore", "").replace("--", ""), currency] for r in kws]),
        "account.json": files.as_json({"meta": meta, "current": _totals(current), "prior": _totals(prior)}),
    }
    notes = [f"Microsoft Advertising had no {what} for {files.long_date(start)} to {files.long_date(end)}, so "
             f"{name_} has no rows" for what, rows, name_ in (("search terms", terms, "search_terms.csv"),
                                                             ("keyword data", kws, "keywords.csv")) if not rows]
    return out, notes

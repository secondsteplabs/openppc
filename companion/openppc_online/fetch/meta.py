"""Meta through the Marketing API (Graph API), GET only, with your own access token (the ads_read permission), read
from META_ACCESS_TOKEN and sent in a header, never in an address.

Two files, each one the templates read: account.json (account-read: spend, impressions, link clicks and conversions,
these days vs the days before) and account_structure.json (account-structure: campaigns, ad sets and ads with their
review status, for the policy check). Meta counts many kinds of action, so --conversion names the one that is a
conversion for this account; without it, the error lists the action types the account recorded.
"""
import datetime as dt
import json
import re
import urllib.parse
from collections import Counter
from collections.abc import Mapping
from typing import Any

from . import files
from .http import Gate, HttpError, codes
from .versions import META

GRAPH = f"https://graph.facebook.com/{META.name}/"
TOKEN_ENV = "META_ACCESS_TOKEN"
NAMES = ["account.json", "account_structure.json"]
PAGE_SIZE = 500
MAX_PAGES = 200  # of one list: 100,000 ads is past any account this is for
ACTION_TYPES_SHOWN = 20
STATUS = {"ACTIVE": "ENABLED", "PAUSED": "PAUSED", "ARCHIVED": "REMOVED", "DELETED": "REMOVED"}
APPROVAL = {"DISAPPROVED": "DISAPPROVED", "WITH_ISSUES": "WITH_ISSUES", "PENDING_REVIEW": "UNDER_REVIEW",
            "IN_PROCESS": "UNDER_REVIEW"}  # every other effective status means the ad passed review
RATE_LIMITS = frozenset({4, 17, 32, 613, *range(80000, 80015)})

Row = dict[str, Any]


def token(env: Mapping[str, str]) -> str:
    if not env.get(TOKEN_ENV):
        raise ValueError(f"set {TOKEN_ENV} first: fetch meta uses your own access token with the ads_read "
                         "permission (a system user's token from Business Settings, or a user token). Without one, "
                         "export the report from Ads Manager and audit that file instead.")
    return env[TOKEN_ENV]


def account_id(text: str) -> str:
    digits = re.sub(r"^act_|[\s-]", "", str(text).strip())
    if not re.fullmatch(r"\d{1,20}", digits):
        raise ValueError(f"{text!r} is not a Meta ad account ID: it is digits, like act_123456789 or 123456789")
    return f"act_{digits}"


def conversion_name(text: str) -> str:
    if not codes([text]):
        raise ValueError(f"{text!r} is not a Meta action type, like lead or offsite_conversion.fb_pixel_purchase")
    return text


def explain(status: int, body: bytes) -> str:
    """Meta's error, in words that say what to do. Only its code comes from the answer."""
    try:
        doc: Any = json.loads(body)
    except ValueError:
        doc = {}
    error: Any = doc.get("error") if isinstance(doc, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    if code == 190:
        return f"Meta refused the access token: it has expired or was revoked. Create a new one and set {TOKEN_ENV}"
    if code == 10 or (isinstance(code, int) and 200 <= code < 300):
        return ("this token can't read that ad account: it needs the ads_read permission and access to the account "
                "(in Business Settings, assign the account to the system user)")
    if code in RATE_LIMITS:
        return "Meta's rate limit for this account is reached. Wait an hour and try again"
    if code == 100:
        return "Meta doesn't know that ad account, or this token can't see it: check the account ID"
    return f"the Marketing API answered HTTP {status}" + (f" (code {code})" if isinstance(code, int) else "")


class Client:
    def __init__(self, access_token: str, gate: Gate):
        self.token, self.gate = access_token, gate

    def _get(self, url: str) -> Row:
        try:
            answer = json.loads(self.gate.call("GET", url, {"Authorization": f"Bearer {self.token}"}))
        except HttpError as e:
            raise ValueError(explain(e.status, e.body)) from None
        return answer if isinstance(answer, dict) else {}

    def get(self, path: str, **params: Any) -> Row:
        return self._get(GRAPH + path + "?" + urllib.parse.urlencode(params))

    def pages(self, path: str, **params: Any) -> list[Row]:
        """Every item of a list, following Meta's next-page links while they stay on the same list."""
        page = self.get(path, limit=PAGE_SIZE, **params)
        out = list(page.get("data") or [])
        for _ in range(MAX_PAGES):
            nxt = str((page.get("paging") or {}).get("next") or "")
            if not nxt:
                break
            parts = urllib.parse.urlsplit(nxt)
            if parts.path != urllib.parse.urlsplit(GRAPH + path).path:
                raise ValueError(f"Meta's next page of {path.split('/')[-1]} pointed somewhere else; stopped")
            query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k != "access_token"]
            page = self._get(parts._replace(query=urllib.parse.urlencode(query)).geturl())
            out += page.get("data") or []
        return out


def insights(client: Client, act: str, start: dt.date, end: dt.date) -> Row:
    rows = client.pages(f"{act}/insights", level="account", fields="spend,impressions,inline_link_clicks,actions",
                        time_range=json.dumps({"since": str(start), "until": str(end)}))
    return rows[0] if rows else {}


def actions(row: Row) -> dict[str, float]:
    return {str(a["action_type"]): float(a.get("value", 0)) for a in row.get("actions") or []
            if isinstance(a, dict) and a.get("action_type")}


def totals(row: Row, conversion: str) -> dict[str, float]:
    return {"spend": round(float(row.get("spend", 0)), 2), "impressions": int(row.get("impressions", 0)),
            "clicks": int(row.get("inline_link_clicks", 0)), "conversions": round(actions(row).get(conversion, 0), 2)}


def _reasons(ad: Row) -> list[str]:
    """The policies an ad's review named, from ad_review_feedback (overall, then per placement)."""
    feedback = ad.get("ad_review_feedback") or {}
    names = list(feedback.get("global") or {})
    for per in (feedback.get("placement_specific") or {}).values():
        names += [n for n in per or {} if n not in names]
    return names


def structure(client: Client, act: str) -> dict[str, list[Row]]:
    """The account snapshot the core's ingest/account.py reads: ad sets are its ad groups."""
    camps = [{"id": c["id"], "name": c.get("name", c["id"]), "status": STATUS.get(c.get("status", ""), c.get("status")),
              "channel": "META"} for c in client.pages(f"{act}/campaigns", fields="id,name,status")]
    sets = [{"id": s["id"], "campaign_id": s.get("campaign_id", ""), "name": s.get("name", s["id"]),
             "status": STATUS.get(s.get("status", ""), s.get("status"))}
            for s in client.pages(f"{act}/adsets", fields="id,name,campaign_id,status")]
    ads = [{"ad_group_id": a.get("adset_id", ""), "name": a.get("name", a["id"]), "type": "META_AD",
            "status": STATUS.get(a.get("status", ""), a.get("status")),
            "approval": APPROVAL.get(a.get("effective_status", ""), "APPROVED"), "policy": _reasons(a)}
           for a in client.pages(f"{act}/ads", fields="id,name,adset_id,status,effective_status,ad_review_feedback")]
    return {"campaigns": camps, "ad_groups": sets, "ads": ads}


def download(account: str, env: Mapping[str, str], gate: Gate, days: int = files.DAYS, today: dt.date | None = None,
             conversion: str | None = None) -> tuple[dict[str, str], list[str]]:
    """The two files' contents by name, and notes on what they leave out."""
    act = account_id(account)
    if conversion:
        conversion = conversion_name(conversion)
    client = Client(token(env), gate)
    start, end, prior_start, prior_end = files.window(days, today)
    current, prior = insights(client, act, start, end), insights(client, act, prior_start, prior_end)
    if not conversion:
        both = Counter(actions(prior)) + Counter(actions(current))
        seen = sorted(both.items(), key=lambda kv: -kv[1])
        shown = [(k, v) for k, v in seen if codes([k])][:ACTION_TYPES_SHOWN]
        listed = ", ".join(f"{k} ({v:g})" for k, v in shown) or "none in these days"
        raise ValueError("add --conversion ACTION_TYPE: Meta counts many kinds of action, so name the one that is a "
                         f"conversion for this account. Its actions, last {days} days and the days before: {listed}")
    info = client.get(act, fields="name,currency")
    name, currency = info.get("name", act), info.get("currency", "USD")
    meta = {"account": name, "currency": currency, "account_id": act, "conversion": conversion,
            "window": files.span(start, end, prior_start, prior_end),
            "source": f"Meta Marketing API {META.name}; clicks are link clicks"}
    out = {
        "account.json": files.as_json({"meta": meta, "current": totals(current, conversion),
                                       "prior": totals(prior, conversion)}),
        "account_structure.json": files.as_json(
            {"meta": {"account": name, "currency": currency, "captured": str(end + dt.timedelta(days=1))},
             **structure(client, act)}),
    }
    return out, ["Meta has no search terms or keywords, so fetch meta writes account.json and "
                 "account_structure.json only"]

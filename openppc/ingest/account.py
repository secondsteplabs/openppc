"""Account snapshot: how an account is built (campaigns, ad groups, keywords, negatives, ads,
assets), in one normalized shape whatever file it came from.

It reads OpenPPC's own snapshot JSON here; openppc/ingest/editor.py reads a Google Ads Editor
whole-account export into this same shape, so the structure checks never care which file the
account came from.

    {"meta": {"account": "Acme Plumbing", "currency": "USD", "captured": "2026-09-28"},
     "campaigns": [{"id": "1", "name": "Acme | Search", "status": "ENABLED", "channel": "SEARCH",
                    "bidding": "MAXIMIZE_CONVERSIONS", "enhanced_cpc": false,
                    "display_network": false, "geo_target_type": "PRESENCE",
                    "budget": 50.0, "budget_limited": false}],
     "ad_groups": [{"id": "11", "campaign_id": "1", "name": "Plumbing repair", "status": "ENABLED"}],
     "keywords": [{"ad_group_id": "11", "text": "plumbing repair", "match_type": "PHRASE",
                   "status": "ENABLED", "serving": "ELIGIBLE", "quality_score": 7,
                   "expected_ctr": "AVERAGE", "ad_relevance": "AVERAGE", "landing_page": "AVERAGE",
                   "approval": "APPROVED"}],
     "negatives": [{"level": "CAMPAIGN", "owner_id": "1", "text": "free", "match_type": "BROAD"}],
     "ads": [{"ad_group_id": "11", "type": "RESPONSIVE_SEARCH_AD", "status": "ENABLED",
              "strength": "GOOD", "headlines": [{"text": "Same-day plumbing repair", "pin": null}],
              "descriptions": [{"text": "Licensed and insured.", "pin": null}],
              "approval": "DISAPPROVED", "policy": ["DESTINATION_NOT_WORKING"]}],
     "assets": [{"level": "CAMPAIGN", "owner_id": "1", "type": "SITELINK", "status": "ENABLED"}]}

Everything but the ids is optional. A section left out of the file is None, not an empty list,
so a check can say "not in this file" instead of reporting a clean account it never saw.
"""
import json
import math
import re

from .google_ads_csv import not_a_folder, parse_number

SECTIONS = ("campaigns", "ad_groups", "keywords", "negatives", "ads", "assets")
ALIASES = {  # the words Editor and the UI use, mapped to the Google Ads API's names
    "MAXIMIZE_CLICKS": "TARGET_SPEND",
    "LOW_SEARCH_VOLUME": "RARELY_SERVED",
}


def enum(value):
    """'Maximize conversions' or 'MAXIMIZE_CONVERSIONS' -> 'MAXIMIZE_CONVERSIONS'."""
    if value is None or str(value).strip() in ("", "--"):
        return None
    key = re.sub(r"[^A-Z0-9]+", "_", str(value).strip().upper()).strip("_")
    return ALIASES.get(key, key)


def words(text):
    """Keyword text as plain lowercase words, match-type marks dropped: '+pipe "repair"' -> ['pipe', 'repair']."""
    return re.findall(r"[a-z0-9]+(?:['&.][a-z0-9]+)*", str(text or "").lower())


def _geo(value):
    """Editor spells the option out, in older ('Presence or interest: ...') or newer
    ('People in, regularly in, or who've shown interest in ...') words."""
    key = enum(value)
    if key is None or key in ("PRESENCE", "PRESENCE_OR_INTEREST", "SEARCH_INTEREST"):
        return key
    if "INTEREST" in key and ("PRESENCE" in key or "REGULARLY_IN" in key):
        return "PRESENCE_OR_INTEREST"
    return "PRESENCE" if "PRESENCE" in key or "REGULARLY_IN" in key else key


def _flag(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "enabled", "on", "1")
    return bool(value)


def _int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _amount(value):
    """A daily budget in the account's currency: 50 or "50.00". Editor's decimal mark is settled in editor.py."""
    if isinstance(value, str):
        value = parse_number(value)
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if math.isfinite(amount) and amount > 0 else None


def _reasons(value):
    """Policy topics as a list: ["TRADEMARKS_IN_AD_TEXT"], or one written as a string, or "a; b" from Editor."""
    items = re.split(r"[;\n]", value) if isinstance(value, str) else value or []
    return [enum(p) for p in items if enum(p)]


def _text_assets(items):
    return [{"text": str(i.get("text", "")) if isinstance(i, dict) else str(i),
             "pin": enum(i.get("pin")) if isinstance(i, dict) else None} for i in items or []]


NORMALIZE = {
    "campaigns": lambda r: {
        "id": str(r["id"]), "name": str(r.get("name") or r["id"]), "status": enum(r.get("status")),
        "channel": enum(r.get("channel")), "bidding": enum(r.get("bidding")),
        "enhanced_cpc": _flag(r.get("enhanced_cpc")), "display_network": _flag(r.get("display_network")),
        "geo_target_type": _geo(r.get("geo_target_type")), "budget": _amount(r.get("budget")),
        "budget_limited": _flag(r.get("budget_limited"))},
    "ad_groups": lambda r: {
        "id": str(r["id"]), "campaign_id": str(r["campaign_id"]), "name": str(r.get("name") or r["id"]),
        "status": enum(r.get("status"))},
    "keywords": lambda r: {
        "ad_group_id": str(r["ad_group_id"]), "text": str(r.get("text", "")), "match_type": enum(r.get("match_type")),
        "status": enum(r.get("status")), "serving": enum(r.get("serving")), "quality_score": _int(r.get("quality_score")),
        "expected_ctr": enum(r.get("expected_ctr")), "ad_relevance": enum(r.get("ad_relevance")),
        "landing_page": enum(r.get("landing_page")), "approval": enum(r.get("approval"))},
    "negatives": lambda r: {
        "level": enum(r.get("level")), "owner_id": str(r.get("owner_id", "")), "text": str(r.get("text", "")),
        "match_type": enum(r.get("match_type")), "status": enum(r.get("status"))},
    "ads": lambda r: {
        "ad_group_id": str(r["ad_group_id"]), "type": enum(r.get("type")), "status": enum(r.get("status")),
        "strength": enum(r.get("strength")), "headlines": _text_assets(r.get("headlines")),
        "descriptions": _text_assets(r.get("descriptions")), "name": str(r.get("name") or ""),
        "approval": enum(r.get("approval")), "policy": _reasons(r.get("policy"))},
    "assets": lambda r: {
        "level": enum(r.get("level")), "owner_id": str(r.get("owner_id", "")), "type": enum(r.get("type")),
        "status": enum(r.get("status"))},
}


def is_snapshot(data):
    return isinstance(data, dict) and isinstance(data.get("campaigns"), list)


def snapshot(data, source=""):
    if not is_snapshot(data):
        raise ValueError("This is not an account snapshot: it needs a list of campaigns.")
    out = {"meta": dict(data.get("meta") or {}), "source": source}
    for name in SECTIONS:
        rows = data.get(name)
        out[name] = None if rows is None else [NORMALIZE[name](r) for r in rows]
    return out


def read_json(path):
    """A JSON file's content, or an error that says plainly what is wrong with it."""
    not_a_folder(path)
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except UnicodeDecodeError:
        raise ValueError(f"{path}: this is not valid JSON: it is not saved as UTF-8 text.") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: this is not valid JSON ({e.msg.lower()} at line {e.lineno}, column {e.colno}).") \
            from None


def load_snapshot(path):
    return snapshot(read_json(path), source=str(path))

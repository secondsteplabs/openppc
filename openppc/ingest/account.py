"""Account snapshot: how an account is built (campaigns, ad groups, keywords, negatives, ads,
assets), in one normalized shape whatever file it came from.

Today it reads OpenPPC's own snapshot JSON. A Google Ads Editor whole-account export will be
read into this same shape, so the structure checks never care which file the account came from.

    {"meta": {"account": "Acme Plumbing", "currency": "USD", "captured": "2026-09-28"},
     "campaigns": [{"id": "1", "name": "Acme | Search", "status": "ENABLED", "channel": "SEARCH",
                    "bidding": "MAXIMIZE_CONVERSIONS", "enhanced_cpc": false,
                    "display_network": false, "geo_target_type": "PRESENCE"}],
     "ad_groups": [{"id": "11", "campaign_id": "1", "name": "Plumbing repair", "status": "ENABLED"}],
     "keywords": [{"ad_group_id": "11", "text": "plumbing repair", "match_type": "PHRASE",
                   "status": "ENABLED", "serving": "ELIGIBLE", "quality_score": 7,
                   "expected_ctr": "AVERAGE", "ad_relevance": "AVERAGE", "landing_page": "AVERAGE"}],
     "negatives": [{"level": "CAMPAIGN", "owner_id": "1", "text": "free", "match_type": "BROAD"}],
     "ads": [{"ad_group_id": "11", "type": "RESPONSIVE_SEARCH_AD", "status": "ENABLED",
              "strength": "GOOD", "headlines": [{"text": "Same-day plumbing repair", "pin": null}],
              "descriptions": [{"text": "Licensed and insured.", "pin": null}]}],
     "assets": [{"level": "CAMPAIGN", "owner_id": "1", "type": "SITELINK", "status": "ENABLED"}]}

Everything but the ids is optional. A section left out of the file is None, not an empty list,
so a check can say "not in this file" instead of reporting a clean account it never saw.
"""
import json
import re

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
    """Editor spells the option out ('Presence or interest: People in, regularly in, ...')."""
    key = enum(value)
    if key and key.startswith("PRESENCE_OR_INTEREST"):
        return "PRESENCE_OR_INTEREST"
    return "PRESENCE" if key and key.startswith("PRESENCE") else key


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


def _text_assets(items):
    return [{"text": str(i.get("text", "")) if isinstance(i, dict) else str(i),
             "pin": enum(i.get("pin")) if isinstance(i, dict) else None} for i in items or []]


NORMALIZE = {
    "campaigns": lambda r: {
        "id": str(r["id"]), "name": str(r.get("name") or r["id"]), "status": enum(r.get("status")),
        "channel": enum(r.get("channel")), "bidding": enum(r.get("bidding")),
        "enhanced_cpc": _flag(r.get("enhanced_cpc")), "display_network": _flag(r.get("display_network")),
        "geo_target_type": _geo(r.get("geo_target_type"))},
    "ad_groups": lambda r: {
        "id": str(r["id"]), "campaign_id": str(r["campaign_id"]), "name": str(r.get("name") or r["id"]),
        "status": enum(r.get("status"))},
    "keywords": lambda r: {
        "ad_group_id": str(r["ad_group_id"]), "text": str(r.get("text", "")), "match_type": enum(r.get("match_type")),
        "status": enum(r.get("status")), "serving": enum(r.get("serving")), "quality_score": _int(r.get("quality_score")),
        "expected_ctr": enum(r.get("expected_ctr")), "ad_relevance": enum(r.get("ad_relevance")),
        "landing_page": enum(r.get("landing_page"))},
    "negatives": lambda r: {
        "level": enum(r.get("level")), "owner_id": str(r.get("owner_id", "")), "text": str(r.get("text", "")),
        "match_type": enum(r.get("match_type")), "status": enum(r.get("status"))},
    "ads": lambda r: {
        "ad_group_id": str(r["ad_group_id"]), "type": enum(r.get("type")), "status": enum(r.get("status")),
        "strength": enum(r.get("strength")), "headlines": _text_assets(r.get("headlines")),
        "descriptions": _text_assets(r.get("descriptions"))},
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
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError(f"{path}: this is not valid JSON.") from None


def load_snapshot(path):
    return snapshot(read_json(path), source=str(path))

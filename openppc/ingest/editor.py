"""Read a Google Ads Editor export (Account > Export > Export whole account, as CSV) into an
account snapshot, the same shape openppc/ingest/account.py reads from JSON.

Editor writes one row per thing in the account: a campaign, an ad group, a keyword or a
negative, an ad, or an asset such as a sitelink. Column names are matched without regard to
case, spaces or underscores, so "Campaign Status" and "campaign_status" are the same column.
A plain export has no ids, so names stand in for them: an ad group is known by its
campaign's name and its own.

What a file does not have comes back as None (a section) or None (a field), so the structure
audit says "not in this file" instead of judging something it never saw.

Read-only by construction: this module opens one local file and nothing else.
"""
import itertools
import os

from .account import enum, snapshot
from .google_ads_csv import (HEADER_LINES, LEGACY, decimal_commas, editor_header, lines_of, parse_number, records,
                             squash)

HEADLINES, DESCRIPTIONS = 15, 4
# Editor's words for something that is switched on; whether policy lets it serve is its approval
LIVE = {"ENABLED", "ACTIVE", "ELIGIBLE", "APPROVED", "APPROVED_LIMITED", "LIMITED", "LOW_SEARCH_VOLUME",
        "RARELY_SERVED", "DISAPPROVED"}
RARE = {"LOW_SEARCH_VOLUME", "RARELY_SERVED"}
APPROVALS = {"APPROVED", "APPROVED_LIMITED", "DISAPPROVED", "UNDER_REVIEW", "AREA_OF_INTEREST_ONLY"}
ASSET_COLUMNS = {"SITELINK": ("linktext", "sitelinktext"), "CALLOUT": ("callouttext",),
                 "STRUCTURED_SNIPPET": ("header", "snippetvalues", "structuredsnippetheader")}
GEO_COLUMNS = ("targetingmethod", "locationtargetingmethod", "locationtargeting")
NOT_EDITOR = ("{name} is not a Google Ads Editor export: it has no Campaign Status, Ad Group Status or Criterion "
              "Type column. In Editor: Account > Export > Export whole account, as CSV.")


def is_editor_export(path):
    """Whether the file's header row is Editor's. A file that can't be read at all is not."""
    try:
        with lines_of(path) as (lines, _):
            return editor_header(list(itertools.islice(lines, HEADER_LINES))) is not None
    except (OSError, ValueError, UnicodeError):
        return False


def _status(value):
    s = enum(value)
    return "ENABLED" if s in LIVE else s


def _approval(row):
    """The Approval Status column, or a Status that is an approval (Disapproved, Approved (limited))."""
    status = enum(row.get("status"))
    return enum(row.get("approvalstatus")) or (status if status in APPROVALS else None)


def _first(row, *keys):
    return next((row[k] for k in keys if row.get(k)), "")


def _match(text, criterion):
    """(keyword text, match type) from Editor's Criterion Type, or from the [exact] and "phrase" marks."""
    words = criterion.lower()
    mt = next((m.upper() for m in ("exact", "phrase", "broad") if m in words), None)
    if text.startswith("[") and text.endswith("]"):
        return text[1:-1].strip(), mt or "EXACT"
    if len(text) > 1 and text.startswith('"') and text.endswith('"'):
        return text[1:-1].strip(), mt or "PHRASE"
    return text, mt or "BROAD"


def _pin(prefix, value):
    v = (value or "").strip()
    if v in ("", "-", "--"):
        return None
    return f"{prefix}_{v}" if v.isdigit() else enum(v)


def _kind(row):
    if row.get("keyword"):
        return "negative" if "negative" in row.get("criteriontype", "").lower() else "keyword"
    if row.get("adtype") or any(row.get(f"headline{i}") for i in range(1, HEADLINES + 1)):
        return "ad"
    for asset, columns in ASSET_COLUMNS.items():
        if any(row.get(c) for c in columns):
            return asset
    return "ad_group" if row.get("adgroup") else "campaign"


def _daily(row):
    """Whether the row's budget is a daily one. A campaign total or a shared monthly figure is not."""
    period = _first(row, "budgettype", "budgetperiod").lower()
    return not period or "daily" in period or period == "standard"


def _campaign(c, row, kind):
    """Fill a campaign's settings from the first row that has each one."""
    status = row.get("campaignstatus") or (row.get("status") if kind == "campaign" else "")
    if status and c.get("status") is None:
        c["status"] = status
    channel = enum(row.get("campaigntype"))
    if channel and c.get("channel") is None:
        c["channel"] = "SEARCH" if channel.startswith("SEARCH") else channel
        if channel.startswith("SEARCH") and "DISPLAY" in channel:
            c["display_network"] = True
    networks = row.get("networks", "")
    if networks and c.get("display_network") is None:
        c["display_network"] = "display" in networks.lower()
    budget = row.get("budget") if _daily(row) else ""
    for field, value in (("bidding", row.get("bidstrategytype")), ("enhanced_cpc", row.get("enhancedcpc")),
                         ("geo_target_type", _first(row, *GEO_COLUMNS)), ("budget", budget)):
        if value and c.get(field) is None:
            c[field] = value


def load_editor(path):
    name = os.path.basename(str(path))
    with lines_of(path) as (lines, encoding):
        first = list(itertools.islice(lines, HEADER_LINES))
        found = editor_header(first)
        if not found:
            raise ValueError(NOT_EDITOR.format(name=name))
        idx, delim, head = found
        keys = [squash(c) for c in head]
        present = set(keys)
        camps, groups = {}, {}
        sections = {"keywords": [] if "keyword" in present else None,
                    "negatives": [] if {"keyword", "criteriontype"} <= present else None,
                    "ads": [] if "adtype" in present or any(f"headline{i}" in present
                                                            for i in range(1, HEADLINES + 1)) else None,
                    "assets": [] if any(c in present for cols in ASSET_COLUMNS.values() for c in cols) else None}
        for cells in records(first, idx, lines, delim):
            _add({k: c.strip() for k, c in zip(keys, cells) if k}, camps, groups, sections)
    # A file with no status column at all only holds what Editor was asked to export: take it as live.
    for table, column in ((camps, "campaignstatus"), (groups, "adgroupstatus")):
        for item in table.values():
            if item.get("status") is None and column not in present and "status" not in present:
                item["status"] = "ENABLED"
            item["status"] = _status(item.get("status"))
    if sections["keywords"] is not None and "status" not in present:
        for k in sections["keywords"]:
            k["status"] = "ENABLED"
    european = decimal_commas([c["budget"] for c in camps.values() if c.get("budget")], delim, name)
    for c in camps.values():
        c["budget"] = parse_number(c.get("budget"), european)
    notes = [LEGACY] if encoding in ("cp1252", "latin-1") else []
    data = {"meta": {"notes": notes} if notes else {}, "campaigns": list(camps.values()),
            "ad_groups": list(groups.values()), **sections}
    return snapshot(data, source=str(path))


def _add(row, camps, groups, sections):
    """File one Editor row under its campaign, ad group and section."""
    kind, c_name, g_name = _kind(row), row.get("campaign", ""), row.get("adgroup", "")
    if not c_name:
        if kind in ASSET_COLUMNS and sections["assets"] is not None:
            sections["assets"].append({"level": "ACCOUNT", "owner_id": "", "type": kind,
                                       "status": _status(row.get("status"))})
        return
    _campaign(camps.setdefault(c_name, {"id": c_name, "name": c_name}), row, kind)
    gid = f"{c_name} \u203a {g_name}" if g_name else ""
    if g_name:
        g = groups.setdefault(gid, {"id": gid, "campaign_id": c_name, "name": g_name})
        status = row.get("adgroupstatus") or (row.get("status") if kind == "ad_group" else "")
        if status and g.get("status") is None:
            g["status"] = status
    if kind == "keyword" and g_name and sections["keywords"] is not None:
        text, mt = _match(row["keyword"], row.get("criteriontype", ""))
        raw = enum(row.get("status"))
        sections["keywords"].append({
            "ad_group_id": gid, "text": text, "match_type": mt, "status": _status(row.get("status")),
            "serving": "RARELY_SERVED" if raw in RARE else ("ELIGIBLE" if raw == "ELIGIBLE" else None),
            "quality_score": row.get("qualityscore"), "expected_ctr": row.get("expectedctr"),
            "ad_relevance": row.get("adrelevance"), "landing_page": row.get("landingpageexperience"),
            "approval": _approval(row)})
    elif kind == "negative" and sections["negatives"] is not None:
        text, mt = _match(row["keyword"], row.get("criteriontype", ""))
        campaign_level = "campaign" in row.get("criteriontype", "").lower() or not g_name
        sections["negatives"].append({"level": "CAMPAIGN" if campaign_level else "AD_GROUP",
                                      "owner_id": c_name if campaign_level else gid, "text": text,
                                      "match_type": mt, "status": _status(row.get("status"))})
    elif kind == "ad" and g_name and sections["ads"] is not None:
        sections["ads"].append({
            "ad_group_id": gid, "type": row.get("adtype") or "Responsive search ad",
            "status": _status(row.get("status")), "strength": row.get("adstrength"), "approval": _approval(row),
            "headlines": [{"text": row[f"headline{i}"], "pin": _pin("HEADLINE", row.get(f"headline{i}position"))}
                          for i in range(1, HEADLINES + 1) if row.get(f"headline{i}")],
            "descriptions": [{"text": row[f"description{i}"],
                              "pin": _pin("DESCRIPTION", row.get(f"description{i}position"))}
                             for i in range(1, DESCRIPTIONS + 1) if row.get(f"description{i}")]})
    elif kind in ASSET_COLUMNS and sections["assets"] is not None:
        sections["assets"].append({"level": "AD_GROUP" if g_name else "CAMPAIGN", "owner_id": gid or c_name,
                                   "type": kind, "status": _status(row.get("status"))})

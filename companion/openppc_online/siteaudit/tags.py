"""Which tag a request or a page belongs to, by the patterns in signatures.json."""
import json
import re
from importlib.resources import files
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .page import PageInfo

SIGNATURES: dict[str, Any] = json.loads((files("openppc_online.siteaudit") / "signatures.json").read_text(encoding="utf-8"))
VERSION: str = SIGNATURES["version"]
VENDORS: dict[str, dict[str, Any]] = {v["id"]: v for v in SIGNATURES["vendors"]}
CONSENT: dict[str, dict[str, Any]] = {c["id"]: c for c in SIGNATURES["consent"]}
# ASCII, as PHP's PCRE reads them in the WordPress plugin: \d and \b mean ASCII digits and word edges
_SOURCE = {v["id"]: [re.compile(p, re.ASCII) for p in v["source"]] for v in SIGNATURES["vendors"]}
_HOSTS = {p["host"] for v in SIGNATURES["vendors"] for p in v["load"] + v["hit"] if "host" in p}
BODY_LINES = 50   # events read from one POST body; GA4 sends at most 25 per request
EVENT_CHARS = 100


def add_vendors(vendors: list[dict[str, Any]]) -> None:
    """Rule packs' signatures, known from now on.
    ponytail: process-wide, fine for one CLI run; a long-lived library user would need per-scan tables."""
    for v in vendors:
        VENDORS[v["id"]] = v
        _SOURCE[v["id"]] = [re.compile(p, re.ASCII) for p in v["source"]]
        _HOSTS.update(p["host"] for p in v["load"] + v["hit"] if "host" in p)


def _host_is(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith("." + suffix)


def _matches(p: dict[str, str], url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return (("host" not in p or _host_is(host, p["host"]))
            and parts.path.startswith(p.get("path", ""))
            and p.get("contains", "") in f"{parts.path}?{parts.query}")


def vendor_of(url: str) -> tuple[str, str] | None:
    """(vendor id, "hit" or "load") for a request, or None."""
    for vid, v in VENDORS.items():
        if any(_matches(p, url) for p in v["hit"]):
            return vid, "hit"
    for vid, v in VENDORS.items():
        if any(_matches(p, url) for p in v["load"]):
            return vid, "load"
    return None


def events_of(url: str, body: str = "") -> tuple[str, list[str]] | None:
    """(vendor id, the events a tag hit sends), or None for a request that isn't a hit. GA4 batches
    several events in one POST, a line of the body each."""
    match = vendor_of(url)
    if not match or match[1] != "hit":
        return None
    v = VENDORS[match[0]]
    fixed = next((p["event"] for p in v["hit"] if "event" in p and _matches(p, url)), "")
    if fixed:
        return match[0], [fixed]
    names = []
    for line in [urlsplit(url).query, *body.splitlines()[:BODY_LINES]]:
        query = parse_qs(line)
        name = next((query[k][0] for k in v.get("events", []) if query.get(k, [""])[0]), "")
        if name:
            names.append(name[:EVENT_CHARS])
    return match[0], names


def known_host(host: str) -> bool:
    """A host a known tag uses, whatever the request to it was for (config, sync, a hit)."""
    return any(_host_is(host, h) for h in _HOSTS)


def consent_platform_of(url: str) -> str | None:
    host = (urlsplit(url).hostname or "").lower()
    return next((cid for cid, c in CONSENT.items() if any(_host_is(host, h) for h in c["hosts"])), None)


def in_text(text: str) -> set[str]:
    """Vendors whose code or ID pattern is in the text."""
    return {vid for vid, patterns in _SOURCE.items() if any(p.search(text) for p in patterns)}


def in_source(info: PageInfo) -> set[str]:
    """Vendors whose script or ID is in the page's HTML. Found in the source is not the same as firing."""
    found = {v[0] for v in map(vendor_of, info.scripts) if v}
    return found | in_text(info.inline + "\n".join(info.scripts))


def consent_platforms_in_source(info: PageInfo) -> set[str]:
    return {cid for cid in map(consent_platform_of, info.scripts) if cid}


def consent_mode_ping(url: str) -> bool:
    """A Google hit carrying a denied consent state (gcs=G100, G101 or G110): Consent Mode's
    cookieless ping, which Google designed to be sent before consent."""
    gcs = parse_qs(urlsplit(url).query).get("gcs", [""])[0]
    return len(gcs) == 4 and gcs.startswith("G1") and "0" in gcs[2:]


def consent_mode_on(url: str) -> bool:
    """A Google hit carrying a consent state (gcs or gcd): Consent Mode is set, however it was set.
    A banner's tag manager template sets it without a dataLayer push the page can see."""
    query = parse_qs(urlsplit(url).query)
    return ("gcs" in query or "gcd" in query) and (vendor_of(url) or ("",))[0] in ("ga4", "google-ads")

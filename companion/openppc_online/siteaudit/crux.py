"""Real visitors' Core Web Vitals from the Chrome UX Report (`openppc-online site --crux-key`), with your own
API key. The requests go to Google's API, never to the audited site; the key travels in a header,
so it isn't in any URL, and it is never printed."""
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
KEY_ENV = "OPENPPC_CRUX_KEY"
TIMEOUT = 30
FORM_FACTOR = "PHONE"
# CrUX metric -> (short name, Google's p75 lines for "good" and "poor")
METRICS = {"largest_contentful_paint": ("lcp", 2500, 4000),
           "interaction_to_next_paint": ("inp", 200, 500),
           "cumulative_layout_shift": ("cls", 0.1, 0.25)}


@dataclass
class FieldData:
    target: str                                       # the origin, or the page URL
    origin: bool                                      # a whole-site record, not one page's
    p75: dict[str, float] = field(default_factory=dict)
    period: str = ""                                  # "2026-09-07 to 2026-10-04"
    error: str = ""                                   # why there is no record


def key_from(flag: str | None) -> str:
    """--crux-key KEY, or --crux-key alone to read the key from OPENPPC_CRUX_KEY (out of shell history)."""
    key = flag or os.environ.get(KEY_ENV, "")
    if not key.strip():
        raise ValueError(f"--crux-key needs a key: pass it, or set {KEY_ENV}")
    return key.strip()


def _date(d: dict[str, int]) -> str:
    return f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}"


def query(target: str, key: str, origin: bool, opener: Callable[..., Any] = urllib.request.urlopen) -> FieldData:
    out = FieldData(target, origin)
    body = json.dumps({"origin" if origin else "url": target, "formFactor": FORM_FACTOR}).encode()
    req = urllib.request.Request(ENDPOINT, body, {"Content-Type": "application/json", "X-Goog-Api-Key": key})
    try:
        with opener(req, timeout=TIMEOUT) as resp:
            record = json.loads(resp.read())["record"]
    except urllib.error.HTTPError as e:
        out.error = ("not enough real-visitor data in Chrome's report" if e.code == 404 else
                     "the API key was refused" if e.code in (400, 403) else f"the API answered {e.code}")
        return out
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        out.error = f"couldn't reach the API: {e}".replace(key, "<key>")
        return out
    for name, (short, _, _) in METRICS.items():
        p75 = record.get("metrics", {}).get(name, {}).get("percentiles", {}).get("p75")
        if p75 is not None:
            out.p75[short] = float(p75)
    period = record.get("collectionPeriod", {})
    if period.get("firstDate") and period.get("lastDate"):
        out.period = f"{_date(period['firstDate'])} to {_date(period['lastDate'])}"
    return out


def field_data(origin: str, home: str, key: str) -> list[FieldData]:
    """The whole site's record, then the home page's."""
    return [query(origin, key, True), query(home, key, False)]

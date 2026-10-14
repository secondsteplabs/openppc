"""Real visitors' Web Vitals from the Chrome UX Report: from its API with your own key (`openppc-online site --crux`),
or as PageSpeed Insights passes it on (`--psi`). The requests go to Google's API, never to the audited site, through
the same guard as every other connection; a key travels in a header, so it isn't in any URL, and it is never printed.
"""
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from .net import Guard, fetch

ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
KEY_ENV = "OPENPPC_CRUX_KEY"
API_KEY = re.compile(r"[A-Za-z0-9_-]+")  # a Google API key; anything else could end up quoted in an error
TIMEOUT = 30.0
MAX_BYTES = 1_000_000
FORM_FACTOR = "PHONE"
FORM_FACTORS = {"PHONE": "phone", "DESKTOP": "desktop"}
# CrUX metric -> (short name, Google's p75 lines for "good" and "poor"): the Core Web Vitals, which findings and the
# assessment read, then the two PSI shows beside them
METRICS = {"largest_contentful_paint": ("lcp", 2500, 4000),
           "interaction_to_next_paint": ("inp", 200, 500),
           "cumulative_layout_shift": ("cls", 0.1, 0.25)}
MORE = {"first_contentful_paint": ("fcp", 1800, 3000),
        "experimental_time_to_first_byte": ("ttfb", 800, 1800)}
ALL_METRICS = {**METRICS, **MORE}
# PageSpeed Insights' names for the same metrics; its CLS percentile is the score times 100
PSI_METRICS = {"LARGEST_CONTENTFUL_PAINT_MS": "lcp", "INTERACTION_TO_NEXT_PAINT": "inp",
               "CUMULATIVE_LAYOUT_SHIFT_SCORE": "cls", "FIRST_CONTENTFUL_PAINT_MS": "fcp",
               "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "ttfb"}
PSI_VERDICT = {"FAST": "passed", "AVERAGE": "failed", "SLOW": "failed"}
NO_DATA = "not enough real-visitor data in Chrome's report"


@dataclass
class FieldData:
    target: str                                       # the origin, or the page URL
    origin: bool                                      # a whole-site record, not one page's
    p75: dict[str, float] = field(default_factory=dict)
    period: str = ""                                  # "2026-09-07 to 2026-10-04"
    error: str = ""                                   # why there is no record
    device: str = "phone"                             # phone or desktop
    shares: dict[str, list[float]] = field(default_factory=dict)  # metric -> good, needs improvement, poor
    verdict: str = ""                                 # the Core Web Vitals assessment: passed, failed, or none
    source: str = "the CrUX API"


def key_from(flag: str | None) -> str:
    """--crux-key KEY, or OPENPPC_CRUX_KEY (out of shell history) when only --crux is given."""
    key = (flag or os.environ.get(KEY_ENV, "")).strip()
    if not key:
        raise ValueError(f"--crux needs a key: pass --crux-key KEY, or set {KEY_ENV}")
    if not API_KEY.fullmatch(key):
        raise ValueError("the CrUX key has characters a Google API key doesn't (letters, digits, - and _ only)")
    return key


def assess(p75: dict[str, float]) -> str:
    """PSI's rule: passed when LCP, INP and CLS are good at p75 (the line itself is good), LCP and CLS alone when
    INP has no data; no assessment without LCP or CLS."""
    if "lcp" not in p75 or "cls" not in p75:
        return ""
    good = all(p75[short] <= line for short, line, _ in METRICS.values() if short in p75)
    return "passed" if good else "failed"


def _date(d: dict[str, int]) -> str:
    return f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}"


def _shares(bins: Any) -> list[float] | None:
    values = [b.get("density") if isinstance(b, dict) else None for b in bins or []]
    if len(values) == 3 and all(isinstance(v, (int, float)) for v in values):
        return [float(v) for v in values]  # type: ignore[arg-type]
    return None


def query(target: str, key: str, origin: bool, guard: Guard, form_factor: str = FORM_FACTOR) -> FieldData:
    out = FieldData(target, origin, device=FORM_FACTORS[form_factor])
    body = json.dumps({"origin" if origin else "url": target, "formFactor": form_factor}).encode()
    resp = fetch(ENDPOINT, guard, "POST", MAX_BYTES, follow=False, body=body, seconds=TIMEOUT, timeout=TIMEOUT,
                 headers={"Content-Type": "application/json", "X-Goog-Api-Key": key})
    if resp.status == 0:
        out.error = f"couldn't reach the API: {resp.error}".replace(key, "<key>")
        return out
    if resp.status != 200:
        out.error = (NO_DATA if resp.status == 404 else
                     "the API key was refused" if resp.status in (400, 403) else f"the API answered {resp.status}")
        return out
    try:
        record = json.loads(resp.body)["record"]
        for name, (short, _, _) in ALL_METRICS.items():
            metric = record.get("metrics", {}).get(name, {})
            p75 = metric.get("percentiles", {}).get("p75")
            if p75 is not None:
                out.p75[short] = float(p75)
            shares = _shares(metric.get("histogram"))
            if shares:
                out.shares[short] = shares
        period = record.get("collectionPeriod", {})
        if period.get("firstDate") and period.get("lastDate"):
            out.period = f"{_date(period['firstDate'])} to {_date(period['lastDate'])}"
    except (ValueError, KeyError, TypeError, AttributeError):
        return FieldData(target, origin, error="the API's answer couldn't be read", device=out.device)
    out.verdict = assess(out.p75)
    return out


def field_data(origin: str, home: str, key: str, guard: Guard) -> list[FieldData]:
    """For phones, then desktops: the page's record, then the whole site's."""
    return [query(target, key, whole, guard, ff) for ff in FORM_FACTORS for target, whole in ((home, False),
                                                                                             (origin, True))]


def from_psi(experience: Any, target: str, origin: bool, device: str) -> FieldData:
    """PageSpeed Insights' loadingExperience (the page) or originLoadingExperience (the site)."""
    out = FieldData(target, origin, device=device, source="PageSpeed Insights")
    exp: dict[str, Any] = experience if isinstance(experience, dict) else {}
    if not origin and exp.get("origin_fallback"):
        out.error = "too few real visitors to this page, so PageSpeed Insights shows the whole site's"
        return out
    metrics: dict[str, Any] = exp["metrics"] if isinstance(exp.get("metrics"), dict) else {}
    for name, short in PSI_METRICS.items():
        m = metrics.get(name)
        if not isinstance(m, dict) or not isinstance(m.get("percentile"), (int, float)):
            continue
        out.p75[short] = m["percentile"] / 100 if short == "cls" else float(m["percentile"])
        proportions = [{"density": d.get("proportion")} for d in m.get("distributions") or [] if isinstance(d, dict)]
        shares = _shares(proportions)
        if shares:
            out.shares[short] = shares
    if not out.p75:
        out.error = NO_DATA
        return out
    out.verdict = PSI_VERDICT.get(str(exp.get("overall_category") or ""), "")
    return out

"""tags.py against the cases the browser extension's matcher is tested on too (tag_cases.json)."""
import json
import re
from pathlib import Path

import pytest
from openppc_online.siteaudit import tags

CASES = json.loads((Path(__file__).parent / "tag_cases.json").read_text(encoding="utf-8"))


def _tuples(answer):
    if isinstance(answer, list):
        return tuple(answer)
    return answer


@pytest.mark.parametrize(("text", "found"), CASES["in_text"])
def test_in_text(text, found):
    assert sorted(tags.in_text(text)) == found


@pytest.mark.parametrize(("url", "found"), CASES["vendor_of"])
def test_vendor_of(url, found):
    assert tags.vendor_of(url) == _tuples(found)


@pytest.mark.parametrize(("url", "found"), CASES["events_of"])
def test_events_of(url, found):
    assert tags.events_of(url) == _tuples(found)


@pytest.mark.parametrize(("host", "known"), CASES["known_host"])
def test_known_host(host, known):
    assert tags.known_host(host) is known


def _cdp_glob(pattern):
    """Chrome's Fetch.enable urlPattern as a regex: * any run, ? one character, a backslash escapes."""
    out, chars = [], iter(pattern)
    for ch in chars:
        out.append(".*" if ch == "*" else "." if ch == "?" else re.escape(next(chars) if ch == "\\" else ch))
    return re.compile("".join(out) + r"\Z", re.S)


HIT_GLOBS = [_cdp_glob(p) for p in tags.hit_patterns()]
# what a page loads that a speed load must leave alone: tag scripts included, since their cost is what's measured
ORDINARY = ["https://shop.test/", "https://shop.test/app.css", "https://shop.test/img/hero.jpg",
            "https://shop.test/static/collect.js", "https://shop.test/collections/spring",
            "https://fonts.gstatic.com/s/inter/v13/a.woff2", "https://www.googletagmanager.com/gtag/js?id=G-ABC123",
            "https://www.googletagmanager.com/gtm.js?id=GTM-ABC", "https://connect.facebook.net/en_US/fbevents.js",
            "https://snap.licdn.com/li.lms-analytics/insight.min.js", "https://bat.bing.com/bat.js",
            "https://www.clarity.ms/tag/abc", "https://static.ads-twitter.com/uwt.js",
            "https://analytics.tiktok.com/i18n/pixel/events.js", "https://www.google.com/images/branding/logo.png",
            "https://assets.adobedtm.com/abc/launch-1.min.js", "https://cdn.segment.com/analytics.js/v1/x/a.min.js"]


@pytest.mark.parametrize(("url", "found"), [c for c in CASES["vendor_of"] if c[1] and c[1][1] == "hit"])
def test_every_tag_hit_is_caught_during_speed_loads(url, found):
    assert any(g.match(url) for g in HIT_GLOBS) and tags.is_hit(url)


@pytest.mark.parametrize("url", ORDINARY)
def test_ordinary_files_and_tag_scripts_load_untouched(url):
    assert not any(g.match(url) for g in HIT_GLOBS) and not tags.is_hit(url)


@pytest.mark.parametrize(("url", "platform"), CASES["consent_platform_of"])
def test_consent_platform_of(url, platform):
    assert tags.consent_platform_of(url) == platform


@pytest.mark.parametrize(("url", "ping"), CASES["consent_mode_ping"])
def test_consent_mode_ping(url, ping):
    assert tags.consent_mode_ping(url) is ping


@pytest.mark.parametrize(("url", "on"), CASES["consent_mode_on"])
def test_consent_mode_on(url, on):
    assert tags.consent_mode_on(url) is on

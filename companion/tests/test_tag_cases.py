"""tags.py against the cases the browser extension's matcher is tested on too (tag_cases.json)."""
import json
from pathlib import Path

import pytest
from openppc_online.siteaudit import tags

CASES = json.loads((Path(__file__).parent / "tag_cases.json").read_text(encoding="utf-8"))


def _tuples(answer):
    if isinstance(answer, list):
        return tuple(answer)
    return answer


@pytest.mark.parametrize(("url", "found"), CASES["vendor_of"])
def test_vendor_of(url, found):
    assert tags.vendor_of(url) == _tuples(found)


@pytest.mark.parametrize(("url", "found"), CASES["events_of"])
def test_events_of(url, found):
    assert tags.events_of(url) == _tuples(found)


@pytest.mark.parametrize(("host", "known"), CASES["known_host"])
def test_known_host(host, known):
    assert tags.known_host(host) is known


@pytest.mark.parametrize(("url", "platform"), CASES["consent_platform_of"])
def test_consent_platform_of(url, platform):
    assert tags.consent_platform_of(url) == platform


@pytest.mark.parametrize(("url", "ping"), CASES["consent_mode_ping"])
def test_consent_mode_ping(url, ping):
    assert tags.consent_mode_ping(url) is ping


@pytest.mark.parametrize(("url", "on"), CASES["consent_mode_on"])
def test_consent_mode_on(url, on):
    assert tags.consent_mode_on(url) is on

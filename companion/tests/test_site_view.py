"""local/site.js and local/fetch.js, the Site and Download views: they stand on app.js's helpers without changing
the hosted app, so a rename there must fail here rather than on someone's screen."""
import re

import pytest

from openppc_online import app

VIEWS = ("site.js", "fetch.js")
APP_JS = (app.CLONE_WEB / "app.js").read_text(encoding="utf-8")


def _view(name):
    return (app.LOCAL / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", VIEWS)
def test_every_app_js_helper_the_view_uses_is_still_there(name):
    used = re.search(r"const APP = \{ ([\w, ]+) \};", _view(name))
    assert used, f"{name} lost its APP line"
    declared = set(re.findall(r"^(?:async )?function (\w+)\(", APP_JS, re.M))
    declared |= set(re.findall(r"^(?:const|let) (\w+) =", APP_JS, re.M))
    missing = {helper.strip() for helper in used[1].split(",")} - declared
    assert not missing, f"web/app.js no longer declares {missing} at the top; update local/{name}"


@pytest.mark.parametrize("name", VIEWS)
def test_the_view_writes_no_markup_of_its_own(name):
    # text goes in through h(), the report through app.js's sanitized reportNode
    text = _view(name)
    assert "innerHTML" not in text and "insertAdjacentHTML" not in text and "outerHTML" not in text


def test_the_hosted_app_is_unchanged_by_the_views():
    index = (app.CLONE_WEB / "index.html").read_text(encoding="utf-8")
    for name in (*VIEWS, "local.js", "site.css"):
        assert name not in index
        assert not (app.CLONE_WEB / name).exists()


def test_the_download_view_asks_for_the_credentials_the_command_reads():
    text = _view("fetch.js")
    for platform, names in app.fetch_command.CREDENTIALS.items():
        block = re.search(rf"\n    {platform}: \{{(.*?)\n    \}},", text, re.S)
        assert block, f"fetch.js lost its {platform} entry"
        assert set(re.findall(r"\['([A-Z_]+)'", block[1])) == set(names)

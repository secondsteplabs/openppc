"""local/site.js, the Site view: it stands on app.js's helpers without changing the hosted app, so a rename there
must fail here rather than on someone's screen."""
import re

from openppc_online import app

SITE_JS = (app.LOCAL / "site.js").read_text(encoding="utf-8")
APP_JS = (app.CLONE_WEB / "app.js").read_text(encoding="utf-8")


def test_every_app_js_helper_the_view_uses_is_still_there():
    used = re.search(r"const APP = \{ ([\w, ]+) \};", SITE_JS)
    assert used, "site.js lost its APP line"
    declared = set(re.findall(r"^(?:async )?function (\w+)\(", APP_JS, re.M))
    declared |= set(re.findall(r"^(?:const|let) (\w+) =", APP_JS, re.M))
    missing = {name.strip() for name in used[1].split(",")} - declared
    assert not missing, f"web/app.js no longer declares {missing} at the top; update local/site.js"


def test_the_view_writes_no_markup_of_its_own():
    # text goes in through h(), the report through app.js's sanitized reportNode
    assert "innerHTML" not in SITE_JS and "insertAdjacentHTML" not in SITE_JS and "outerHTML" not in SITE_JS


def test_the_hosted_app_is_unchanged_by_the_view():
    for name in ("site.js", "site.css"):
        assert name not in (app.CLONE_WEB / "index.html").read_text(encoding="utf-8")
        assert not (app.CLONE_WEB / name).exists()

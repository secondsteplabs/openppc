"""What testing the app end to end turned up (checklist 14a), pinned so it cannot come back.

A wrong file gets a plain reason, in the app's file chip and on the command line, instead of a raw
error: an unrelated JSON, a file that is not valid JSON, and the .xlsx, .xls, .pdf and empty files people
pick by mistake (Google Ads offers .xlsx and .pdf in the same Download menu as .csv).
"""
import json
import re

import pytest

from openppc import webapi
from openppc.checkfacts import facts_for_paths
from openppc.ingest import load_report

NOT_AN_ACCOUNT = "this JSON is not an account file OpenPPC reads"


def _inspect(path):
    return json.loads(webapi.inspect_file(str(path)))


@pytest.mark.parametrize("content, says", [
    ('{"theme": "dark", "items": [1, 2, 3]}', NOT_AN_ACCOUNT),   # used to show a bare 'cs'
    ("[1, 2, 3]", NOT_AN_ACCOUNT),
    ('{"current": {"spend": 10}, "prior": {}}', NOT_AN_ACCOUNT),
    ("{not json", "this is not valid JSON"),
])
def test_a_json_that_is_not_an_account_file_says_so(tmp_path, content, says):
    path = tmp_path / "settings.json"
    path.write_text(content)
    info = _inspect(path)
    assert not info["ok"] and info["error"].startswith(says), info["error"]  # the chip shows the name above it
    with pytest.raises(ValueError, match=re.escape(f"settings.json: {says}")):  # the command line names the file
        facts_for_paths([path])


@pytest.mark.parametrize("name, data, says", [
    ("report.xlsx", b"PK\x03\x04" + bytes(200), "this is an Excel workbook, not a .csv"),
    ("report.xls", b"\xd0\xcf\x11\xe0" + bytes(200), "this is an old Excel workbook (.xls)"),
    ("report.zip", b"PK\x03\x04" + bytes(200), "this is a zip file"),
    ("report.pdf", b"%PDF-1.7\n%%EOF\n", "this is a PDF"),
    ("empty.csv", b"", "the file is empty"),
    ("blank.csv", "\n\n".encode("utf-16"), "the file is empty"),
])
def test_files_people_pick_instead_of_the_csv_are_named(tmp_path, name, data, says):
    path = tmp_path / name
    path.write_bytes(data)
    info = _inspect(path)
    assert not info["ok"] and info["error"].startswith(says), info["error"]
    with pytest.raises(ValueError, match=re.escape(f"{name}: {says}")):
        load_report(str(path))


def test_the_chip_does_not_repeat_the_file_name(tmp_path):
    path = tmp_path / "leads.csv"
    path.write_text("Date,Email,Keyword,Company\n2026-07-01,jo@example.com,drain repair,Example Co\n")
    info = _inspect(path)
    assert info["error"].startswith("no header row with Clicks and Cost columns"), info["error"]


def test_real_exports_still_read():
    for sample in ("examples/search_terms_acme.csv", "examples/keywords_acme.csv",
                   "examples/account_structure_acme.json", "examples/account_acme.json"):
        assert _inspect(sample)["ok"], sample

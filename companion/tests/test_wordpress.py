"""The WordPress plugin (companion/wordpress/openppc-site-check/): the crawler's signatures, only what ships, and
its PHP tests, run here so `pytest companion` covers them."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

COMPANION = Path(__file__).parents[1]
PLUGIN = COMPANION / "wordpress" / "openppc-site-check"
SHIPPED = {"openppc-site-check.php", "readme.txt", "signatures.json"}


def test_the_plugin_knows_the_crawlers_tags():
    crawler = COMPANION / "openppc_online" / "siteaudit" / "signatures.json"
    assert (PLUGIN / "signatures.json").read_bytes() == crawler.read_bytes(), \
        "copy openppc_online/siteaudit/signatures.json to wordpress/openppc-site-check/signatures.json"


def test_the_plugin_folder_is_what_ships():
    assert {p.name for p in PLUGIN.iterdir()} == SHIPPED


def test_the_plugin_and_its_readme_agree():
    head = (PLUGIN / "openppc-site-check.php").read_text(encoding="utf-8")
    readme = (PLUGIN / "readme.txt").read_text(encoding="utf-8")
    for header, field in (("Version", "Stable tag"), ("Requires at least", "Requires at least"),
                          ("Requires PHP", "Requires PHP"), ("License", "License")):
        ours = re.search(rf"^ \* {header}:\s*(.+)$", head, re.M)
        theirs = re.search(rf"^{field}:\s*(.+)$", readme, re.M)
        assert ours and theirs and ours[1].strip() == theirs[1].strip(), header


def test_the_plugins_php_tests_pass():
    php = shutil.which("php")
    if php is None:
        if os.environ.get("CI"):
            pytest.fail("CI needs PHP 7.4 or later for these tests")
        pytest.skip("needs PHP 7.4 or later")
    run = subprocess.run([php, str(Path(__file__).parent / "php" / "site_check_test.php")],
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert run.returncode == 0 and run.stdout.strip() == "all passed", run.stdout + run.stderr

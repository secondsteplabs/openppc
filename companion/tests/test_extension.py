"""The Tag Inspector browser extension (companion/extension/): the same signatures as the crawler, and its
Node tests, run here so `pytest companion` covers them."""
import shutil
import subprocess
from pathlib import Path

import pytest

COMPANION = Path(__file__).parents[1]
EXTENSION = COMPANION / "extension"


def test_the_extension_knows_the_crawlers_tags():
    crawler = COMPANION / "openppc_online" / "siteaudit" / "signatures.json"
    assert (EXTENSION / "signatures.json").read_bytes() == crawler.read_bytes(), \
        "copy openppc_online/siteaudit/signatures.json to extension/signatures.json"


def test_the_extensions_node_tests_pass():
    node = shutil.which("node")
    if node is None:
        pytest.skip("needs Node.js 22 or later")
    tests = sorted(str(p) for p in (Path(__file__).parent / "js").glob("*.test.mjs"))
    assert tests
    run = subprocess.run([node, "--test", *tests], capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr

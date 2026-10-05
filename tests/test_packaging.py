"""What goes to PyPI is an explicit allowlist, never whatever happens to sit in the folder."""
from pathlib import Path

import pytest

tomllib = pytest.importorskip("tomllib")  # Python 3.11+; CI runs this on 3.12 and later

ROOT = Path(__file__).resolve().parent.parent


def test_the_package_archives_are_allowlists():
    hatch = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]["build"]["targets"]
    assert hatch["wheel"]["packages"] == ["openppc"]
    include = hatch["sdist"]["include"]
    assert "/openppc" in include
    for private_or_heavy in ("/site", "/web", "/brand", "/exports", "/.code-review-graph", "/.github"):
        assert private_or_heavy not in include, private_or_heavy

"""The logo files are complete, need no font, and every copy of them matches brand/."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "brand"


def test_every_file_the_brand_readme_lists_exists():
    readme = (BRAND / "README.md").read_text()
    names = re.findall(r"`([\w./-]+\.(?:svg|png|ico))`", readme)
    assert len(names) >= 14
    for name in names:
        found = list(BRAND.rglob(name))
        assert found, name


def test_the_logo_files_need_no_font_and_load_nothing():
    for svg in BRAND.glob("*.svg"):
        text = svg.read_text()
        assert "<text" not in text and "<image" not in text and "href=" not in text, svg.name
        assert 'aria-label="OpenPPC"' in text and "<title>OpenPPC</title>" in text, svg.name


def test_the_app_favicon_is_the_brand_icon():
    assert (ROOT / "web" / "favicon.svg").read_text() == (BRAND / "openppc-icon.svg").read_text()
    assert '<link rel="icon" href="favicon.svg" type="image/svg+xml">' in (ROOT / "web" / "index.html").read_text()

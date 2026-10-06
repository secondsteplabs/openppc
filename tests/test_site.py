"""openppc.si builds, every internal link resolves, and the pages carry what they promise."""
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _site():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "tools" / "build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_site_builds_with_no_broken_links(tmp_path):
    report = _site().build(tmp_path / "dist")
    assert report["broken"] == []
    assert {"/", "/docs/", "/docs/install/", "/app/"} <= set(report["pages"])
    for page in ("index.html", "docs/index.html", "docs/install/index.html", "404.html", "app/index.html"):
        assert (tmp_path / "dist" / page).exists(), page


def test_the_home_page_has_the_video_the_app_and_github(tmp_path):
    _site().build(tmp_path / "dist")
    home = (tmp_path / "dist" / "index.html").read_text()
    assert 'src="/media/openppc-demo.mp4"' in home and 'href="/app/"' in home
    assert "https://github.com/secondsteplabs/openppc" in home
    assert '<link rel="canonical" href="https://openppc.si/">' in home
    assert "Works inside Claude, Cursor and ChatGPT" in home and "cursor://anysphere.cursor-deeplink/mcp/install?name=openppc" in home
    assert "coming soon" in home and '"openppc[mcp]"' in home and "git+https://" not in home
    faq = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', home)]
    assert [b["@type"] for b in faq] == ["SoftwareApplication", "FAQPage"] and len(faq[1]["mainEntity"]) == 7


def test_the_install_guide_shows_every_step(tmp_path):
    _site().build(tmp_path / "dist")
    guide = (tmp_path / "dist" / "docs" / "install" / "index.html").read_text()
    for anchor in ("browser", "export", "audit", "check", "pdf", "computer", "ai", "claude", "cursor", "chatgpt",
                   "connector", "self-host", "trouble"):
        assert f'id="{anchor}"' in guide, anchor
    assert len(re.findall(r'<img src="/img/docs/', guide)) == 7


def test_pages_load_nothing_from_other_sites(tmp_path):
    _site().build(tmp_path / "dist")
    for page in ("index.html", "docs/index.html", "docs/install/index.html", "404.html"):
        text = (tmp_path / "dist" / page).read_text()
        assert not re.findall(r'(?:src|href)="https?://(?!github\.com|getsecondstep\.com|docs\.astral\.sh)[^"]*\.(?:js|css|woff2?)', text)
        assert "default-src 'self'" in text


def test_the_site_serves_the_logo_icons_and_share_image(tmp_path):
    site = _site()
    site.build(tmp_path / "dist")
    for src, dest in site.BRAND.items():
        assert (tmp_path / "dist" / dest).read_bytes() == (ROOT / "brand" / src).read_bytes(), dest
    home = (tmp_path / "dist" / "index.html").read_text()
    assert '<img src="/logo.svg" alt="OpenPPC"' in home and 'href="/apple-touch-icon.png"' in home
    assert '<meta property="og:image" content="https://openppc.si/og-image.png">' in home


def test_analytics_runs_on_the_website_and_never_in_the_app(tmp_path):
    _site().build(tmp_path / "dist")
    dist = tmp_path / "dist"
    tag = (dist / "analytics.js").read_text()
    assert "GTM-MKK8JT53" in tag and tag.index("'consent', 'default'") < tag.index("gtm.js?id=")
    for page in ("index.html", "docs/index.html", "docs/install/index.html", "404.html"):
        assert '<script src="/analytics.js" async></script>' in (dist / page).read_text(), page
    app = (dist / "app" / "index.html").read_text()
    assert "analytics.js" not in app and "googletagmanager" not in app
    assert "connect-src https://cdn.jsdelivr.net;" in app   # the app may fetch the Python runtime and nothing else


def test_the_app_names_its_files_by_content(tmp_path):
    # Cloudflare lets browsers keep scripts for hours and the page is never cached: a new page must name new files
    _site().build(tmp_path / "dist")
    app = tmp_path / "dist" / "app"
    index, appjs, worker = ((app / n).read_text() for n in ("index.html", "app.js", "engine-worker.js"))
    for name in ("style.css", "engine.js", "app.js"):
        assert re.search(rf'"{re.escape(name)}\?v=[0-9a-f]{{12}}"', index), name
    assert re.search(r"new Worker\('engine-worker\.js\?v=[0-9a-f]{12}'", appjs)
    assert re.search(r"import\('\./engine\.js\?v=[0-9a-f]{12}'\)", worker)

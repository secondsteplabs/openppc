"""openppc.si builds, every internal link resolves, and the pages carry what they promise."""
import importlib.util
import json
from html import unescape
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
    assert 'src="/media/openppc-demo.mp4?v=' in home and 'href="/app/"' in home
    assert "https://github.com/secondsteplabs/openppc" in home
    assert '<link rel="canonical" href="https://openppc.si/">' in home
    assert "Works inside Claude, Cursor and ChatGPT" in home and "cursor://anysphere.cursor-deeplink/mcp/install?name=openppc" in home
    assert "coming soon" in home and '"openppc[mcp]"' in home and "git+https://" not in home
    faq = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', home)]
    assert [b["@type"] for b in faq] == ["Organization", "WebSite", "SoftwareApplication", "FAQPage"] and len(faq[-1]["mainEntity"]) == 7


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
        assert re.search(r'<script src="/analytics\.js\?v=[0-9a-f]{12}" async></script>', (dist / page).read_text()), page
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


def test_pages_name_their_images_and_video_by_content(tmp_path):
    # Cloudflare keeps media for days: a new demo video must get a new address, or visitors keep the old one
    import hashlib
    _site().build(tmp_path)
    home = (tmp_path / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|poster)="(/(?:img|media)/[^"?]+)\?v=([0-9a-f]{12})"', home)
    assert {r for r, _ in refs} >= {"/media/openppc-demo.mp4", "/media/openppc-demo-poster.jpg"}
    for ref, tag in refs:
        assert hashlib.sha256((tmp_path / ref.lstrip("/")).read_bytes()).hexdigest()[:12] == tag
    assert not re.search(r'(?:src|poster)="/(?:img|media)/[^"?]+"', home)  # none left unversioned


def test_pages_name_their_stylesheet_and_scripts_by_content(tmp_path):
    # browsers keep CSS and JS for hours: a changed stylesheet must get a new address, or pages render with the old one
    import hashlib
    _site().build(tmp_path)
    for page in (tmp_path / "index.html", tmp_path / "articles" / "index.html"):
        html = page.read_text(encoding="utf-8")
        for ref, attr in (("/site.css", "href"), ("/analytics.js", "src")):
            tag = hashlib.sha256((tmp_path / ref.lstrip("/")).read_bytes()).hexdigest()[:12]
            assert f'{attr}="{ref}?v={tag}"' in html, (page, ref)
            assert f'{attr}="{ref}"' not in html


def test_pages_use_no_inline_styles(tmp_path):
    # the website's CSP is style-src 'self': a style="" attribute is silently dropped, so a chart placed with one
    # breaks (the app has its own CSP)
    _site().build(tmp_path)
    pages = [p for p in tmp_path.rglob("*.html") if "app" not in p.relative_to(tmp_path).parts]
    assert len(pages) >= 10
    for page in pages:
        assert 'style="' not in page.read_text(encoding="utf-8"), page


def test_articles_are_listed_and_marked_up_for_search_and_answer_engines(tmp_path):
    report = _site().build(tmp_path / "dist")
    articles = [p for p in report["pages"] if p.startswith("/articles/") and p != "/articles/"]
    assert len(articles) >= 5 and "/articles/" in report["pages"]
    index = (tmp_path / "dist" / "articles" / "index.html").read_text(encoding="utf-8")
    llms = (tmp_path / "dist" / "llms.txt").read_text(encoding="utf-8")
    sitemap = (tmp_path / "dist" / "sitemap.xml").read_text(encoding="utf-8")
    for url in articles:
        html = (tmp_path / "dist" / url.strip("/") / "index.html").read_text(encoding="utf-8")
        blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
        kinds = {b["@type"] for b in blocks}
        assert {"Article", "FAQPage"} <= kinds, url
        article = next(b for b in blocks if b["@type"] == "Article")
        assert article["headline"] in html and article["author"]["name"] == "Shivendra Rawat"
        assert f'href="{url}"' in index and f"https://openppc.si{url}" in llms and f"https://openppc.si{url}" in sitemap
        assert "—" not in html and "–" not in html  # house style: no em or en dashes


def test_pages_have_one_h1_a_self_canonical_and_search_sized_snippets(tmp_path):
    # the basics a search engine reads first: one main heading, the page's own canonical URL, and a title and
    # description that fit the result snippet
    report = _site().build(tmp_path)
    for url in report["pages"]:
        html = (tmp_path / url.strip("/") / "index.html").read_text(encoding="utf-8") if url != "/" else (tmp_path / "index.html").read_text(encoding="utf-8")
        assert len(re.findall(r"<h1[\s>]", html)) == 1, url
        assert re.findall(r'<link rel="canonical" href="([^"]+)"', html) == [f"https://openppc.si{url}"], url
        if url != "/app/":
            title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
            desc = unescape(re.search(r'<meta name="description" content="([^"]*)"', html).group(1))
            assert len(title) <= 62 and 120 <= len(desc) <= 160, (url, len(title), len(desc))


def test_articles_and_docs_carry_breadcrumbs_and_articles_an_author(tmp_path):
    report = _site().build(tmp_path)
    for url in [u for u in report["pages"] if u.startswith(("/articles/", "/docs/"))]:
        html = (tmp_path / url.strip("/") / "index.html").read_text(encoding="utf-8")
        blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
        trail = next(b for b in blocks if b["@type"] == "BreadcrumbList")["itemListElement"]
        assert trail[0]["item"] == "https://openppc.si/" and trail[-1]["item"] == f"https://openppc.si{url}", url
        assert '<nav class="crumbs" aria-label="Breadcrumb">' in html, url
        if url not in ("/articles/", "/docs/"):
            assert len(trail) == 3, url
        article = next((b for b in blocks if b["@type"] == "Article"), None)
        if article:
            assert article["author"]["sameAs"] and 'class="author-bio"' in html, url
    home = (tmp_path / "index.html").read_text(encoding="utf-8")
    kinds = {json.loads(b)["@type"] for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', home, re.S)}
    assert {"Organization", "WebSite", "SoftwareApplication"} <= kinds


def test_pages_show_webp_screenshots(tmp_path):
    # the JPGs stay in the repo for the README; pages load the smaller WebP copies
    _site().build(tmp_path)
    for page in tmp_path.rglob("*.html"):
        assert not re.search(r'src="/img/[^"]+\.jpg', page.read_text(encoding="utf-8")), page

"""Build openppc.si into dist/: the site pages, their files, and the web app at /app/.

    python tools/build_site.py
    python3 -m http.server 8766 --directory dist

Pages are HTML fragments in site/pages/ with a short header comment (title, description),
wrapped in site/layout.html. The build fails on any internal link or file that does not exist.
"""
import json
import re
import shutil
import sys
from html import escape
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DIST = ROOT / "dist"
ORIGIN = "https://openppc.si"
GITHUB = "https://github.com/secondsteplabs/openppc"
# brand/ is the one source of the logo; the site serves copies of these files at its root
BRAND = {"openppc-logo.svg": "logo.svg", "openppc-icon.svg": "favicon.svg", "png/favicon.ico": "favicon.ico",
         "png/apple-touch-icon.png": "apple-touch-icon.png", "social/og-image.png": "og-image.png"}

HEADERS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  X-Frame-Options: DENY
  Permissions-Policy: camera=(), microphone=(), geolocation=(), interest-cohort=()
/media/*
  Cache-Control: public, max-age=604800
/fonts/*
  Cache-Control: public, max-age=31536000, immutable
"""

LLMS = f"""# OpenPPC

> Open-source, read-only Google Ads audits where every number is checked against the account's own export. The app runs in the browser and uploads nothing, and it works inside Claude, Cursor and ChatGPT over MCP.

OpenPPC does two things. It checks any audit (from ChatGPT, Claude, an agency or another tool) against the Google Ads export it was written from, marking every number as traced, a mismatch or not in the data. And it runs free audit templates on an export, where code computes every figure and a checker traces each one before the report is shown.

## Links

- [Home]({ORIGIN}/): what OpenPPC does, with a demo video
- [The app]({ORIGIN}/app/): runs in the browser, no sign-up
- [Install and quick start]({ORIGIN}/docs/install/): browser, command line, self-hosting
- [Claude, Cursor and ChatGPT]({ORIGIN}/docs/install/#ai): MCP server on your computer (`uvx --from "openppc[mcp] @ git+https://github.com/secondsteplabs/openppc" openppc-mcp`), or a web connector you run with `openppc-mcp --http` (a hosted one is coming soon)
- [Source code]({GITHUB}): MIT license
"""


def header(text):
    """The comment at the top of a page: `key: value` lines."""
    match = re.match(r"\s*<!--(.*?)-->", text, re.S)
    if not match:
        raise ValueError("a page must start with a <!-- title: ... description: ... --> comment")
    meta = {}
    for line in match.group(1).strip().splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, text[match.end():].strip()


def route(page):
    """site/pages/docs/install.html -> (/docs/install/, dist/docs/install/index.html)"""
    rel = page.relative_to(SITE / "pages").with_suffix("")
    if rel.name == "404":
        return "/404.html", Path("404.html")
    if rel.name == "index":
        rel = rel.parent
    url = "/" if str(rel) == "." else f"/{rel.as_posix()}/"
    return url, Path(url.strip("/")) / "index.html"


def structured(meta, url, body):
    """JSON-LD for search and answer engines: the product on the home page, questions where there is a FAQ."""
    blocks = []
    if meta.get("schema") == "home":
        blocks.append({"@context": "https://schema.org", "@type": "SoftwareApplication", "name": "OpenPPC",
                       "applicationCategory": "BusinessApplication", "operatingSystem": "Web browser, macOS, Windows, Linux",
                       "description": meta["description"], "url": ORIGIN + url, "license": "https://opensource.org/licenses/MIT",
                       "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}, "codeRepository": GITHUB})
    faqs = re.findall(r"<details><summary>(.*?)</summary><p>(.*?)</p></details>", body, re.S)
    if faqs:
        blocks.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"<[^>]+>", "", a)}}
            for q, a in faqs]})
    return "\n".join(f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>' for b in blocks)


def broken_links(out):
    """Every internal href and src must point at a file in the build."""
    broken = []
    for page in out.rglob("*.html"):
        if "app" in page.relative_to(out).parts:
            continue  # the app is built and tested on its own
        for ref in re.findall(r'(?:href|src|poster)="(/[^"#?]*)', page.read_text(encoding="utf-8")):
            target = out / ref.lstrip("/")
            if ref.endswith("/"):
                target = target / "index.html"
            if not target.exists():
                broken.append(f"{page.relative_to(out)} -> {ref}")
    return broken


def build(out=DIST):
    out = Path(out)
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(SITE / "static", out)
    shutil.copytree(ROOT / "web", out / "app")
    for src, dest in BRAND.items():
        shutil.copyfile(ROOT / "brand" / src, out / dest)
    layout = Template((SITE / "layout.html").read_text(encoding="utf-8"))
    urls = []
    for page in sorted((SITE / "pages").rglob("*.html")):
        meta, body = header(page.read_text(encoding="utf-8"))
        url, dest = route(page)
        docs = url.startswith("/docs/")
        html = layout.substitute(
            title=escape(meta["title"]), description=escape(meta["description"]),
            canonical=ORIGIN + url, body=body, structured=structured(meta, url, body), scripts="",
            docs_current=' aria-current="page"' if docs and url == "/docs/" else "",
            install_current=' aria-current="page"' if url == "/docs/install/" else "")
        (out / dest).parent.mkdir(parents=True, exist_ok=True)
        (out / dest).write_text(html, encoding="utf-8")
        if url != "/404.html":
            urls.append(url)
    urls.append("/app/")
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{ORIGIN}{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {ORIGIN}/sitemap.xml\n", encoding="utf-8")
    (out / "llms.txt").write_text(LLMS, encoding="utf-8")
    (out / "_headers").write_text(HEADERS, encoding="utf-8")
    return {"pages": urls, "broken": broken_links(out)}


def main():
    report = build()
    for link in report["broken"]:
        print(f"broken link: {link}", file=sys.stderr)
    print(f"built {len(report['pages'])} pages into {DIST.relative_to(ROOT)}/")
    sys.exit(1 if report["broken"] else 0)


if __name__ == "__main__":
    main()

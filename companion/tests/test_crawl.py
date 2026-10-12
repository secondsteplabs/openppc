"""The crawler: robots.txt as RFC 9309 reads it, sitemaps, URL clean-up, per-pattern caps, and what a crawl keeps
when it stops early."""
import pytest
from sites import acme, local, page

from openppc_online.siteaudit import crawl as crawl_module
from openppc_online.siteaudit.crawl import PROBE, Robots, crawl, follow, normalize, pattern
from openppc_online.siteaudit.net import Guard
from openppc_online.siteaudit.page import read


def test_url_cleanup():
    assert normalize("HTTP://Example.COM:80/a?utm_source=x&b=2&a=1#top") == "http://example.com/a?a=1&b=2"
    assert pattern("https://x.com/product/blue-shirt") == "/product/*"
    with pytest.raises(ValueError):
        normalize("mailto:someone@example.com")


def test_the_crawl_follows_links_sitemaps_and_robots_txt(serve):
    base = serve(acme)
    c = crawl(base, local(), fast=True)
    assert base + "/about" in c.pages and not any("utm_" in u for u in c.pages)
    assert base + "/private/x" in c.robots_blocked and base + "/private/x" not in c.pages
    assert c.skipped["/item?"] == 5  # 10 query variants per path
    assert c.pages[base + "/broken"].status == 404 and c.referrer[base + "/broken"] == base + "/"
    assert c.pages[base + "/old"].resp.hops == [(base + "/old", 301)]
    assert c.sitemap_files == [base + "/sitemap.xml"] and base + "/gone" in c.sitemap_urls
    assert c.probe is not None and c.probe.status == 404 and not c.llms_txt
    elsewhere = f"http://elsewhere.test:{base.rsplit(':', 1)[1]}/missing"
    assert c.external[elsewhere].status == 404
    assert not any(p.resp.body for p in c.pages.values())  # read, then let go


def test_robots_txt_is_read_as_rfc_9309_says():
    r = Robots("User-agent: *\nDisallow: /\n\nUser-agent: OpenPPC/1.0\nDisallow: /private\nAllow: /private/ok$\n"
               "Disallow: /*.pdf$\nDisallow: /café\nCrawl-delay: 2  # seconds\nSitemap: https://x.test/s.xml\n")
    allowed = {path: r.can_fetch("OpenPPC", "https://x.test" + path) for path in (
        "/", "/private/x", "/private/ok", "/private/ok/more", "/files/a.pdf", "/files/a.pdf?x=1", "/caf%C3%A9",
        "/robots.txt")}
    assert allowed == {"/": True, "/private/x": False, "/private/ok": True, "/private/ok/more": False,
                       "/files/a.pdf": False, "/files/a.pdf?x=1": True, "/caf%C3%A9": False, "/robots.txt": True}
    assert not r.can_fetch("GPTBot", "https://x.test/")  # no group of its own: `*`
    assert r.crawl_delay("OpenPPC") == 2 and r.site_maps() == ["https://x.test/s.xml"]
    tie = Robots("User-agent: *\nDisallow: /a\nAllow: /a\nDisallow: /b\nAllow: /b/c\n")
    assert tie.can_fetch("x", "https://x.test/a") and tie.can_fetch("x", "https://x.test/b/c")
    assert not tie.can_fetch("x", "https://x.test/b/d")


def test_a_failing_robots_txt_stops_the_crawl(serve):
    base = serve(lambda b: {**acme(b), "/robots.txt": (500, {}, "")})
    c = crawl(base, local(), fast=True)
    assert list(c.pages) == [base + "/"] and c.robots_failed and "robots.txt couldn't be read" in c.incomplete


def test_robots_txt_is_read_before_the_start_page(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home")),
                            "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nDisallow: /\n")},
                 fallback=(200, {}, page("Oops")))
    c = crawl(base, local(), fast=True, external=False)
    assert serve.asked == ["/robots.txt"] and not c.pages and c.probe is None
    assert "robots.txt disallows it" in c.incomplete


def test_a_sitemap_with_a_document_type_declaration_is_not_read(serve):
    bomb = "<?xml version='1.0'?><!DOCTYPE x [<!ENTITY a 'aaaa'>]><urlset><url><loc>&a;</loc></url></urlset>"
    base = serve(lambda b: {"/": (200, {}, page("Home")), "/sitemap.xml": (200, {"Content-Type": "text/xml"}, bomb)})
    c = crawl(base, local(), fast=True, external=False)
    assert c.sitemap_files == [] and "document type declaration" in c.sitemap_errors[0]


def test_urls_with_spaces_and_accents_are_fetched(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home", "<a href='/café menu'>Menu</a>")),
                            "/caf%C3%A9%20menu": (200, {}, page("Menu"))})
    c = crawl(base, local(), fast=True, external=False)
    assert c.pages[base + "/caf%C3%A9%20menu"].status == 200


def test_the_crawl_stays_on_the_host_the_start_page_moves_to(serve):
    base = serve(lambda b: {"/": (302, {"Location": "/en/"}, ""), "/en/": (200, {}, page("Home"))})
    c = crawl(base, local(), fast=True, external=False)
    assert c.origin == base and c.pages[base + "/"].resp.final_url == base + "/en/"
    assert c.pages[base + "/en/"].info is not None


def test_ctrl_c_keeps_what_was_crawled(serve, monkeypatch):
    def interrupt(*args, **kw):
        raise KeyboardInterrupt
    monkeypatch.setattr(crawl_module, "wait", interrupt)
    base = serve(acme)
    c = crawl(base, local(), fast=True)
    assert c.incomplete == "stopped with Ctrl-C" and base + "/" in c.pages


def test_the_page_limit_and_a_429_retried_once(serve, monkeypatch):
    c = crawl(serve(acme), local(), fast=True, external=False, max_pages=3)
    assert len(c.pages) == 3 and c.incomplete == "stopped at the `--max-pages` limit"
    monkeypatch.setattr(crawl_module, "RETRY_AFTER_MAX", 0.0)
    base = serve(lambda b: {"/": (200, {}, page("Home", "<a href='/busy'>Busy</a>")),
                            "/busy": (429, {"Retry-After": "1"}, "")})
    before = serve.asked.count("/busy")
    c = crawl(base, local(), fast=True, external=False)
    assert c.pages[base + "/busy"].status == 429 and serve.asked.count("/busy") - before == 2


def test_links_javascript_added_are_followed_under_the_same_rules(serve):
    base = serve(lambda b: {**acme(b), "/hidden": (200, {}, page("Hidden", "<a href='/hidden/deeper'>On</a>")),
                            "/hidden/deeper": (200, {}, page("Deeper"))})
    guard = local()
    c = crawl(base, guard, fast=True, external=False)
    before = set(c.pages)
    links = {base + "/hidden": base + "/", base + "/private/js": base + "/", base + "/about": base + "/"}
    assert follow(c, guard, links, max_pages=len(c.pages) + 1, fast=True) == 1  # the page limit counts both passes
    assert set(c.pages) - before == {base + "/hidden"} and c.pages[base + "/hidden"].depth == 1
    assert base + "/private/js" in c.robots_blocked and c.incomplete == "stopped at the `--max-pages` limit"


def test_a_missing_page_answering_200_is_recorded_and_llms_txt_counts_only_as_text(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home"))}, fallback=(200, {}, page("Oops")))
    c = crawl(base, local(), fast=True, external=False)
    assert c.probe is not None and c.probe.url == base + PROBE and c.probe.status == 200
    assert not c.llms_txt  # the "not found" page answering /llms.txt is not an llms.txt
    base = serve(lambda b: {"/": (200, {}, page("Home")),
                            "/llms.txt": (200, {"Content-Type": "text/plain"}, "# Acme\n> Plumbing\n")})
    assert crawl(base, local(), fast=True, external=False).llms_txt


def test_a_bot_wall_stops_the_crawl_at_the_start_page(serve):
    wall = (403, {"Server": "cloudflare"}, "<title>Just a moment...</title> challenge")
    base = serve(lambda b: {"/": wall})
    c = crawl(base, local(), fast=True)
    assert c.blocked_by == "Cloudflare" and list(c.pages) == [base + "/"]


def test_where_a_crawl_may_start(serve):
    base = serve(acme)
    with pytest.raises(ValueError, match=r"couldn't fetch https://127\.0\.0\.1"):  # a bare domain means https
        crawl(base.split("://", 1)[1], local())
    with pytest.raises(ValueError, match="not an http"):  # not rewritten into https://mailto:a@b.com
        crawl("mailto:a@b.com", local())
    with pytest.raises(ValueError, match="no address"):
        crawl(" ", local())
    with pytest.raises(ValueError, match="--allow-private"):
        crawl(base, Guard())


def test_microdata_items_are_read_with_their_properties():
    info = read("<div itemscope itemtype='https://schema.org/Product'><span itemprop='name'>Drain</span>"
                "<div itemprop='brand' itemscope itemtype='https://schema.org/Brand'><b itemprop='name'>A</b></div>"
                "</div><div itemscope itemtype='http://schema.org/Event'><meta itemprop='name' content='x'>"
                "<meta itemprop='startDate' content='2026-10-05'><span itemprop='location'>here", "https://a.test/")
    assert ("Product", {"name", "brand"}) in info.items and ("Brand", {"name"}) in info.items
    assert ("Event", {"name", "startDate", "location"}) in info.items  # closed by the end of the page

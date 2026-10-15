"""The browser pass without a browser: the vendored axe-core is the one npm publishes, the pages it picks, and what it
says when Playwright isn't installed. tests/test_render_e2e.py drives it in Chromium."""
import hashlib

import pytest
from sites import local, page

from openppc_online.siteaudit import render as render_module
from openppc_online.siteaudit import words
from openppc_online.siteaudit.crawl import crawl
from openppc_online.siteaudit.render import AXE_VERSION, INSTALL, axe_source, pick, preflight, render

# axe-core@4.10.3's axe.min.js as npm publishes it (cdn.jsdelivr.net/npm/axe-core@4.10.3/axe.min.js)
AXE_SHA256 = "880970c081707360e64f34cea25ff91892f5bc95675b0776925b9709dd8a68bb"


def test_the_vendored_axe_core_is_the_published_file_with_its_license():
    source = axe_source()
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == AXE_SHA256
    assert source.startswith(f"/*! axe v{AXE_VERSION}\n") and "Mozilla Public" in source[:400]


def test_every_plain_worded_accessibility_rule_is_one_axe_runs():
    source = axe_source()
    assert [rule for rule in words.A11Y if f'id:"{rule}"' not in source] == []


def test_the_home_page_then_one_page_per_section_is_rendered(serve):
    links = "".join(f"<a href='{p}'>{p}</a>" for p in ("/shop/a", "/shop/b", "/blog/x", "/about", "/blog/y"))
    base = serve(lambda b: {"/": (200, {}, page("Home", links)),
                            **{p: (200, {}, page(p)) for p in ("/shop/a", "/shop/b", "/blog/x", "/about", "/blog/y")}})
    c = crawl(base, local(), fast=True, external=False)  # pages fetched in parallel arrive in any order
    picked = pick(c)
    assert picked[0] == base + "/" and sorted(u.split("/")[3] for u in picked[1:]) == ["about", "blog", "shop"]
    assert pick(c, 2) == picked[:2]


def test_without_playwright_it_says_how_to_install_it(serve, monkeypatch):
    monkeypatch.setattr(render_module, "sync_playwright", None)
    c = crawl(serve(lambda b: {"/": (200, {}, page("Home"))}), local(), fast=True, external=False)
    for attempt in (preflight, lambda: render(c, local())):
        with pytest.raises(ValueError, match="openppc-online\\[render\\]") as e:
            attempt()
        assert str(e.value) == INSTALL

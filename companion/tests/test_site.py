"""`openppc-online site`, the command: the fork's QA matrix against its QA site, the hosts it contacts (fitness
function 9), the secrets it never shows (fitness function 11), the webhook, the JSON schema and its exit codes."""
import json
import re
import socket
from html import escape
from pathlib import Path

import jsonschema
import pytest
from sites import acme, page, qa_site

from openppc_online import site
from openppc_online.cli import main
from openppc_online.siteaudit import crawl as crawl_module
from openppc_online.siteaudit import render as render_module
from openppc_online.siteaudit.crux import KEY_ENV

COMPANION = Path(__file__).resolve().parent.parent
PACKS = COMPANION / "examples" / "rulepacks"
SCHEMA = json.loads((COMPANION / "openppc_online" / "schemas" / "site-report.schema.json").read_text(encoding="utf-8"))
QA_PACK = {"openppc_site": 1, "name": "QA pack",
           "rules": [{"id": "qa-title-has-brand", "category": "seo", "severity": "low", "title": "Title doesn't name Acme",
                      "fix": "Add the brand.", "require": {"field": "title", "contains": "Acme"}}],
           "suppress": [{"rule": "site-h1-missing", "reason": "QA suppression test"}]}
P = ["--allow-private", "--fast"]
CRUX_HOST = "chromeuxreport.googleapis.com"


def _dead_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run(args, capsys):
    try:
        code = main(args)
    except SystemExit as e:  # argparse's own errors
        code = e.code
    out = capsys.readouterr()
    return code, out.out + "\n" + out.err


# the fork's QA matrix, SITE-01 to SITE-28 (SITE-29 and 30, with --render, are in test_render_e2e.py); "{bad}",
# "{good}" and "{blocked}" are the QA sites, "{out}" a scratch folder, "{baseline}" the bad site's own --format json result
CASES = [
    ("SITE-01", ["{bad}", *P], 0, ["Site audit", "REDACTED"]),
    ("SITE-02", ["{good}", *P], 0, ["Overall"]),
    ("SITE-03", ["{bad}", *P, "--fail-on", "high"], 2, []),
    ("SITE-04", ["{bad}", *P, "--fail-on", "medium"], 2, []),
    ("SITE-05", ["{bad}", *P, "--fail-on", "low"], 2, []),
    ("SITE-06", ["{good}", *P, "--fail-on", "medium", "--no-external"], 2, ["served over plain HTTP"]),
    ("SITE-07", ["{blocked}", *P], 0, ["robots.txt disallows"]),
    ("SITE-08", ["{blocked}", *P, "--fail-on", "high"], 4, ["Inconclusive"]),  # the fork's B5
    ("SITE-09", ["{bad}", *P, "--format", "json", "--out", "{out}/bad.json"], 0, ["wrote"]),
    ("SITE-10", ["{bad}", *P, "--baseline", "{baseline}", "--fail-on", "low"], 0, ["0 new"]),  # the fork's B7
    ("SITE-11", ["{good}", *P, "--baseline", "{baseline}"], 0, ["fixed"]),
    ("SITE-12", ["{bad}", *P, "--format", "sarif", "--out", "{out}/site.sarif"], 0, ['"version": "2.1.0"']),
    ("SITE-13", ["{bad}", *P, "--format", "html", "--out", "{out}/site.html"], 0, ["<!doctype html>"]),
    ("SITE-14", ["{bad}", *P, "--max-pages", "3"], 0, ["`--max-pages` limit"]),
    ("SITE-15", ["{bad}", "--allow-private", "--max-time", "1"], 0, []),
    ("SITE-16", ["{bad}", *P, "--no-external"], 0, ["!Broken links to other sites"]),
    ("SITE-17", ["{bad}", *P, "--config", "{out}/qa-pack.json"], 0, ["QA suppression test", "Acme"]),
    ("SITE-18", ["{bad}", *P, "--config", str(PACKS / "agency-baseline.json")], 0, ["main heading"]),
    ("SITE-19", ["{bad}", *P, "--config", str(PACKS / "ecommerce.json"), "--config",
                 str(PACKS / "project-example.json")], 0, ["The first-party collector isn't on the site"]),
    ("SITE-20", ["{bad}", *P, "--max-per-pattern", "1"], 0, ["skipped"]),
    ("SITE-21", ["{dead}", *P], 1, ["couldn't fetch"]),
    ("SITE-22", ["{dead}", *P, "--fail-on", "high"], 1, ["couldn't fetch"]),
    ("SITE-23", ["{bare}", *P], 1, ["couldn't fetch https://127.0.0.1"]),
    ("SITE-24", ["{bad}", *P, "--post-to", "{hook}"], 0, ["posted the result to 127.0.0.1 (204)"]),
    ("SITE-25", ["{bad}", *P, "--post-to", "http://127.0.0.1:{dead_port}/nothing"], 0, ["couldn't post"]),
    ("SITE-26", ["{bad}about", *P], 0, ["Site audit"]),
    ("SITE-27", ["{bad_upper}", *P], 0, ["Site audit"]),
    ("SITE-28", ["{bad}", "--allow-private"], 0, ["Site audit"]),
]


@pytest.mark.parametrize("case, args, expected, wanted", CASES, ids=[c[0] for c in CASES])
def test_the_qa_matrix(case, args, expected, wanted, serve, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(crawl_module, "POLITE_INTERVAL", 0.02)  # the pace, not the politeness, is what's slow
    bad, good, blocked = qa_site(serve, "bad"), qa_site(serve, "good"), qa_site(serve, "blocked")
    hook = serve(lambda b: {"/hook": (204, {}, "")}) + "/hook"
    dead_port = _dead_port()
    (tmp_path / "qa-pack.json").write_text(json.dumps(QA_PACK), encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    if any("{baseline}" in a for a in args):
        assert main(["site", bad, *P, "--format", "json", "--out", str(baseline)]) == 0
        capsys.readouterr()
    values = {"bad": bad, "good": good, "blocked": blocked, "out": str(tmp_path), "baseline": str(baseline),
              "hook": hook, "dead": f"http://127.0.0.1:{dead_port}/", "dead_port": str(dead_port),
              "bare": bad.split("://", 1)[1], "bad_upper": bad.replace("http://", "HTTP://")}
    full = ["site", *(a.format(**values) for a in args)]
    code, output = _run(full, capsys)
    if "--out" in full:
        output += Path(full[full.index("--out") + 1]).read_text(encoding="utf-8")
    assert code == expected, output[-2000:]
    for w in wanted:
        if w.startswith("!"):
            assert w[1:] not in output
        else:
            assert w in output, w
    assert "Traceback" not in output and "Number check FAILED" not in output
    if case == "SITE-24":
        path, headers, body = serve.posted[-1]
        posted = json.loads(body)
        assert path == "/hook" and posted["text"].startswith("OpenPPC site audit of") and posted["findings"]


def test_the_json_result_matches_its_schema(serve, tmp_path, capsys):
    bad = qa_site(serve, "bad")
    first = tmp_path / "first.json"
    assert main(["site", bad, *P, "--format", "json", "--out", str(first)]) == 0
    (tmp_path / "qa-pack.json").write_text(json.dumps(QA_PACK), encoding="utf-8")
    again = tmp_path / "again.json"
    assert main(["site", bad, *P, "--format", "json", "--config", str(tmp_path / "qa-pack.json"),
                 "--baseline", str(first), "--out", str(again)]) == 0
    for path in (first, again):
        doc = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.validate(doc, SCHEMA)
        assert doc["format_version"] == 1 and doc["passed"] and doc["openppc_online"]
    assert doc["baseline"]["file"] == str(first) and doc["suppressed"][0]["reason"] == "QA suppression test"
    assert doc["scores"]["tracking"]["not_scored"] == "needs --render"


@pytest.fixture
def hosts(monkeypatch):
    """Every host name looked up, and every address connected to. Names the test knows resolve to 127.0.0.1;
    anything else fails to resolve, so nothing here leaves the computer."""
    seen = {"resolved": [], "connected": []}
    real_lookup, real_connect = socket.getaddrinfo, socket.socket.connect

    def lookup(host, port, *args, **kw):
        seen["resolved"].append(host)
        if host in ("127.0.0.1", "elsewhere.test", "localhost"):
            return real_lookup("127.0.0.1", port, *args, **kw)
        raise socket.gaierror(f"{host} isn't resolved in this test")

    def connect(self, address):
        seen["connected"].append(address[0])
        return real_connect(self, address)
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    monkeypatch.setattr(socket.socket, "connect", connect)
    return seen


def test_the_command_contacts_only_its_declared_hosts(serve, hosts, tmp_path, capsys):
    base = serve(acme)  # links to elsewhere.test, an external host
    hook = serve(lambda b: {"/hook": (204, {}, "")}) + "/hook"
    assert main(["site", base, *P, "--out", str(tmp_path / "a.md")]) == 0
    assert set(hosts["resolved"]) == {"127.0.0.1", "elsewhere.test"}  # the site, and the host it links to
    hosts["resolved"].clear()
    assert main(["site", base, *P, "--no-external", "--out", str(tmp_path / "b.md")]) == 0
    assert set(hosts["resolved"]) == {"127.0.0.1"}
    hosts["resolved"].clear()
    assert main(["site", base, *P, "--no-external", "--crux-key", "KEY", "--post-to", hook.replace("127.0.0.1",
                 "localhost"), "--out", str(tmp_path / "c.md")]) == 0
    assert set(hosts["resolved"]) == {"127.0.0.1", CRUX_HOST, "localhost"}  # CrUX and the webhook: only when asked
    assert set(hosts["connected"]) == {"127.0.0.1"}
    assert "Real visitors" in (tmp_path / "c.md").read_text(encoding="utf-8")  # the API was asked, and failed


@pytest.mark.parametrize("fmt", ["md", "json", "html", "sarif"])
def test_secrets_never_show(fmt, serve, hosts, tmp_path, capsys, monkeypatch):
    key, path = "SENTINEL-CRUX-KEY-7d41", "/hooks/T000/SENTINEL-HOOK-PATH-c9e2"
    bad = qa_site(serve, "bad")  # links to /login?token=SECRET123abc&email=a@b.com
    hook = serve(lambda b: {path: (204, {}, "")}) + path
    out = tmp_path / f"site.{fmt}"
    monkeypatch.setenv(KEY_ENV, key)
    code, output = _run(["site", bad, *P, "--crux", "--format", fmt, "--out", str(out), "--post-to", hook], capsys)
    assert code == 0, output
    shown = output + out.read_text(encoding="utf-8") + serve.posted[-1][2].decode()
    for secret in (key, "SENTINEL-HOOK-PATH", "SECRET123abc", "a@b.com"):
        assert secret not in shown, secret
    assert "posted the result to 127.0.0.1" in output


def test_the_webhook_follows_no_redirect_and_needs_allow_private_for_this_computer(serve, tmp_path, capsys):
    base = serve(acme)
    moved = serve(lambda b: {"/hook": (302, {"Location": b + "/elsewhere"}, "")})
    code, output = _run(["site", base, *P, "--no-external", "--post-to", moved + "/hook",
                         "--out", str(tmp_path / "a.md")], capsys)
    assert code == 0 and "couldn't post the result to 127.0.0.1: it answered 302" in output
    assert "/elsewhere" not in serve.asked
    guard = site.Guard()
    assert "--allow-private" in site.post(moved + "/hook", "{}", guard)


@pytest.mark.parametrize("url, allowed", [
    ("https://hooks.slack.com/services/T0/B0/x", True), ("http://127.0.0.1:9000/hook", True),
    ("http://localhost/hook", True), ("http://[::1]:9000/hook", True), ("http://example.com/hook", False),
    ("ftp://127.0.0.1/hook", False), ("hooks.slack.com/x", False), ("https:///x", False)])
def test_which_webhook_addresses_are_taken(url, allowed):
    if allowed:
        assert site.webhook_host(url) and "/" not in site.webhook_host(url)
    else:
        with pytest.raises(ValueError, match="--post-to needs an https:// address"):
            site.webhook_host(url)


@pytest.mark.parametrize("args", [
    ["--post-to", "ftp://x"], ["--post-to", "http://example.com/hook"], ["--crux"], ["--crux-key"],
    ["--crux-key", " "],
    ["--config", "missing.json"], ["--baseline", "missing.json"], ["--max-pages", "0"], ["--max-pages", "x"],
    ["--max-time", "0"], ["--max-time", "nan"], ["--max-per-pattern", "-1"], ["--format", "pdf"],
    ["--screenshots", "shots"], ["--render-url", "/thanks"], ["--render", "--render-url", "https://elsewhere.test/x"],
    ["--render-pages", "0"], ["--vitals-pages", "-1"], ["--render"]])
def test_bad_input_fails_before_the_crawl(args, monkeypatch, capsys, tmp_path):
    def never(*a, **kw):
        raise AssertionError("crawled")
    monkeypatch.setattr(site, "crawl", never)
    monkeypatch.setattr(render_module, "sync_playwright", None)  # --render, with the extra not installed
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    code, output = _run(["site", "https://example.invalid", *args], capsys)
    assert code == 1, output
    assert not (tmp_path / "shots").exists()
    if args == ["--render"]:
        assert 'pip install "openppc-online[render]"' in output


@pytest.mark.parametrize("args, said", [
    (["--lighthouse", "missing"], "no Lighthouse in missing: install it there with npm install lighthouse@13"),
    (["--psi", "--lighthouse", "lh"], "--psi and --lighthouse both measure with Lighthouse: pick one"),
    (["--lighthouse", "lh/node_modules/lighthouse", *(a for i in range(5) for a in ("--render-url", f"/p{i}"))],
     "--lighthouse measures at most 5 pages: the start page and up to 4 --render-url pages"),
])
def test_lighthouse_needs_its_folder_and_isnt_mixed_with_psi(args, said, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(site, "crawl", lambda *a, **kw: pytest.fail("crawled"))
    monkeypatch.setattr(site.lighthouse, "node", lambda: "node")
    monkeypatch.chdir(tmp_path)
    found = tmp_path / "lh" / "node_modules" / "lighthouse"
    (found / "core").mkdir(parents=True)
    (found / "core" / "index.js").write_text("", encoding="utf-8")
    (found / "package.json").write_text('{"name": "lighthouse", "version": "13.0.1"}', encoding="utf-8")
    code, output = _run(["site", "https://example.invalid", *args], capsys)
    assert code == 1 and said in output, output


HOSTILE = "<img src=x onerror=alert(1)>`<script>alert(2)</script>"


def test_the_sites_own_text_never_becomes_markup_in_the_report(serve, tmp_path):
    base = serve(lambda b: {"/": (200, {}, page(escape(HOSTILE), f"<h1>{HOSTILE}</h1><a href='/gone?q={HOSTILE}'>x</a>"
                                                         f"<a href=\"/moved\">{HOSTILE}</a>")),
                            "/moved": (301, {"Location": f"/gone/{HOSTILE}"}, "")})
    pack = tmp_path / "pack.json"  # a rule that quotes each page's title in its finding
    pack.write_text(json.dumps({"openppc_site": 1, "rules": [{
        "id": "title-is-acme", "category": "seo", "severity": "low", "title": "Title isn't Acme", "fix": "Fix it.",
        "require": {"field": "title", "equals": "Acme"}}]}), encoding="utf-8")
    md, html = tmp_path / "site.md", tmp_path / "site.html"
    assert main(["site", base, *P, "--config", str(pack), "--out", str(md)]) == 0
    assert main(["site", base, *P, "--config", str(pack), "--format", "html", "--out", str(html)]) == 0
    markdown = md.read_text(encoding="utf-8")
    assert "<img src=x onerror=alert(1)>'<script>" in markdown  # the title, quoted, its backtick made harmless
    outside_code = re.sub(r"`[^`\n]*`", "", markdown)
    page_html = html.read_text(encoding="utf-8").lower()
    assert "onerror=alert(1)&gt;" in page_html  # there too, escaped
    for shown in (outside_code, page_html):
        for markup in ("<img src=x", "<script>alert"):
            assert markup not in shown, markup


def test_this_computer_needs_allow_private(serve, capsys):
    base = serve(acme)
    code, output = _run(["site", base, "--fast"], capsys)
    assert code == 1 and "--allow-private" in output

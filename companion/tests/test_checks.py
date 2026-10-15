"""The site checks, the tag signatures, field data and the report: a local site with known problems is crawled and
each planted problem is found, and every number in the report traces back to the crawl."""
import json

import pytest
from sites import acme, by_id, local, page

from openppc_online.siteaudit import checks, crux, packs, tags, words
from openppc_online.siteaudit.crawl import AD_PARAMS, crawl
from openppc_online.siteaudit.lab.insights import Insight, TagCost
from openppc_online.siteaudit.page import read
from openppc_online.siteaudit.render import AdParamsSeen, Observation, Rendered, Vitals
from openppc_online.siteaudit.report import Extras, data, report, sarif
from openppc_online.siteaudit.tags import consent_mode_on, known_host, vendor_of
from openppc_online.siteaudit.triage import Diff, Suppressed, fingerprint


def test_the_crawl_finds_the_planted_problems(serve):
    base = serve(acme)
    c = crawl(base, local(), fast=True)
    f = by_id(checks.evaluate(c))
    assert f["site-broken-internal"].items == [base + "/broken"]
    assert base + "/old" in f["site-redirect-linked"].items
    assert f["site-jsonld-invalid"].items == [base + "/about"]
    assert "`offers`" in f["site-jsonld-incomplete"].notes[base + "/services/drain"]
    assert f["site-img-alt-missing"].items == [base + "/about"]
    assert f["site-noindex"].items == [base + "/services/drain"]
    assert set(f["site-sitemap-bad-url"].items) == {base + "/old", base + "/gone"}
    assert f["site-ai-crawlers-blocked"].items == ["`GPTBot`"]
    assert f["site-broken-external"].items == [f"http://elsewhere.test:{base.rsplit(':', 1)[1]}/missing"]
    assert "site-no-https" in f and "site-soft-404" not in f and "site-sitemap-missing" not in f


def test_every_number_in_the_report_is_traced(serve):
    base = serve(acme)
    c = crawl(base, local(), fast=True)
    markdown, _, passed = report(c, None, checks.evaluate(c))
    assert passed, markdown
    assert "need a browser: run again with `--render`" in markdown and "`--allow-private`" in markdown


def test_a_failing_robots_txt_is_a_finding_and_the_report_still_traces(serve):
    base = serve(lambda b: {**acme(b), "/robots.txt": (500, {}, "")})
    c = crawl(base, local(), fast=True)
    f = by_id(checks.evaluate(c))
    assert "site-robots-unreachable" in f and "site-sitemap-missing" not in f
    markdown, _, passed = report(c, None, list(f.values()))
    assert passed and "Inconclusive: robots.txt couldn't be read" in markdown and "## Scores" not in markdown


def test_the_home_page_is_where_the_root_redirects(serve):
    base = serve(lambda b: {"/": (302, {"Location": "/en/"}, ""), "/en/": (200, {}, page("Home"))})
    f = by_id(checks.evaluate(crawl(base, local(), fast=True, external=False)))
    assert f["site-structured-data-none"].items == f["site-no-analytics"].items == [base + "/en/"]
    f = by_id(checks.evaluate(crawl(base, local(), fast=True, external=False, max_pages=1)))
    assert "site-no-analytics" not in f  # the home page wasn't read, so nothing is known about its tags


def test_a_missing_page_answering_200_is_a_soft_404(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home"))}, fallback=(200, {}, page("Oops")))
    assert "site-soft-404" in by_id(checks.evaluate(crawl(base, local(), fast=True, external=False)))


def test_a_bot_wall_is_the_only_finding(serve):
    base = serve(lambda b: {"/": (403, {"Server": "cloudflare"}, "<title>Just a moment...</title> challenge")})
    c = crawl(base, local(), fast=True)
    assert [f.id for f in checks.evaluate(c)] == ["site-bot-blocked"]


def test_microdata_items_are_checked_for_required_properties():
    info = read("<div itemscope itemtype='https://schema.org/Product'><span itemprop='name'>Drain</span></div>",
                "https://a.test/")
    _, incomplete = checks._structured({"https://a.test/": info})
    assert incomplete == {"https://a.test/": "`Product` needs `offers` or `review` or `aggregateRating`"}


def test_a_report_with_every_rule_passes_its_number_check(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    c = crawl(base, local(), fast=True, external=False)
    markdown, _, passed = report(c, None, [checks.Finding(rule, [base + "/"]) for rule in checks.RULES])
    assert passed, markdown


def test_a_report_with_every_extra_passes_its_number_check(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    c = crawl(base, local(), fast=True, external=False)
    findings = [checks.Finding(rule, [base + "/"]) for rule in checks.RULES]
    spec = checks.Rule("seo", "high", "Titles over 70 characters cost 15% of clicks", "pages", "Cut 2 words.")
    findings.append(checks.Finding("my-rule", [base + "/"], spec=spec))
    used = [Suppressed(packs.Suppression("site-x", "/a*", "Gone by 2027-01, ticket 4411.", "p.json"),
                       [("site-x", base + "/a")])]
    diff = Diff("old.json", {"site-noindex": [base + "/n"]}, [("Pages with no title", base + "/t")], 7)
    field = [crux.FieldData(base, True, {"lcp": 3120.0, "inp": 180.0, "cls": 0.07}, "2026-09-07 to 2026-10-04"),
             crux.FieldData(base + "/", False, error="not enough real-visitor data in Chrome's report")]
    r = Rendered(pages=[Observation(base + "/", screenshot="shots/01-home.png")])
    markdown, _, passed = report(c, r, findings, Extras(["p.json"], used, diff, field))
    assert passed, markdown
    assert "## Scores" in markdown and "Overall: **" in markdown and "### Check by hand" in markdown
    assert "## Real visitors (Chrome UX Report)" in markdown and "3,120 ms" in markdown


def test_the_vitals_section_without_a_measurement(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    c = crawl(base, local(), fast=True, external=False)
    markdown, _, passed = report(c, Rendered(vitals=[Vitals(base + "/", error="timed out")]), [])
    assert passed and "couldn't be measured" in markdown and "representative of" not in markdown
    run = dict.fromkeys(("lcp", "cls", "tbt", "fcp", "ttfb", "si", "tti"), 1.0)
    details = {"lcp_element": "img#hero.big", "lcp_url": base + "/hero.jpg", "blocking": [base + "/app.css"],
               "heavy": [[base + "/hero.jpg", 251_904], [base + "/app.js", 90_112]]}
    markdown, _, passed = report(c, Rendered(vitals=[Vitals(base + "/", runs=[run], details=details),
                                                     Vitals(base + "/b", runs=[run, run], capped=1,
                                                            hits_answered=14)]), [])
    assert passed, markdown
    assert "Lab, throttled phone (rough estimate): 412x823 screen" in markdown and "562.5 ms latency" in markdown
    assert "### `" + base + "/b`" in markdown and "hadn't gone quiet, after 45 seconds" in markdown
    assert "the page sends no visits to the site's analytics" in markdown and "running in a worker" in markdown and "answered on this computer: 14." in markdown
    assert "`img#hero.big`" in markdown and "(246 KB)" in markdown and "block the first paint" in markdown
    assert "One load, so a number just over a line" in markdown and "The representative of 2 loads" in markdown
    assert "| Speed Index | 1 ms | 1 to 1 ms |" in markdown and "## Glossary" in markdown
    # 1 ms is top for the four timings; a layout shift of 1 is poor and costs CLS's quarter of the score
    assert "OpenPPC lab score (uncalibrated): **76** (average, orange)" in markdown and words.DIFFERS in markdown
    assert "**OpenPPC lab score:**" in markdown and "benchmark index" not in markdown  # no benchmark measured
    markdown, _, passed = report(c, Rendered(vitals=[Vitals(base + "/", runs=[run])], benchmark=812.6), [])
    assert passed, markdown
    assert "benchmark index (Lighthouse's CPU test, run before the loads): 813. At 1,000 or below" in markdown
    slow = run | {"fcp": 3000.0, "si": 5800.0, "lcp": 4000.0, "tbt": 600.0, "cls": 0.25}  # each at its median
    assert Vitals(base + "/", runs=[slow]).score == 50 and Vitals(base + "/", runs=[slow], device="desktop").score < 50
    assert Vitals(base + "/", runs=[run | {"si": None}]).score is None


def test_lighthouses_insights_are_listed_with_their_savings_and_traced(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    c = crawl(base, local(), fast=True, external=False)
    run = dict.fromkeys(("lcp", "cls", "tbt", "fcp", "ttfb", "si", "tti"), 1.0)
    found = [Insight("render-blocking-insight", "Render blocking requests", "fail", {"FCP": 900, "LCP": 850},
                     items=[base + "/app.css"]),
             Insight("image-delivery-insight", "Improve image delivery", "fail", {"LCP": 1650}, 353_009),
             Insight("document-latency-insight", "Document request latency", "fail", {},
                     failed=["Server responded slowly (observed 812 ms)"]),
             Insight("cls-culprits-insight", "Layout shift culprits", "fail", {"CLS": 0.124}),
             Insight("cache-insight", "Use efficient cache lifetimes", "pass"),
             Insight("lcp-breakdown-insight", "LCP breakdown", "informative")]
    costs = [TagCost("onetrust", "OneTrust", "consent", 20_480, 212.6, 1),
             TagCost("ga4", "Google Analytics 4", "tag", 153_600, 48.2, 3)]
    markdown, _, passed = report(c, Rendered(vitals=[Vitals(base + "/", runs=[run], insights=found,
                                                            tag_costs=costs)]), [])
    assert passed, markdown
    assert "| OneTrust | consent banner | 20 KB | 213 ms | 1 |" in markdown
    assert "| Google Analytics 4 | tag | 150 KB | 48 ms | 3 |" in markdown
    assert "the DevTools trace engine `0.0.65`) from one more load at full speed, with the phone simulated" in markdown
    assert ("- **Render blocking requests** (`render-blocking-insight`): could save about 900 ms of First Contentful "
            "Paint and 850 ms of Largest Contentful Paint. In plain words: files the browser must fetch") in markdown
    assert "About: `" + base + "/app.css`." in markdown
    assert "1,650 ms of Largest Contentful Paint and 345 KB." in markdown
    assert "(`document-latency-insight`). Failed: Server responded slowly (observed 812 ms). In plain" in markdown
    assert "could save about 0.124 of Cumulative Layout Shift" in markdown
    assert "- Passed: 1; to look at, with nothing to fix: 1." in markdown
    markdown, _, passed = report(c, Rendered(vitals=[Vitals(base + "/", runs=[run], insights=found[4:])]), [])
    assert passed and "- None of them found anything to fix." in markdown
    markdown, _, passed = report(c, Rendered(vitals=[Vitals(base + "/", runs=[run], insights_error="no load")]), [])
    assert passed and "Lighthouse's insights couldn't be worked out: `no load`" in markdown


def test_one_load_just_over_a_line_is_no_finding_but_a_note(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    c = crawl(base, local(), fast=True, external=False)
    near = {"fcp": 900.0, "lcp": 2800.0, "tbt": 150.0, "cls": 0.0, "ttfb": 100.0, "si": 1000.0, "tti": 2000.0}
    clear = near | {"lcp": 3100.0}  # 24% over the good line
    for runs, finding in (([near], False), ([clear], True), ([near, near], True)):
        r = Rendered(vitals=[Vitals(base + "/", runs=runs)])
        assert ("site-lcp-slow" in by_id(checks.evaluate(c, r))) is finding
    markdown, _, passed = report(c, Rendered(vitals=[Vitals(base + "/", runs=[near])]), [])
    assert passed and "too close for one load to call, so no finding: Largest Contentful Paint" in markdown


def test_what_a_browser_pass_saw_becomes_findings(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home", "<a href='/a'>A</a>")), "/a": (200, {}, page("A"))})
    c = crawl(base, local(), fast=True, external=False)
    hit = "https://region1.google-analytics.com/g/collect?v=2&en=page_view"
    r = Rendered(pages=[Observation(base + "/", before=[hit, "https://cdn.unknown.test/x.js"],
                                    links=[base + "/a", base + "/app/deep", "https://other.test/"],
                                    events={"ga4": ["page_view", "step_2"]}, datalayer=["form_submit_3"],
                                    axe=[{"id": "image-alt", "impact": "critical", "help": "Images need alt text",
                                          "targets": ["img.hero"], "criteria": ["1.1.1"]}],
                                    errors=["TypeError: fbq_2 is `not` a function", "SyntaxError: line 40"]),
                        Observation(base + "/a")],
                 ad_params=AdParamsSeen(c.ad_params.url, base + "/?" + "&".join(
                     f"{p}=OPENPPC-TEST" for p in AD_PARAMS if p not in ("gclid", "fbclid")), answered=3))
    f = by_id(checks.evaluate(c, r))
    assert f["site-ad-params-dropped-js"].notes[base + "/"].startswith("loses `gclid`, `fbclid` once its scripts run")
    assert checks.js_dropped_ad_params(c, Rendered(ad_params=AdParamsSeen(c.ad_params.url, error="timed out"))) == []
    assert f["site-js-only-links"].items == [base + "/app/deep"]
    assert f["site-no-consent-banner"].items == ["Google Analytics 4"]
    assert f["site-unknown-third-party"].items == ["cdn.unknown.test"]
    assert f["site-a11y:image-alt"].level == "high"
    assert f["site-js-errors"].items == [base + "/"]
    assert f["site-js-errors"].notes == {base + "/": "`TypeError: fbq_2 is 'not' a function`"}
    markdown, _, passed = report(c, r, list(f.values()))
    assert passed, markdown
    assert "| `page_view`, `step_2` |" in markdown and "dataLayer: `form_submit_3`." in markdown
    assert "Pages with JavaScript errors" in markdown
    doc = data(c, r, list(f.values()))
    assert doc["rendered"]["ad_params"]["dropped"] == ["gclid", "fbclid"] and doc["rendered"]["ad_params"]["answered"] == 3
    assert doc["rendered"]["pages"][0]["errors"][0].startswith("TypeError")
    r = Rendered(pages=[Observation(base + "/", before=[hit], consent="onetrust", accepted=True, selector="#accept",
                                    banner_shift=0.1563), Observation(base + "/a", banner_shift=0.09)])
    f = by_id(checks.evaluate(c, r))
    assert f["site-consent-banner-shift"].items == [base + "/"]
    markdown, _, passed = report(c, r, list(f.values()))
    assert passed and "it moved the page by a layout shift of 0.156 (a desktop window" in markdown


@pytest.mark.parametrize("url, vendor", [
    ("https://alb.reddit.com/rp?id=t2_x", "reddit"), ("https://px4.ads.linkedin.com/collect?pid=1", "linkedin"),
    ("https://region1.google-analytics.com/g/s/collect?v=2", "ga4"),
    ("https://ad.doubleclick.net/ccm/collect?en=page_view", "google-ads"),
    ("https://www.google.com/rmkt/collect/123/", "google-ads"),
    ("https://edge.adobedc.net/ee/v1/interact?configId=x", "adobe")])
def test_current_tag_endpoints_count_as_hits(url, vendor):
    assert vendor_of(url) == (vendor, "hit")


def test_a_known_tags_other_requests_are_not_unknown_hosts():
    assert vendor_of("https://assets.adobedtm.com/abc/launch-1.min.js") == ("adobe-tags", "load")  # not Analytics
    assert known_host("connect.facebook.net") and known_host("c.clarity.ms") and known_host("bat.bing.com")
    assert not known_host("cdn.taboola.com")


def test_consent_mode_is_seen_in_google_hits():
    assert consent_mode_on("https://region1.google-analytics.com/g/collect?v=2&gcs=G111")
    assert consent_mode_on("https://www.google.com/ccm/collect?gcd=13l3l3l3l1")
    assert not consent_mode_on("https://region1.google-analytics.com/g/collect?v=2")
    assert not consent_mode_on("https://example.com/collect?gcs=G111")


@pytest.mark.parametrize("url, body, found", [
    ("https://region1.google-analytics.com/g/collect?v=2&tid=G-ABC123&en=page_view", "", ("ga4", ["page_view"])),
    ("https://www.google-analytics.com/g/collect?v=2&tid=G-ABC123", "en=page_view&_et=4\r\nen=purchase&epn.value=9",
     ("ga4", ["page_view", "purchase"])),
    ("https://www.facebook.com/tr/?id=1&ev=Purchase&cd[value]=9", "", ("meta", ["Purchase"])),
    ("https://bat.bing.com/action/0?ti=1&evt=custom&ea=submit_lead_form&ev=5", "",
     ("microsoft-ads", ["submit_lead_form"])),
    ("https://www.googleadservices.com/pagead/conversion/123/?label=x&value=9", "", ("google-ads", ["conversion"])),
    ("https://px4.ads.linkedin.com/collect?pid=1", "", ("linkedin", [])),
    ("https://www.googletagmanager.com/gtag/js?id=G-ABC123&en=x", "", None)])
def test_a_tag_hit_says_which_events_it_sent(url, body, found):
    assert tags.events_of(url, body) == found


def test_field_data_is_read_through_the_guard_and_the_key_stays_out_of_sight(serve, monkeypatch):
    bins = [{"start": 0, "end": 2500, "density": 0.5}, {"start": 2500, "end": 4000, "density": 0.2},
            {"start": 4000, "density": 0.3}]
    record = {"record": {"metrics": {"largest_contentful_paint": {"percentiles": {"p75": 4200}, "histogram": bins},
                                     "cumulative_layout_shift": {"percentiles": {"p75": "0.05"}}},
                         "collectionPeriod": {"firstDate": {"year": 2026, "month": 9, "day": 7},
                                              "lastDate": {"year": 2026, "month": 10, "day": 4}}}}
    api = serve(lambda b: {"/q": (200, {"Content-Type": "application/json"}, json.dumps(record)),
                           "/none": (404, {}, "{}")})
    monkeypatch.setattr(crux, "ENDPOINT", api + "/q")
    d = crux.query("https://a.test", "SECRET", True, local())
    assert d.p75 == {"lcp": 4200.0, "cls": 0.05} and d.period == "2026-09-07 to 2026-10-04"
    assert d.shares == {"lcp": [0.5, 0.2, 0.3]} and d.verdict == "failed" and d.device == "phone"
    path, headers, body = serve.posted[0]
    assert "SECRET" not in path and headers["X-Goog-Api-Key"] == "SECRET"
    assert json.loads(body) == {"origin": "https://a.test", "formFactor": "PHONE"}
    found = []
    checks._field_findings([d], lambda rule, items, notes=None, severity="": found.append(
        checks.Finding(rule, items, notes or {}, severity=severity)))
    found = by_id(found)
    assert found["site-field-lcp-slow"].level == "high" and "site-field-cls-high" not in found
    monkeypatch.setattr(crux, "ENDPOINT", api + "/none")
    assert crux.query("https://a.test/", "SECRET", False, local()).error == \
        "not enough real-visitor data in Chrome's report"
    assert "--allow-private" in crux.query("https://a.test", "SECRET", True, crux.Guard()).error  # the guard's rules


def test_sarif_has_a_result_per_page_with_stable_fingerprints(serve):
    base = serve(acme)
    c = crawl(base, local(), fast=True, external=False)
    doc = sarif(c, checks.evaluate(c), "0.0.0")
    run = doc["runs"][0]
    assert doc["version"] == "2.1.0" and run["tool"]["driver"]["rules"]
    hit = next(x for x in run["results"] if x["ruleId"] == "site-broken-internal")
    assert hit["level"] == "error" and hit["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == \
        base + "/broken"
    assert hit["partialFingerprints"]["openppcSite/fp1"] == fingerprint("site-broken-internal", base + "/broken")

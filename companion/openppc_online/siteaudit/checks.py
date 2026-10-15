"""The site checks. Each rule is a row here and in rulebook/rules.csv (a test keeps the two in step),
and a problem found on many pages is one finding with every page listed, not one finding per page.
"""
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from .crawl import AD_PARAMS, AD_TEST_VALUE, AI_BOTS, Crawl, Page, dropped_ad_params, normalize
from .crux import METRICS as CRUX_METRICS
from .crux import FieldData
from .lab.lhr import Speed
from .net import Response
from .page import PageInfo, read
from .render import Rendered
from .tags import VENDORS, consent_mode_on, consent_mode_ping, consent_platform_of, in_source, known_host, vendor_of

TITLE_MAX_CHARS = 60         # longer titles are usually cut off in search results
REDIRECT_CHAIN_HOPS = 2      # this many redirects in a row is a chain
THIN_TEXT_CHARS = 200        # less visible text than this in the HTML: the content needs JavaScript
LCP_GOOD_MS = 2500           # Core Web Vitals "good" and "poor" lines, measured here in a lab
LCP_POOR_MS = 4000
CLS_GOOD = 0.1
CLS_POOR = 0.25
TBT_GOOD_MS = 200            # Lighthouse's lines for Total Blocking Time, the lab stand-in for INP
TBT_POOR_MS = 600
NEAR_LINE = 1.2              # a page measured once is flagged only above the poor line or this far over the good one
LHR_METRICS = {"largest-contentful-paint": "lcp", "cumulative-layout-shift": "cls", "total-blocking-time": "tbt"}
UNVERIFIABLE = (401, 403, 429, 999)  # an external site refusing a bot, not a broken link
SECURITY_HEADERS = ("strict-transport-security", "content-security-policy", "x-content-type-options",
                    "referrer-policy")
# Google's required properties for a rich result, per type: each group needs at least one of its names
REQUIRED: dict[str, tuple[tuple[str, ...], ...]] = {
    "Product": (("name",), ("offers", "review", "aggregateRating")),
    "BreadcrumbList": (("itemListElement",),),
    "FAQPage": (("mainEntity",),),
    "Event": (("name",), ("startDate",), ("location",)),
    "LocalBusiness": (("name",), ("address",)),
    "Recipe": (("name",), ("image",)),
    "JobPosting": (("title",), ("description",), ("datePosted",), ("hiringOrganization",)),
    "Review": (("author",), ("itemReviewed",)),
    "VideoObject": (("name",), ("thumbnailUrl",), ("uploadDate",)),
    "Course": (("name",), ("description",)),
    "Dataset": (("name",), ("description",)),
    "SoftwareApplication": (("name",), ("offers",), ("aggregateRating", "review")),
    "Movie": (("name",), ("image",)),
    "QAPage": (("mainEntity",),),
    "ProfilePage": (("mainEntity",),),
    "DiscussionForumPosting": (("author",), ("datePublished",), ("text", "image", "video")),
    "ClaimReview": (("claimReviewed",), ("reviewRating",), ("url",)),
    "EmployerAggregateRating": (("itemReviewed",), ("ratingValue",)),
}
# rules that judge a whole site, which `--single` (one page) can't: comparisons across pages, the sitemap, how the
# site answers a missing page, and other sites' links, which it doesn't check
WHOLE_SITE = frozenset({"site-title-duplicate", "site-description-duplicate", "site-sitemap-missing",
                        "site-sitemap-bad-url", "site-soft-404", "site-broken-external", "site-external-unverified"})
SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1, "info": 0}
AXE_SEVERITY = {"critical": "high", "serious": "high", "moderate": "medium", "minor": "low"}


@dataclass(frozen=True)
class Rule:
    category: str
    severity: str
    title: str
    unit: str   # what the count counts
    fix: str
    effort: str = "low"   # the work to fix it: low (a setting or a line), medium, high (a project)


R = Rule
RULES: dict[str, Rule] = {
    # on-page SEO (AUD-02)
    "site-title-missing": R("seo", "medium", "Pages with no title", "pages",
                            "Give every page its own `<title>`; Google often uses it as the link in search results."),
    "site-title-duplicate": R("seo", "low", "Pages that share their title with another page", "pages",
                              "Give each page its own title, so search results can tell them apart."),
    "site-title-long": R("seo", "low", f"Titles longer than {TITLE_MAX_CHARS} characters", "pages",
                         "Put the words that matter first: search results usually cut long titles off."),
    "site-description-missing": R("seo", "low", "Pages with no meta description", "pages",
                                  "Write a sentence or two; Google sometimes shows it under the link.", "medium"),
    "site-description-duplicate": R("seo", "low", "Pages that share their meta description", "pages",
                                    "Describe each page in its own words, or leave it out and let Google choose."),
    "site-h1-missing": R("seo", "low", "Pages with no main heading (`<h1>`)", "pages",
                         "Give each page one visible main heading that matches its topic."),
    "site-img-alt-missing": R("seo", "medium", "Pages with images that have no alt text", "pages",
                              "Add an `alt` to every image: describe it, or use `alt=\"\"` if it's decoration. "
                              "Screen readers and search engines read it.", "medium"),
    "site-lang-missing": R("seo", "low", "Pages with no language set", "pages",
                           "Set it on the page, e.g. `<html lang=\"en\">`; screen readers and translation use it."),
    "site-viewport-missing": R("seo", "medium", "Pages with no mobile viewport", "pages",
                               "Add `<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">` "
                               "so phones don't show a shrunken desktop page."),
    "site-meta-refresh": R("seo", "low", "Pages that redirect with a meta refresh", "pages",
                           "Use a server redirect instead; search engines and screen readers handle it better."),
    "site-redirect-chain": R("seo", "low", f"URLs that redirect {REDIRECT_CHAIN_HOPS} or more times in a row", "pages",
                             "Point the first URL straight at the final one."),
    "site-redirect-linked": R("seo", "low", "Internal links that point at a redirect", "links",
                              "Link to the final URL, so visitors and crawlers skip the extra hop."),
    # links (AUD-03)
    "site-broken-internal": R("links", "high", "Broken internal links", "links",
                              "Fix or remove links to pages that don't exist: each one is a dead end."),
    "site-broken-external": R("links", "medium", "Broken links to other sites", "links",
                              "Update or remove them."),
    "site-external-unverified": R("links", "info", "Links to other sites that refuse automated checks", "links",
                                  "Nothing to fix unless one looks wrong: these sites block bots, so check by hand."),
    "site-crawl-error": R("links", "medium", "Pages that couldn't be fetched", "pages",
                          "Check that they load: slow or failing pages lose visitors and crawlers."),
    "site-soft-404": R("links", "medium", "Missing pages that answer `200 OK`", "pages",
                       "Answer a page that doesn't exist with a real `404`, or search engines may index the "
                       "error page.", "medium"),
    # indexing (AUD-04)
    "site-home-hidden": R("indexing", "high", "The home page is hidden from search engines", "pages",
                          "Remove the noindex, or the robots.txt rule that blocks it, unless the site is meant "
                          "to be hidden."),
    "site-robots-unreachable": R("indexing", "high", "robots.txt answers with a server error, or not at all", "files",
                                 "Make it answer normally (or with `404` if you don't need one): while it fails, "
                                 "Google stops crawling the site."),
    "site-robots-missing": R("indexing", "low", "No robots.txt", "files",
                             "Optional: add one, if only to point crawlers at your sitemap."),
    "site-sitemap-missing": R("indexing", "low", "No readable XML sitemap", "files",
                              "Publish one at `/sitemap.xml`, or list it in robots.txt, so search engines find "
                              "every page."),
    "site-sitemap-bad-url": R("indexing", "medium", "Sitemap URLs that aren't indexable pages", "pages",
                              "List only final pages that load and may be indexed: no redirects, errors, noindex pages "
                              "or pages robots.txt blocks."),
    "site-noindex": R("indexing", "low", "Pages that ask search engines not to index them", "pages",
                      "Check each one is meant to stay out of search results."),
    "site-canonical-multiple": R("indexing", "medium", "Pages with more than one canonical", "pages",
                                 "Keep a single `rel=canonical`; with several, Google ignores them."),
    "site-canonical-conflict": R("indexing", "medium", "Canonicals that point at a page that can't be indexed", "pages",
                                 "Point the canonical at the final, indexable version of the page."),
    # structured data (AUD-05)
    "site-jsonld-invalid": R("structured-data", "medium", "Pages with JSON-LD that isn't valid JSON", "pages",
                             "Fix the syntax: search engines skip a block they can't parse."),
    "site-jsonld-incomplete": R("structured-data", "medium", "Structured data missing a property Google requires",
                                "pages", "Add the property named next to each page; without it the item can't get "
                                         "a rich result.", "medium"),
    "site-structured-data-none": R("structured-data", "low", "The home page has no structured data", "pages",
                                   "Describe the business with Organization or LocalBusiness markup in JSON-LD.",
                                   "medium"),
    "site-open-graph-missing": R("structured-data", "low", "Pages with no Open Graph title or image", "pages",
                                 "Add `og:title` and `og:image`, so a link shared on social media shows a preview."),
    # HTTPS and security headers (AUD-12)
    "site-no-https": R("security", "high", "The site is served over plain HTTP", "pages",
                       "Serve every page over HTTPS; browsers mark plain HTTP pages \"Not secure\".", "medium"),
    "site-http-not-redirected": R("security", "medium", "The http:// address doesn't move to https://", "pages",
                                  "Redirect plain HTTP to HTTPS with a permanent redirect."),
    "site-mixed-content": R("security", "medium", "HTTPS pages that load files over plain HTTP", "pages",
                            "Load every image, script and stylesheet over HTTPS; browsers block or flag the rest.",
                            "medium"),
    "site-security-headers": R("security", "low", "Security headers missing on the home page", "headers",
                               "Send them from the server or CDN; each closes a common kind of attack.", "medium"),
    # AI crawlers (AUD-32)
    "site-ai-crawlers-blocked": R("ai", "info", "AI crawlers that robots.txt blocks", "crawlers",
                                  "Nothing to fix if it's intended. A blocked assistant can't read or cite the site."),
    "site-js-only-content": R("ai", "medium", "Pages with almost no text until JavaScript runs", "pages",
                              "Send the main content in the HTML: crawlers that don't run JavaScript, many AI "
                              "crawlers among them, see an empty page.", "high"),
    "site-js-only-links": R("ai", "low", "Links that appear only after JavaScript runs", "links",
                            "Put important links in the HTML as `<a href>`: crawlers that don't run JavaScript "
                            "can't follow the others.", "medium"),
    # tracking and consent (AUD-09, AUD-10, AUD-11, AUD-13)
    "site-no-analytics": R("tracking", "medium", "No analytics tag found", "pages",
                           "Install analytics (for example GA4), or check it isn't loaded in a way this scan "
                           "can't see."),
    "site-tag-no-hit": R("tracking", "medium", "Tags that loaded but sent nothing during the scan", "tags",
                         "Open the page in your own browser and watch the network tab for the tag's requests. "
                         "Common causes: a consent category that stays off after accepting, a broken ID or "
                         "trigger, or a tag (Meta's, for one) that ignores automated browsers."),
    "site-tag-before-consent": R("tracking", "high", "Tags that send data before the visitor consents", "tags",
                                 "Hold them until consent, or use Consent Mode's cookieless pings, wherever privacy "
                                 "law (such as the GDPR) requires consent.", "medium"),
    "site-no-consent-banner": R("tracking", "medium", "Tags send data and no consent banner was recognised", "tags",
                                "If you have visitors where consent is required (the EU, the UK and others), add a "
                                "banner. If you have one, pass its accept button with `--consent-selector`.", "medium"),
    "site-consent-not-clicked": R("tracking", "info", "A consent banner was found but couldn't be accepted", "pages",
                                  "These results are the before-consent state only. Pass the accept button's CSS "
                                  "selector with `--consent-selector`."),
    "site-consent-mode-missing": R("tracking", "low", "Google tags run with no Consent Mode default", "pages",
                                   "Set a default (`gtag('consent', 'default', ...)`) before the tags load, so Google "
                                   "can model the conversions of visitors who decline."),
    "site-ad-params-dropped": R("tracking", "high", "Ad click IDs that a server redirect drops", "pages",
                                "Make the redirect keep the query string, or use the page it ends on as the ad's "
                                "final URL. Without the click ID, the ad platform can't tie a sale or lead to the "
                                "click that brought it."),
    "site-unknown-third-party": R("tracking", "info", "Third-party hosts this scan doesn't recognise", "hosts",
                                  "Check you know what each one is: any of them could be a tracker."),
    "site-ad-params-dropped-js": R("tracking", "medium", "Ad click IDs that the page's scripts take out of the "
                                   "address", "pages",
                                   "Find the script that rewrites the address (a router, a consent or cookie script) "
                                   "and make it keep the query string. A tag that reads the address after it (one "
                                   "held until consent, or loaded late) gets no click ID, so the ad platform can't tie "
                                   "a sale or lead to the click."),
    "site-js-errors": R("tracking", "medium", "Pages with JavaScript errors", "pages",
                        "Open the page with the browser's console showing and fix each error: an error stops the "
                        "rest of its script, which can be a tag or the code that sends a conversion.", "medium"),
    # accessibility (AUD-08): one finding per axe rule, titled with axe's own words
    "site-a11y": R("accessibility", "medium", "Accessibility problem", "pages",
                   "See the axe rule's page for how to fix it; automated checks find only some problems.", "medium"),
    # performance (AUD-06, AUD-07): lab measurements on a simulated phone, and real visitors' from Chrome
    "site-lcp-slow": R("performance", "medium", "Slow Largest Contentful Paint (lab)", "pages",
                       "Make the biggest image or text block load sooner: compress it, preload it, cut "
                       "render-blocking scripts.", "high"),
    "site-cls-high": R("performance", "medium", "Layout shifts while loading (lab)", "pages",
                       "Reserve space for images, ads and embeds, so content doesn't jump.", "medium"),
    "site-consent-banner-shift": R("performance", "medium", "The consent banner moves the page as it appears", "pages",
                                   "Show the banner over the page (fixed to the bottom or as a dialog), or reserve "
                                   "its space from the start, so the content doesn't jump while the visitor reads.",
                                   "medium"),
    "site-tbt-high": R("performance", "medium", "Main thread blocked while loading (lab)", "pages",
                       "Ship less JavaScript, split long tasks, and defer what isn't needed at load.", "high"),
    "site-field-lcp-slow": R("performance", "medium", "Real visitors wait for the main content", "sites",
                             "Chrome's field data says the biggest element loads slowly for real phone visitors: "
                             "compress and preload it, and cut render-blocking files.", "high"),
    "site-field-inp-slow": R("performance", "medium", "Real visitors' taps and clicks respond slowly", "sites",
                             "Chrome's field data says the page is slow to react to input: ship less JavaScript "
                             "and break up long tasks.", "high"),
    "site-field-cls-high": R("performance", "medium", "Real visitors see the layout jump", "sites",
                             "Chrome's field data says content shifts while visitors read: reserve space for "
                             "images, ads and embeds.", "medium"),
    # the crawl itself
    "site-bot-blocked": R("crawl", "high", "Bot protection blocked the scan", "pages",
                          "Allow the `OpenPPC-SiteAudit` user agent in your bot protection and run again. "
                          "Nothing else was checked."),
}
CATEGORIES = {"crawl": "The crawl", "seo": "On-page SEO", "links": "Links", "indexing": "Indexing",
              "structured-data": "Structured data", "security": "HTTPS and security", "ai": "AI crawlers",
              "tracking": "Tracking and consent", "accessibility": "Accessibility (automated checks only)",
              "performance": "Performance"}
# who usually makes the fix, for the app's summary: by area, then the rules whose fix lives elsewhere
WHO = {"crawl": "hosting", "seo": "developer", "links": "developer", "indexing": "developer",
       "structured-data": "developer", "security": "hosting", "ai": "developer", "tracking": "tag manager",
       "accessibility": "developer", "performance": "developer"}
WHO_RULE = {"site-mixed-content": "developer", "site-crawl-error": "hosting", "site-robots-unreachable": "hosting",
            "site-ad-params-dropped": "developer or hosting", "site-ad-params-dropped-js": "developer",
            "site-js-errors": "developer", "site-consent-banner-shift": "tag manager"}


@dataclass
class Finding:
    rule: str
    items: list[str]                                     # URLs, or header, crawler, tag or host names
    notes: dict[str, str] = field(default_factory=dict)  # detail printed after an item
    key: str = ""        # the id when one rule makes several findings: "site-a11y:image-alt"
    title: str = ""      # overrides the rule's title
    severity: str = ""   # overrides the rule's severity
    spec: Rule | None = None  # a rule pack's rule, which isn't in RULES

    @property
    def id(self) -> str:
        return self.key or self.rule

    @property
    def about(self) -> Rule:
        return self.spec or RULES[self.rule]

    @property
    def level(self) -> str:
        return self.severity or self.about.severity

    @property
    def who(self) -> str:
        return WHO_RULE.get(self.rule) or WHO.get(self.about.category, "developer")


def code(text: str) -> str:
    """Text from the site or the network (an error, a selector) as a code span: its digits are not claims."""
    return "`" + text.replace("`", "'") + "`"


def noindex(p: Page) -> bool:
    return bool(p.info and p.info.noindex) or "noindex" in p.resp.headers.get("x-robots-tag", "").lower()


def home(c: Crawl) -> Page:
    """The home page as read: the root, or where the start URL redirects to (/ -> /en/)."""
    start = c.pages.get(c.start) or Page(c.start, 0, Response(c.start, c.start, -1))  # robots.txt kept us out
    for url in (c.origin + "/", start.resp.final_url):
        p = c.pages.get(normalize(url))
        if p and p.info:
            return p
    return start


def _duplicates(values: dict[str, str]) -> list[str]:
    groups: dict[str, list[str]] = defaultdict(list)
    for url, value in values.items():
        if value:
            groups[value].append(url)
    return [u for urls in groups.values() if len(urls) > 1 for u in urls]


def _jsonld_items(data: Any) -> list[dict[str, Any]]:
    items = data if isinstance(data, list) else [data]
    out = []
    for item in items:
        if isinstance(item, dict):
            out.append(item)
            out += [g for g in item.get("@graph", []) if isinstance(g, dict)]
    return out


def _types(item: dict[str, Any]) -> list[str]:
    t = item.get("@type", [])
    return [str(x).rsplit("/", 1)[-1].rsplit(":", 1)[-1] for x in (t if isinstance(t, list) else [t])]


def _missing(kind: str, props: Any) -> str:
    groups = [" or ".join(f"`{k}`" for k in group) for group in REQUIRED.get(kind, ())
              if not any(k in props for k in group)]
    return f"`{kind}` needs {', '.join(groups)}" if groups else ""


def _structured(info: dict[str, PageInfo]) -> tuple[list[str], dict[str, str]]:
    invalid: list[str] = []
    incomplete: dict[str, str] = {}
    for url, i in info.items():
        found: list[tuple[str, Any]] = list(i.items)  # Microdata
        for block in i.jsonld:
            try:
                data = json.loads(block)
            except ValueError:
                invalid.append(url)
                continue
            found += [(t, item) for item in _jsonld_items(data) for t in _types(item)]
        for kind, props in found:
            note = _missing(kind, props)
            if note:
                incomplete.setdefault(url, note)
    return invalid, incomplete


def tracking(c: Crawl, r: Rendered | None) -> dict[str, dict[str, bool]]:
    """Per vendor: in the page source, its script loaded, a hit before consent (a real one, or a
    Consent Mode ping), a hit after consent."""
    out: dict[str, dict[str, bool]] = {}

    def state(vid: str) -> dict[str, bool]:
        return out.setdefault(vid, dict.fromkeys(("source", "loaded", "before", "ping", "after"), False))

    source = home(c).info
    for vid in in_source(source) if source else ():
        state(vid)["source"] = True
    for o in r.pages if r else []:
        for phase, urls in (("before", o.before), ("after", o.after)):
            for url in urls:
                match = vendor_of(url)
                if not match:
                    continue
                vid, what = match
                if what == "load":
                    state(vid)["loaded"] = True
                elif phase == "before":
                    state(vid)["ping" if consent_mode_ping(url) else "before"] = True
                else:
                    state(vid)["after"] = True
    return out


def events(r: Rendered | None) -> dict[str, list[str]]:
    """Per tag, the distinct events its hits sent on the rendered pages."""
    out: dict[str, list[str]] = {}
    for o in r.pages if r else []:
        for vid, names in o.events.items():
            seen = out.setdefault(vid, [])
            seen += [n for n in names if n not in seen]
    return out


def _tracking_findings(c: Crawl, r: Rendered | None, add: Any) -> None:
    tags = tracking(c, r)
    analytics = [v for v, s in tags.items() if VENDORS[v]["kind"] == "analytics"]
    # without a browser, analytics inside a tag manager is unseen, and a home page not read says nothing
    managed = any(VENDORS[v]["kind"] == "tag manager" for v in tags)
    if not analytics and (r or (home(c).info and not managed)):
        add("site-no-analytics", [home(c).url])
    if not r:
        return
    banner = any(o.consent or o.tcf for o in r.pages)
    fired = [v for v, s in tags.items() if VENDORS[v]["kind"] in ("ads", "analytics") and s["before"]]
    add("site-tag-no-hit", [VENDORS[v]["name"] for v, s in tags.items()
                            if VENDORS[v]["hit"] and (s["source"] or s["loaded"])
                            and not (s["before"] or s["ping"] or s["after"])])
    if banner:
        add("site-tag-before-consent", [VENDORS[v]["name"] for v in fired])
    else:
        add("site-no-consent-banner", [VENDORS[v]["name"] for v in fired])
    add("site-consent-not-clicked", [o.url for o in r.pages if o.consent and not o.accepted])
    google = {"gtm", "ga4", "google-ads"} & set(tags)
    if google and banner and not any(o.consent_mode or any(map(consent_mode_on, o.before + o.after))
                                     for o in r.pages):
        add("site-consent-mode-missing", [home(c).url])
    base = host_base(c.origin)
    seen = {u: (urlsplit(u).hostname or "").lower() for o in r.pages for u in o.before + o.after}
    recognised = {host for u, host in seen.items() if vendor_of(u) or consent_platform_of(u)}
    unknown = sorted({host for host in seen.values() if host and not same_site(host, base)
                      and host not in recognised and not known_host(host)})
    add("site-unknown-third-party", unknown)
    if lost := js_dropped_ad_params(c, r):
        names = ", ".join(f"`{p}`" for p in lost)
        add("site-ad-params-dropped-js", [c.start],
            {c.start: f"loses {names} once its scripts run: the address became {code(r.ad_params.final_url)}"
             if r.ad_params else ""})
    shifted = [o.url for o in r.pages if o.banner_shift is not None and o.banner_shift >= CLS_GOOD]
    add("site-consent-banner-shift", shifted)


def js_dropped_ad_params(c: Crawl, r: Rendered | None) -> list[str]:
    """The AD_PARAMS the server's redirects kept and the page's scripts then took out of the address."""
    seen = r.ad_params if r else None
    if not seen or seen.error or not seen.final_url:
        return []
    kept = dict(parse_qsl(urlsplit(seen.final_url).query, keep_blank_values=True))
    gone = set(dropped_ad_params(c.ad_params))
    return [p for p in AD_PARAMS if p not in gone and kept.get(p) != AD_TEST_VALUE]


def host_base(origin: str) -> str:
    host = (urlsplit(origin).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def same_site(host: str, base: str) -> bool:
    return host == base or host.endswith("." + base)


def _rendered_findings(r: Rendered, add: Any) -> None:
    broken = [o for o in r.pages if o.errors]
    add("site-js-errors", [o.url for o in broken], {o.url: code(o.errors[0]) for o in broken})
    by_rule: dict[str, dict[str, Any]] = {}
    for o in r.pages:
        for v in o.axe:
            entry = by_rule.setdefault(v["id"], {"v": v, "pages": [], "notes": {}})
            entry["pages"].append(o.url)
            entry["notes"][o.url] = code(v["targets"][0]) if v["targets"] else ""
    for axe_id, entry in sorted(by_rule.items(), key=lambda kv: -SEVERITY_RANK[AXE_SEVERITY.get(
            kv[1]["v"]["impact"] or "minor", "low")]):
        v = entry["v"]
        criteria = ", ".join(f"`{x}`" for x in v.get("criteria", []))
        add("site-a11y", entry["pages"], entry["notes"], key=f"site-a11y:{axe_id}",
            title=f"`{axe_id}`: {v['help']}" + (f" (WCAG {criteria})" if criteria else ""),
            severity=AXE_SEVERITY.get(v["impact"] or "minor", "low"))


def lab_values(r: Rendered | None, speed: list[Speed]) -> dict[str, tuple[dict[str, float | None], bool]]:
    """Each page's lab LCP, CLS and TBT on a phone: Lighthouse's (PageSpeed Insights') where it measured the page,
    else this computer's representative load; and whether that was a single load."""
    out: dict[str, tuple[dict[str, float | None], bool]] = {}
    for s in speed:
        if s.device == "mobile" and s.metrics:
            got = {m.id: m.value for m in s.metrics}
            out[s.url] = ({key: got.get(audit) for audit, key in LHR_METRICS.items()}, False)
    for v in r.vitals if r else []:
        if v.device == "mobile" and v.runs:
            out.setdefault(v.url, (v.shown, len(v.runs) == 1))
    return out


LAB_LINES = (("site-lcp-slow", "lcp", LCP_GOOD_MS, LCP_POOR_MS), ("site-cls-high", "cls", CLS_GOOD, CLS_POOR),
             ("site-tbt-high", "tbt", TBT_GOOD_MS, TBT_POOR_MS))


def near_line(value: float, good: float, bad: float) -> bool:
    """Too close to the good line for one load to call: over it, but neither poor nor NEAR_LINE times it."""
    return good < value <= bad and value <= good * NEAR_LINE


def _lab_findings(values: dict[str, tuple[dict[str, float | None], bool]], add: Any) -> None:
    slow: dict[str, list[str]] = defaultdict(list)
    poor: dict[str, bool] = defaultdict(bool)
    for url, (m, once) in values.items():
        for rule, key, good, bad in LAB_LINES:
            value = m.get(key)
            if value is not None and value > good and not (once and near_line(value, good, bad)):
                slow[rule].append(url)
                poor[rule] |= value > bad
    for rule, urls in slow.items():
        add(rule, urls, severity="high" if poor[rule] else "")


def js_only_links(c: Crawl, r: Rendered) -> dict[str, str]:
    """Links on the site that a rendered page has and its HTML doesn't: link -> the page it was on."""
    host = urlsplit(c.origin).netloc
    out: dict[str, str] = {}
    for o in r.pages:
        p = c.pages.get(o.url)
        if not (p and p.info):
            continue
        in_html = set()
        for link in p.info.links:
            try:
                in_html.add(normalize(link))
            except ValueError:
                continue
        for link in o.links:
            try:
                url = normalize(link)
            except ValueError:
                continue
            if urlsplit(url).netloc == host and url not in in_html and url != o.url:
                out.setdefault(url, o.url)
    return out


def _field_findings(field_data: list[FieldData], add: Any) -> None:
    site = next((f for f in field_data if f.origin and f.p75 and f.device == "phone"), None)
    if not site:
        return
    for rule, short in (("site-field-lcp-slow", "lcp"), ("site-field-inp-slow", "inp"),
                        ("site-field-cls-high", "cls")):
        good, bad = next(v[1:] for v in CRUX_METRICS.values() if v[0] == short)
        value = site.p75.get(short)
        if value is not None and value > good:
            add(rule, [site.target], {site.target: f"p75 {code(f'{value:g}')}"},
                severity="high" if value > bad else "")


def evaluate(c: Crawl, r: Rendered | None = None, field_data: list[FieldData] | None = None,
             speed: list[Speed] | None = None) -> list[Finding]:
    out: list[Finding] = []

    def add(rule: str, items: list[str], notes: dict[str, str] | None = None, key: str = "", title: str = "",
            severity: str = "") -> None:
        if items and not (c.single and rule in WHOLE_SITE):
            out.append(Finding(rule, list(dict.fromkeys(items)), notes or {}, key, title, severity))

    if c.blocked_by:
        add("site-bot-blocked", [c.start], {c.start: f"answered by {c.blocked_by}"})
        return out
    if c.start not in c.pages and c.start in c.robots_blocked:
        add("site-home-hidden", [c.start], {c.start: "robots.txt disallows it"})
        return out
    pages = c.html_pages()
    info = {p.url: p.info for p in pages if p.info}
    first = home(c)

    add("site-title-missing", [u for u, i in info.items() if not i.title])
    add("site-title-duplicate", _duplicates({u: i.title for u, i in info.items()}))
    add("site-title-long", [u for u, i in info.items() if len(i.title) > TITLE_MAX_CHARS])
    add("site-description-missing", [u for u, i in info.items() if not i.description])
    add("site-description-duplicate", _duplicates({u: i.description for u, i in info.items()}))
    add("site-h1-missing", [u for u, i in info.items() if not i.h1])
    add("site-img-alt-missing", [u for u, i in info.items() if i.images_without_alt])
    add("site-lang-missing", [u for u, i in info.items() if not i.lang])
    add("site-viewport-missing", [u for u, i in info.items() if not i.viewport])
    add("site-meta-refresh", [u for u, i in info.items() if i.refresh])
    add("site-redirect-chain", [p.url for p in c.pages.values() if len(p.resp.hops) >= REDIRECT_CHAIN_HOPS])
    add("site-redirect-linked", [p.url for p in c.pages.values() if p.resp.hops and p.url in c.referrer])

    add("site-broken-internal", [p.url for p in c.pages.values() if p.status >= 400 and not p.blocked_by
                                 and (p.url in c.referrer or p.url == c.start)])  # sitemap-only URLs: below
    errors = {p.url: "cut off at the size limit" if p.resp.truncated else
              code(p.resp.error) if p.resp.error else f"answered by {p.blocked_by}"
              for p in c.pages.values() if p.status == 0 or p.blocked_by or p.resp.truncated}
    add("site-crawl-error", list(errors), errors)
    broken = {u: code(x.error or str(x.status)) for u, x in c.external.items()
              if not x.refused and x.status != -1 and x.status not in UNVERIFIABLE
              and (x.status == 0 or x.status in (404, 410) or x.status >= 500)}
    add("site-broken-external", list(broken), broken)
    add("site-external-unverified", [u for u, x in c.external.items() if x.status in UNVERIFIABLE])
    if c.probe and c.probe.status == 200:
        probe_title = read(c.probe.body.decode("utf-8", "replace"), c.probe.final_url).title
        add("site-soft-404", [c.probe.url] + [u for u, i in info.items() if probe_title and i.title == probe_title])

    if noindex(first) or not c.allowed(first.url):
        add("site-home-hidden", [first.url])
    if c.robots and c.robots_failed:
        add("site-robots-unreachable", [c.robots.url], {c.robots.url: code(c.robots.error or str(c.robots.status))})
    elif c.robots and c.robots.status >= 400:
        add("site-robots-missing", [c.robots.url])
    if not c.sitemap_files and not c.robots_failed:  # sitemaps aren't read while robots.txt fails
        add("site-sitemap-missing", [c.origin + "/sitemap.xml"])
    bad: dict[str, str] = {}
    for u in sorted(c.sitemap_urls):
        p = c.pages.get(u)
        if u in c.robots_blocked:
            bad[u] = "blocked by robots.txt"
        elif p and p.resp.hops:
            bad[u] = "redirects"
        elif p and p.status != 200:
            bad[u] = f"answers `{p.status}`" if p.status else "doesn't load"
        elif p and noindex(p):
            bad[u] = "noindex"
    add("site-sitemap-bad-url", list(bad), bad)
    add("site-noindex", [p.url for p in pages if noindex(p) and p.url != first.url])
    add("site-canonical-multiple", [u for u, i in info.items() if len(set(i.canonicals)) > 1])
    conflicts: dict[str, str] = {}
    for u, i in info.items():
        try:
            target = normalize(i.canonicals[0]) if i.canonicals else u
        except ValueError:
            continue
        t = c.pages.get(target)
        if target == u:
            continue
        if target in c.robots_blocked:
            conflicts[u] = "its canonical is blocked by robots.txt"
        elif t and (t.resp.hops or t.status != 200):
            conflicts[u] = "its canonical redirects or doesn't load"
        elif t and noindex(t):
            conflicts[u] = "its canonical is noindex"
    add("site-canonical-conflict", list(conflicts), conflicts)

    invalid, incomplete = _structured(info)
    add("site-jsonld-invalid", invalid)
    add("site-jsonld-incomplete", list(incomplete), incomplete)
    if first.info and not first.info.jsonld and not first.info.microdata:
        add("site-structured-data-none", [first.url])
    add("site-open-graph-missing", [u for u, i in info.items() if not {"og:title", "og:image"} <= set(i.og)])

    if c.origin.startswith("http:"):
        add("site-no-https", [c.origin + "/"])
    elif c.plain_http and c.plain_http.status and not c.plain_http.final_url.startswith("https://"):
        add("site-http-not-redirected", [c.plain_http.url])
    dropped = dropped_ad_params(c.ad_params)
    if c.ad_params and dropped:
        lost = ", ".join(f"`{p}`" for p in dropped)
        add("site-ad-params-dropped", [c.start], {c.start: f"loses {lost} on the way to "
                                                           f"{code(c.ad_params.final_url)} (server redirects only)"})
    mixed = {u: f"loads `{next(s for s in i.subresources if s.startswith('http://'))}`" for u, i in info.items()
             if u.startswith("https://") and any(s.startswith("http://") for s in i.subresources)}
    add("site-mixed-content", list(mixed), mixed)
    if first.status == 200:
        h = first.resp.headers
        missing = [n for n in SECURITY_HEADERS if n not in h and (n != "strict-transport-security"
                                                                   or first.url.startswith("https://"))]
        if "x-frame-options" not in h and "frame-ancestors" not in h.get("content-security-policy", ""):
            missing.append("x-frame-options")
        add("site-security-headers", [f"`{n}`" for n in missing])

    if c.rules:
        add("site-ai-crawlers-blocked", [f"`{b}`" for b in AI_BOTS if not c.allowed(c.origin + "/", b)])
    add("site-js-only-content", [u for u, i in info.items()
                                 if i.text_chars < THIN_TEXT_CHARS and (i.scripts or i.inline.strip())])
    _tracking_findings(c, r, add)
    if r:
        hidden = js_only_links(c, r)
        add("site-js-only-links", list(hidden), {u: f"on `{page}`" for u, page in hidden.items()})
        _rendered_findings(r, add)
    _lab_findings(lab_values(r, speed or []), add)
    _field_findings(field_data or [], add)
    return out

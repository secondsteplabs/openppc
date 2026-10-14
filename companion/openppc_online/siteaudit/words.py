"""Plain words for people who aren't web developers: what each speed measure means for someone who clicked an ad,
the commonest Lighthouse audits in a line each, and a glossary. No numbers here: a report's numbers are traced, and
these sentences are the same in every report."""

# what a speed measure means, in the order PageSpeed Insights lists them
MEASURES = {
    "fcp": ("First Contentful Paint", "when the first text or image appears. Until then, someone who clicked your ad "
                                      "looks at a blank screen, and some leave."),
    "lcp": ("Largest Contentful Paint", "when the main content (usually the biggest image or heading) has shown: the "
                                        "moment the visitor sees what the ad promised."),
    "tbt": ("Total Blocking Time", "how long the page is too busy running scripts to answer a tap while it loads. "
                                   "Tags, chat widgets and sliders are common causes. A test load can't tap, so this "
                                   "stands in for Interaction to Next Paint."),
    "cls": ("Cumulative Layout Shift", "how much the page jumps around as it loads. A jump can make a visitor tap the "
                                       "wrong thing or lose their place."),
    "si": ("Speed Index", "how quickly the page fills in as a whole. A page that shows content bit by bit feels faster "
                          "than one that stays blank, then appears."),
    "inp": ("Interaction to Next Paint", "how quickly the page answers taps and clicks over a real visit. A slow "
                                         "answer to a form or a buy button makes visitors try again or give up."),
    "ttfb": ("Time to First Byte", "how long the server takes to start answering. Everything else waits for it; slow "
                                   "hosting and redirects add to it."),
}
WHY = ("A visitor from an ad has already cost you the click, so a slow or jumpy landing page wastes it, and Google Ads "
       "counts landing page experience in Quality Score.")

# the Lighthouse audits that most often fail on landing pages, by id, in a line each
AUDITS = {
    "render-blocking-insight": "files the browser must fetch before it can show anything; they keep the screen blank.",
    "lcp-discovery-insight": "the main image is found late, or loaded lazily, so the biggest thing on the page shows "
                             "last.",
    "lcp-breakdown-insight": "where the wait for the main content goes: the server, finding the file, downloading it, "
                             "or drawing it.",
    "image-delivery-insight": "images bigger than they're shown, or in older formats; smaller files arrive sooner on "
                              "a phone.",
    "document-latency-insight": "the page itself is slow to arrive: redirects, a slow server, or no compression.",
    "cache-insight": "files the browser has to download again on every visit, because the server doesn't let it keep "
                     "them.",
    "third-parties-insight": "scripts from other companies (tags, chat, video) and how much of the load they take.",
    "unused-javascript": "script that downloads but isn't used on this page: waiting for nothing.",
    "network-dependency-tree-insight": "files that wait for other files, one after another, which a phone on a slow "
                                       "network feels most.",
    "cls-culprits-insight": "what makes the page jump: images without a size, late banners, fonts swapping.",
}

# terms a report may use, with the words that show it does
GLOSSARY = (
    ("Lighthouse", ("Lighthouse",), "Google's free tool that loads a page as a slow phone or a desktop would and "
                                    "scores its speed, accessibility, best practices and SEO."),
    ("PageSpeed Insights (PSI)", ("PageSpeed Insights", "PSI"), "Google's website (pagespeed.web.dev) that runs "
                                                               "Lighthouse on its own servers and adds real visitors' "
                                                               "data."),
    ("Speed score", ("speed score",), "Lighthouse's grade for how fast a page loads, from its five measures; green is "
                                      "good, orange average, red poor."),
    ("Lab and real visitors", ("lab", "Real visitors"), "a lab number comes from one test load; real visitors' numbers "
                                                         "come from Chrome users' actual visits. They often differ; "
                                                         "Google ranks on the real ones."),
    ("Chrome UX Report (CrUX)", ("Chrome UX Report", "CrUX"), "Google's public data on how real Chrome users' visits "
                                                              "to a site went, over the last four weeks."),
    ("p75", ("p75",), "the value three visits in four beat: the number Google uses for real visitors."),
    ("Core Web Vitals", ("Core Web Vitals",), "the three measures Google treats as the page experience: Largest "
                                              "Contentful Paint, Interaction to Next Paint and Cumulative Layout "
                                              "Shift."),
    ("Tag", ("tag", "Tag"), "a script from an analytics or ad platform (GA4, Google Ads, Meta) that reports visits "
                            "and conversions; a tag hit is one such report."),
    ("Consent banner and Consent Mode", ("consent", "Consent"), "the banner asks visitors whether they accept "
                                                                "tracking; Consent Mode tells Google's tags what they "
                                                                "chose."),
    ("Click ID", ("click ID", "Click ID", "gclid"), "the code an ad platform adds to the address when someone clicks "
                                                    "an ad (gclid for Google Ads, msclkid for Microsoft, fbclid for "
                                                    "Meta); it ties a sale back to the click."),
    ("robots.txt", ("robots.txt",), "a file that tells crawlers which pages they may visit."),
    ("Sitemap", ("sitemap",), "a file listing the site's pages, so search engines find them all."),
    ("Canonical", ("canonical",), "a tag that names the main version of a page that exists at several addresses."),
    ("noindex", ("noindex",), "a setting that asks search engines to leave a page out of their results."),
    ("WCAG and axe-core", ("WCAG", "axe-core"), "WCAG is the accessibility standard; axe-core is the free tool that "
                                                "checks a page against part of it automatically."),
)

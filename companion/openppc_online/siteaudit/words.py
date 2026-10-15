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
# beside every number the lab measures here (SITE_AUDIT_PARITY_PLAN.md, U6)
DIFFERS = ("Why these differ from PageSpeed Insights: PageSpeed loads the page on Google's servers and works out how a "
           "slow phone would do from one fast load; this lab loads it on this computer, slowed down as Chrome's "
           "developer tools slow it, so this computer's speed, its internet connection and its distance from the "
           "site's servers all count. Loads also differ from each other (ads, tags and servers vary), and real "
           "visitors, on every kind of phone, differ again. Compare numbers from the same source only.")

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

# who usually makes a fix (checks.WHO), as the app's summary names them to a client
WHO = {"developer": "your web developer", "hosting": "your hosting company",
       "tag manager": "whoever sets up your tracking tags (often your ad agency)",
       "developer or hosting": "your web developer or hosting company"}

# findings whose report wording is for a developer or the command line, as the app's summary puts them to a client
FINDINGS = {
    "site-lcp-slow": ("Speed: the main content shows slowly on a phone (test load)",
                      "Ask for the biggest image or heading to load sooner: smaller images, fewer scripts before it."),
    "site-tbt-high": ("Speed: the page is too busy running scripts to answer taps while it loads (test load)",
                      "Ask for fewer scripts at load: tags, chat widgets and sliders that aren't needed straight away "
                      "can wait."),
    "site-cls-high": ("Speed: the page jumps around as it loads (test load)",
                      "Ask for space to be kept for images, ads and banners, so nothing moves."),
    "site-no-consent-banner": ("Consent: tags send data and no consent banner was recognised",
                               "If you have visitors where consent is required (the EU, the UK and others), add a "
                               "banner. If you have one, check again with its accept button named in Consent banner "
                               "accept button."),
    "site-consent-mode-missing": ("Consent: Google's tags load before they're told what the visitor chose",
                                  "Ask for a Consent Mode default to be set before the tags load, so Google can model "
                                  "the conversions of visitors who decline."),
}

# the accessibility (axe-core) rules landing pages fail most, by id: what a visitor meets, and what to ask for
A11Y = {
    "color-contrast": ("some text is too faint against its background to read easily",
                       "Darken the text or lighten its background until it reads clearly."),
    "link-in-text-block": ("links in text look like the words around them",
                           "Underline links, or make them stand out by more than their colour."),
    "image-alt": ("images have no description for people who can't see them",
                  "Give each image a short text description (alt text); decorative ones get an empty one."),
    "role-img-alt": ("some pictures have no description for people who can't see them",
                     "Give each one a short text description."),
    "svg-img-alt": ("some icons and drawings have no description for people who can't see them",
                    "Give each one a short text description."),
    "input-image-alt": ("image buttons have no description, so a screen reader can't say what they do",
                        "Give each image button a short text description."),
    "link-name": ("some links have no words, so a screen reader can't say where they go",
                  "Give every link text, or a label, that says where it goes."),
    "button-name": ("some buttons have no words, so a screen reader can't say what they do",
                    "Give every button text, or a label, that says what it does."),
    "label": ("form fields have no label, so some visitors can't tell what to type",
              "Give every form field a visible label."),
    "select-name": ("drop-down lists have no label", "Give every drop-down list a visible label."),
    "frame-title": ("embedded content (videos, maps, chat) has no name for screen readers",
                    "Give each embedded frame a short title."),
    "html-has-lang": ("the page doesn't say what language it's in, so screen readers may read it wrongly",
                      "Set the page's language in its code."),
    "html-lang-valid": ("the page names a language that doesn't exist",
                        "Set the page's language to a real language code."),
    "document-title": ("the page has no title for the browser tab", "Give the page a title."),
    "meta-viewport": ("visitors can't zoom in on a phone", "Let visitors zoom: remove the setting that stops it."),
    "meta-refresh": ("the page reloads or moves on by itself after a while",
                     "Stop the automatic reload, or let visitors control it."),
    "list": ("lists are built in a way screen readers can't follow", "Build lists from list items only."),
    "listitem": ("list items sit outside a list, so screen readers can't follow them",
                 "Put each list item inside a list."),
    "heading-order": ("headings skip levels, which makes the page harder to scan with a screen reader",
                      "Use heading levels in order (a main heading, then subheadings)."),
    "empty-heading": ("some headings are empty", "Remove empty headings or give them words."),
    "page-has-heading-one": ("the page has no main heading", "Give the page one main heading."),
    "region": ("some content sits outside the page's marked areas, so screen reader users can skip past it",
               "Put all content inside the page's header, main, footer or navigation areas."),
    "landmark-one-main": ("the page doesn't mark its main content", "Mark the main content area."),
    "duplicate-id-aria": ("two parts of the page share a name that labels need to be unique",
                          "Give each labelled part its own name."),
    "aria-hidden-focus": ("hidden parts of the page can still be reached with the keyboard",
                          "Make hidden parts unreachable by keyboard too."),
    "nested-interactive": ("buttons or links sit inside other buttons or links, which confuses screen readers",
                           "Don't put one clickable thing inside another."),
    "scrollable-region-focusable": ("some scrolling boxes can't be scrolled with the keyboard",
                                    "Let keyboard users reach and scroll them."),
    "target-size": ("some buttons or links are too small to tap easily on a phone",
                    "Make tap targets bigger, or space them further apart."),
    "aria-allowed-attr": ("some parts carry screen reader settings that don't apply to them",
                          "Remove the settings that don't belong."),
    "aria-valid-attr-value": ("some screen reader settings have wrong values", "Correct the values."),
    "aria-required-children": ("some menus or lists are missing the parts screen readers expect",
                               "Add the missing parts, or remove the role that needs them."),
    "aria-required-parent": ("some parts sit outside the menu or list they belong to",
                             "Put them inside the right container."),
    "aria-prohibited-attr": ("some parts are labelled in a way screen readers ignore",
                             "Label them with visible text instead."),
    "aria-input-field-name": ("some custom form fields have no label, so some visitors can't tell what to type",
                              "Give every form field a label."),
    "aria-toggle-field-name": ("some switches and checkboxes have no label", "Give each one a label."),
    "aria-command-name": ("some custom buttons and links have no words, so a screen reader can't say what they do",
                          "Give each one text, or a label."),
    "aria-dialog-name": ("some pop-ups have no name for screen readers", "Give each pop-up a title."),
    "aria-progressbar-name": ("some progress bars have no name for screen readers", "Give each one a label."),
    "aria-tooltip-name": ("some tooltips have no words for screen readers", "Give each tooltip text."),
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
    ("OpenPPC lab score", ("OpenPPC lab score",), "Lighthouse's speed score formula applied to the test loads on "
                                                  "this computer. Uncalibrated means it hasn't yet been checked "
                                                  "against Lighthouse on the same computer; it never replaces "
                                                  "PageSpeed's score."),
    ("Benchmark index", ("benchmark index",), "Lighthouse's quick test of how fast this computer's processor is; a "
                                              "slow one makes test loads slower."),
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

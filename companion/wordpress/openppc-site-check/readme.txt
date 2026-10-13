=== OpenPPC Site Check ===
Contributors: openppc
Tags: site health, seo, tracking, consent, ads
Requires at least: 5.8
Tested up to: 7.1
Requires PHP: 7.4
Stable tag: 0.1.0
License: MIT
License URI: https://opensource.org/licenses/MIT

Five quick checks in Tools > Site Health for a site that runs ads: indexing, search basics, tags, consent banner, sitemap.

== Description ==

OpenPPC Site Check adds five checks to the Site Health screen WordPress already has:

* Search engines may index the site (Settings > Reading).
* The home page has the search basics: a title, a meta description, one h1, a canonical link, a viewport, a language, and no noindex.
* The home page's HTML loads an ad, analytics or tag manager tag (Google Analytics 4, Google Ads, Google Tag Manager, Meta Pixel, Microsoft UET, TikTok, LinkedIn and others).
* A page with tags has a consent banner (OneTrust, Cookiebot, Complianz, CookieYes, Borlabs and others, found in the HTML or among your active plugins).
* robots.txt names a sitemap.

It reads only your own site: WordPress requests its own home page and robots.txt, the way Site Health's loopback test does, and follows no redirect elsewhere. It sends nothing to any other address, stores nothing and adds no settings. The checks that read a page run after Site Health opens, so the screen doesn't wait for them.

These checks read the HTML. Whether each tag actually fires, with which events, before and after consent, shows only in a real browser. For that, run the free OpenPPC website check on your computer: `openppc-online site https://your-site.example --render`. Each check shows the exact command.

The tag list is the one the OpenPPC website check uses, and the same test cases keep the two in step.

== Installation ==

1. Upload the `openppc-site-check` folder to `wp-content/plugins/`, or upload the zip in Plugins > Add New > Upload Plugin.
2. Activate it.
3. Open Tools > Site Health.

== Frequently Asked Questions ==

= Does it slow my site down? =

No. It runs only when an administrator opens Site Health, and adds nothing to your pages.

= Does it send my data anywhere? =

No. Its only requests are to your own site.

== Changelog ==

= 0.1.0 =
* First release.

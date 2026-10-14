"""Websites for the site check's tests, served on 127.0.0.1 by the `serve` fixture."""
from openppc_online.siteaudit.net import Guard

PUBLIC = "93.184.215.14"   # a public address; the `public` fixture connects it to this computer
PSI_HOST = "pagespeedonline.googleapis.com"


def local():
    """A guard on which every name resolves to the test server's address, so another "site" is just another host
    name."""
    return Guard(allow_private=True, resolve=lambda host, port: ["127.0.0.1"])


def page(title, body="", head=""):
    return (f"<!doctype html><html lang='en'><head><title>{title}</title>"
            f"<meta name='description' content='{title} page'>"
            f"<meta name='viewport' content='width=device-width'>{head}</head>"
            f"<body><h1>{title}</h1>{body}<p>{'Plenty of words here. ' * 20}</p></body></html>")


def _qa_page(title, body, head=""):
    t = f"<title>{title}</title>" if title is not None else ""
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width'>{t}{head}</head><body>{body}</body></html>")


QA_GOOD = {
    "/": _qa_page("Acme Plumbing - 24/7 plumbers in Springfield",
                  "<h1>Acme Plumbing</h1><p>Emergency plumbing.</p><a href='/services'>Services</a> "
                  "<a href='/contact'>Contact</a>",
                  "<meta name='description' content='Acme Plumbing fixes leaks, drains and water heaters across "
                  "Springfield, day and night.'><link rel='canonical' href='/'>"),
    "/services": _qa_page("Plumbing services - Acme Plumbing", "<h1>Services</h1><a href='/'>Home</a>",
                          "<meta name='description' content='Drain cleaning, leak detection and water heater installs "
                          "from licensed Acme plumbers.'><link rel='canonical' href='/services'>"),
    "/contact": _qa_page("Contact Acme Plumbing", "<h1>Contact</h1><a href='/'>Home</a>",
                         "<meta name='description' content='Call Acme Plumbing any time, or book a visit online in "
                         "two minutes flat.'><link rel='canonical' href='/contact'>"),
}
QA_BAD = {
    "/": _qa_page("Home", "<h1>Welcome</h1><h1>Second h1</h1>"
                  "<a href='/about'>About</a> <a href='/missing-page'>Broken</a> <a href='/old'>Old</a> "
                  "<a href='/noindex'>Hidden</a> <a href='/no-title'>No title</a> <a href='/dup1'>D1</a> "
                  "<a href='/dup2'>D2</a> <a href='/products?id=1&utm_source=x'>P1</a> <a href='/products?id=2'>P2</a> "
                  "<a href='/login?token=SECRET123abc&email=a@b.com'>Login</a> "
                  "<a href='/canon'>Canon</a> <a href='/refresh'>Refresh</a> <a href='/long'>Long</a> "
                  "<a href='http://127.0.0.1:1/unreachable-external'>Ext</a> <img src='/x.png'>",
                  "<script type='application/ld+json'>{\"@context\":\"https://schema.org\",\"@type\":\"Organization\","
                  "\"name\":\"Acme\"}</script>"),
    "/about": _qa_page("About", "<p>No h1 here</p><a href='/'>Home</a> <a href='/about/team'>Team</a>"),
    "/about/team": _qa_page("Team", "<h1>Team</h1><img src='/a.png'><img src='/b.png' alt=''>"),
    "/noindex": _qa_page("Hidden page", "<h1>Hidden</h1>", "<meta name='robots' content='noindex'>"),
    "/no-title": _qa_page(None, "<h1>No title</h1>"),
    "/dup1": _qa_page("Duplicate title", "<h1>D1</h1>", "<meta name='description' content='same'>"),
    "/dup2": _qa_page("Duplicate title", "<h1>D2</h1>", "<meta name='description' content='same'>"),
    "/products": _qa_page("Products", "<h1>Products</h1>"),
    "/login": _qa_page("Login", "<h1>Login</h1>"),
    "/canon": _qa_page("Canon", "<h1>C</h1>", "<link rel='canonical' href='/a'><link rel='canonical' href='/b'>"),
    "/refresh": _qa_page("Refresh", "<h1>R</h1>", "<meta http-equiv='refresh' content='0; url=/'>"),
    "/long": _qa_page("T" * 200, "<h1>Long title</h1>"),
    "/final": _qa_page("Final", "<h1>Final</h1>"),
}
QA_SECURITY = {"Strict-Transport-Security": "max-age=31536000", "X-Content-Type-Options": "nosniff",
               "X-Frame-Options": "DENY", "Content-Security-Policy": "default-src 'self'",
               "Referrer-Policy": "strict-origin-when-cross-origin"}


def qa_site(serve, mode):
    """The fork's QA site: "bad" is full of planted defects and answers a missing page with 200, "good" is clean,
    and "blocked" disallows everything in robots.txt."""
    pages = QA_GOOD if mode == "good" else QA_BAD

    def routes(base):
        robots = "User-agent: *\nDisallow: /\n" if mode == "blocked" else \
            f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"
        urls = "".join(f"<url><loc>{base}{p}</loc></url>" for p in pages) + (
            "" if mode == "good" else f"<url><loc>{base}/in-sitemap-but-404</loc></url>")
        out = {p: (200, QA_SECURITY if mode == "good" else {}, html) for p, html in pages.items()}
        out["/robots.txt"] = (200, {"Content-Type": "text/plain"}, robots)
        out["/sitemap.xml"] = (200, {"Content-Type": "application/xml"},
                               "<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                               f"{urls}</urlset>")
        if mode != "good":
            for a, b in (("/old", "/older"), ("/older", "/oldest"), ("/oldest", "/final")):
                out[a] = (301, {"Location": b}, "")
        for img in ("/x.png", "/a.png", "/b.png"):
            out[img] = (200, {"Content-Type": "image/png"}, b"\x89PNG\r\n\x1a\n")
        return out

    fallback = (200, {}, _qa_page("Oops", "<h1>Not found</h1>")) if mode == "bad" else \
        (404, {}, _qa_page("Not found", "<h1>404</h1>"))
    return serve(routes, fallback) + "/"


def by_id(findings):
    return {f.id: f for f in findings}


def acme(base):
    """A small site with a problem of each kind planted in it."""
    port = base.rsplit(":", 1)[1]
    links = "".join(f"<a href='/item?id={i}'>item {i}</a>" for i in range(15))
    return {
        "/": (200, {}, page("Acme Plumbing", "<a href='/about?utm_source=x'>About</a><a href='/old'>Old</a>"
                            "<a href='/broken'>Broken</a><a href='/private/x'>Private</a>"
                            "<a href='/services/drain'>Drain</a>"
                            f"<a href='http://elsewhere.test:{port}/missing'>elsewhere</a>" + links)),
        "/about": (200, {}, page("About", "<img src='/a.png'>",
                                 "<script type='application/ld+json'>{not json</script>")),
        "/services/drain": (200, {}, page("Drain", "", "<meta name='robots' content='noindex'>"
                                          "<script type='application/ld+json'>"
                                          '{"@type": "Product", "name": "Drain cleaning"}</script>')),
        "/old": (301, {"Location": "/about"}, ""),
        "/broken": (404, {}, "<title>Not found</title>"),
        **{f"/item?id={i}": (200, {}, page(f"Item {i}")) for i in range(15)},
        "/robots.txt": (200, {"Content-Type": "text/plain"},
                        f"User-agent: *\nDisallow: /private\n\nUser-agent: GPTBot\nDisallow: /\n\n"
                        f"Sitemap: {base}/sitemap.xml\n"),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"},
                         "<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                         f"<url><loc>{base}/</loc></url><url><loc>{base}/old</loc></url>"
                         f"<url><loc>{base}/gone</loc></url></urlset>"),
    }

"""Websites for the site check's tests, served on 127.0.0.1 by the `serve` fixture."""
from openppc_online.siteaudit.net import Guard


def local():
    """A guard on which every name resolves to the test server's address, so another "site" is just another host
    name."""
    return Guard(allow_private=True, resolve=lambda host, port: ["127.0.0.1"])


def page(title, body="", head=""):
    return (f"<!doctype html><html lang='en'><head><title>{title}</title>"
            f"<meta name='description' content='{title} page'>"
            f"<meta name='viewport' content='width=device-width'>{head}</head>"
            f"<body><h1>{title}</h1>{body}<p>{'Plenty of words here. ' * 20}</p></body></html>")


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

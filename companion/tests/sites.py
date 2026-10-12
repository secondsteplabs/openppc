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

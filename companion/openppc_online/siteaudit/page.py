"""What the checks need from one HTML page, read with the standard library's tolerant parser."""
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin

SKIP_TEXT = {"script", "style", "noscript", "template", "svg"}
INLINE_SCRIPT_CHARS = 200_000  # of inline script kept per page, to find tag IDs in
CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([\w-]+)""", re.I)
REFRESH = re.compile(r"^\s*\d+\s*;\s*url\s*=\s*['\"]?([^'\"]+)", re.I)


@dataclass
class PageInfo:
    titles: list[str] = field(default_factory=list)
    descriptions: list[str] = field(default_factory=list)
    robots: list[str] = field(default_factory=list)       # meta robots and googlebot values, lower-case
    canonicals: list[str] = field(default_factory=list)   # absolute
    h1: int = 0
    images: int = 0
    images_without_alt: int = 0
    lang: str = ""
    viewport: bool = False
    links: list[str] = field(default_factory=list)        # absolute hrefs of <a> and <area>
    refresh: str = ""                                     # meta refresh target, absolute
    jsonld: list[str] = field(default_factory=list)       # raw text of each JSON-LD script
    microdata: list[str] = field(default_factory=list)    # itemtype values
    items: list[tuple[str, set[str]]] = field(default_factory=list)  # Microdata items: (type, itemprop names)
    og: dict[str, str] = field(default_factory=dict)      # og:* properties
    meta: dict[str, str] = field(default_factory=dict)    # every <meta name|property>, first value
    scripts: list[str] = field(default_factory=list)      # absolute script src values
    inline: str = ""                                      # inline script text, capped
    subresources: list[str] = field(default_factory=list)  # img, script, stylesheet, iframe, media src
    text_chars: int = 0                                   # visible text, whitespace collapsed

    @property
    def title(self) -> str:
        return self.titles[0] if self.titles else ""

    @property
    def description(self) -> str:
        return self.descriptions[0] if self.descriptions else ""

    @property
    def noindex(self) -> bool:
        return any("noindex" in r or r.strip() == "none" for r in self.robots)


class _Reader(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.info = PageInfo()
        self.stack: list[str] = []
        self.capture: list[str] | None = None  # text of the current <title> or JSON-LD script
        self.capture_tag = ""
        self.scopes: list[tuple[int, str, set[str]]] = []  # open Microdata items: (stack depth, type, props)

    def _close_scopes(self) -> None:
        while self.scopes and self.scopes[-1][0] > len(self.stack):
            _, kind, props = self.scopes.pop()
            self.info.items.append((kind, props))

    def _abs(self, value: str | None) -> str:
        if not value:
            return ""
        try:
            return urljoin(self.base, value.strip())
        except ValueError:
            return ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        info = self.info
        if tag == "base" and a.get("href"):
            self.base = self._abs(a["href"])
        elif tag == "html":
            info.lang = a.get("lang", "").strip()
        elif tag == "title" and "svg" not in self.stack:
            self.capture, self.capture_tag = [], "title"
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            content = a.get("content", "")
            if name:
                info.meta.setdefault(name, content.strip())
            if name == "description":
                info.descriptions.append(content.strip())
            elif name in ("robots", "googlebot"):
                info.robots.append(content.lower())
            elif name == "viewport":
                info.viewport = True
            elif name.startswith("og:"):
                info.og.setdefault(name, content.strip())
            if a.get("http-equiv", "").lower() == "refresh":
                m = REFRESH.match(content)
                info.refresh = self._abs(m.group(1)) if m else self.base
        elif tag == "link":
            rel = a.get("rel", "").lower().split()
            if "canonical" in rel and a.get("href"):
                info.canonicals.append(self._abs(a["href"]))
            if "stylesheet" in rel and a.get("href"):
                info.subresources.append(self._abs(a["href"]))
        elif tag in ("a", "area") and a.get("href"):
            info.links.append(self._abs(a["href"]))
        elif tag == "h1":
            info.h1 += 1
        elif tag == "img":
            info.images += 1
            if "alt" not in a:
                info.images_without_alt += 1
            info.subresources.append(self._abs(a.get("src")))
        elif tag == "script":
            if a.get("src"):
                info.scripts.append(self._abs(a["src"]))
                info.subresources.append(self._abs(a["src"]))
            elif a.get("type", "").lower() == "application/ld+json":
                self.capture, self.capture_tag = [], "jsonld"
            else:
                self.capture, self.capture_tag = [], "inline"
        elif tag in ("iframe", "video", "audio", "source", "embed") and a.get("src"):
            info.subresources.append(self._abs(a["src"]))
        if "itemtype" in a:
            info.microdata.append(a["itemtype"].strip())
        if a.get("itemprop") and self.scopes:  # an itemscope's own itemprop names it in the enclosing item
            self.scopes[-1][2].update(a["itemprop"].split())
        void = tag in ("meta", "link", "img", "br", "hr", "input", "base", "source", "embed", "area", "wbr")
        if not void:
            self.stack.append(tag)
        if "itemscope" in a:
            kind = a.get("itemtype", "").split()[0].rstrip("/").rsplit("/", 1)[-1] if a.get("itemtype") else ""
            self.scopes.append((len(self.stack) + (1 if void else 0), kind, set()))
            if void:
                self._close_scopes()

    def handle_endtag(self, tag: str) -> None:
        if self.capture is not None and tag in ("title", "script"):
            text = "".join(self.capture)
            if self.capture_tag == "title":
                self.info.titles.append(" ".join(text.split()))
            elif self.capture_tag == "jsonld":
                self.info.jsonld.append(text)
            elif len(self.info.inline) < INLINE_SCRIPT_CHARS:
                self.info.inline += text[:INLINE_SCRIPT_CHARS] + "\n"
            self.capture = None
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass
            self._close_scopes()

    def handle_data(self, data: str) -> None:
        if self.capture is not None:
            self.capture.append(data)
        elif not SKIP_TEXT.intersection(self.stack):
            self.info.text_chars += len(" ".join(data.split()))


def decode(body: bytes, content_type_header: str) -> str:
    """The page's text: the charset from the BOM, then the header, then a <meta>; UTF-8 otherwise."""
    if body.startswith(b"\xef\xbb\xbf"):
        return body[3:].decode("utf-8", "replace")
    m = re.search(r"charset=([\w-]+)", content_type_header, re.I)
    found = m.group(1) if m else None
    if not found:
        meta = CHARSET.search(body[:4096])
        found = meta.group(1).decode("ascii", "replace") if meta else None
    try:
        return body.decode(found or "utf-8", "replace")
    except LookupError:
        return body.decode("utf-8", "replace")


def read(html: str, base: str) -> PageInfo:
    reader = _Reader(base)
    reader.feed(html)
    reader.close()
    reader.stack.clear()
    reader._close_scopes()  # items left open by a page that never closes its tags
    return reader.info

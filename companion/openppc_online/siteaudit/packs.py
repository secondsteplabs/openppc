"""Rule packs: checks, suppressions and tag signatures written as data (`openppc-online site --config FILE`).

A pack and a project's own config file are the same JSON format, specified in
openppc_online/schemas/site-config.schema.json:

    {"openppc_site": 1,
     "rules": [{"id": "gtm-everywhere", "category": "tracking", "severity": "high",
                "title": "Pages without our tag manager", "fix": "Add the GTM snippet to the page template.",
                "require": {"field": "source", "contains": "GTM-ABC123"}}],
     "suppress": [{"rule": "site-noindex", "match": "/thank-you*", "reason": "Kept out of search on purpose."}],
     "signatures": [{"id": "our-collector", "name": "Our server-side tag", "kind": "analytics",
                     "hit": [{"host": "t.example.com", "path": "/collect"}]}]}

Safe by construction: a rule compares one field of a page with a literal (no regular expressions,
no code), so a pack from anyone can't hang the scan or run anything on your machine.
"""
import json
import re
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit

from .checks import CATEGORIES, SEVERITY_RANK, Finding, Rule, code, events, tracking
from .crawl import Crawl, Page
from .render import NOT_RUN, Rendered
from .tags import EVENT_CHARS, VENDORS, add_vendors

SPEC = 1
ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
EFFORTS = ("low", "medium", "high")
TEXT_FIELDS = ("title", "description", "lang", "canonical", "robots", "source", "url", "jsonld")
NUMBER_FIELDS = ("h1", "text_chars", "images_without_alt", "status")
PREFIX_FIELDS = ("meta:", "header:")
TEXT_OPS = {"present": bool, "absent": bool, "equals": str, "contains": str, "not_contains": str,
            "starts_with": str, "min_length": int, "max_length": int}
NUMBER_OPS = {"min": (int, float), "max": (int, float), "equals": (int, float)}
VENDOR_KINDS = ("analytics", "ads", "tag manager")
NOTE_CHARS = 80  # of a field's value quoted in a finding
TEXT_LIMIT = 1000  # longest literal a rule may compare with


@dataclass(frozen=True)
class PackRule:
    id: str
    spec: Rule
    require: dict[str, Any]
    pages: tuple[str, ...] = ()   # path globs; empty means every page
    source: str = ""              # the file it came from


@dataclass(frozen=True)
class Suppression:
    rule: str      # a finding id or rule id; a trailing * matches a prefix
    match: str     # a glob on the item (a URL's path and query, or the item's text); "" matches all
    reason: str
    source: str = ""


@dataclass
class Config:
    files: list[str] = field(default_factory=list)
    rules: list[PackRule] = field(default_factory=list)
    suppress: list[Suppression] = field(default_factory=list)
    vendors: list[dict[str, Any]] = field(default_factory=list)


class PackError(ValueError):
    pass


def _fail(where: str, path: str, message: str) -> NoReturn:
    raise PackError(f"{where}: {path}: {message}" if path else f"{where}: {message}")


def _keys(where: str, path: str, obj: Any, required: tuple[str, ...], optional: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(obj, dict):
        _fail(where, path, "must be an object")
    for k in required:
        if k not in obj:
            _fail(where, path, f"missing \"{k}\"")
    for k in obj:
        if k not in required + optional:
            _fail(where, path, f"unknown key \"{k}\" (allowed: {', '.join(required + optional)})")
    return obj


def _text(where: str, path: str, value: Any, most: int) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(where, path, "must be non-empty text")
    if len(value) > most:
        _fail(where, path, f"is longer than {most} characters")
    return value.strip()


def _require(where: str, path: str, req: Any, vendors: set[str]) -> dict[str, Any]:
    if isinstance(req, dict) and "tag" in req:
        _keys(where, path, req, ("tag",), ("event",))
        if req["tag"] not in vendors:
            _fail(where, path + ".tag", f"unknown tag \"{req['tag']}\" (known: {', '.join(sorted(vendors))})")
        if "event" in req:
            _text(where, path + ".event", req["event"], EVENT_CHARS)
        return req
    _keys(where, path, req, ("field",), tuple(TEXT_OPS) + tuple(NUMBER_OPS))
    name = req["field"]
    numeric = name in NUMBER_FIELDS
    if not (numeric or name in TEXT_FIELDS or (isinstance(name, str) and name.startswith(PREFIX_FIELDS)
                                                and len(name) > len(name.split(":")[0]) + 1)):
        _fail(where, path + ".field", f"unknown field \"{name}\" (known: {', '.join(TEXT_FIELDS + NUMBER_FIELDS)}, "
                                      "meta:NAME, header:NAME)")
    ops = {k: v for k, v in req.items() if k != "field"}
    if not ops:
        _fail(where, path, "needs a condition, e.g. \"present\": true")
    allowed: dict[str, Any] = NUMBER_OPS if numeric else TEXT_OPS
    for op, value in ops.items():
        kind = allowed.get(op)
        if kind is None:
            _fail(where, f"{path}.{op}", f"isn't a condition for a {'number' if numeric else 'text'} field "
                                         f"(allowed: {', '.join(allowed)})")
        if (isinstance(value, bool) and kind is not bool) or not isinstance(value, kind):
            _fail(where, f"{path}.{op}", "has the wrong type")
        if kind is bool and value is not True:
            _fail(where, f"{path}.{op}", "can only be true")
        if isinstance(value, str) and not 0 < len(value) <= TEXT_LIMIT:
            _fail(where, f"{path}.{op}", f"must be 1 to {TEXT_LIMIT} characters")
    return req


def _pattern(where: str, path: str, p: Any) -> dict[str, str]:
    _keys(where, path, p, (), ("host", "path", "contains"))
    if not p or not all(isinstance(v, str) and v for v in p.values()):
        _fail(where, path, "needs at least one of host, path, contains, as text")
    return dict(p)


def _vendor(where: str, path: str, v: Any, taken: set[str]) -> dict[str, Any]:
    _keys(where, path, v, ("id", "name", "kind"), ("load", "hit", "source", "events"))
    if not isinstance(v["id"], str) or not ID.match(v["id"]):
        _fail(where, path + ".id", "must be lower-case letters, digits and dashes")
    if v["id"] in taken:
        _fail(where, path + ".id", f"\"{v['id']}\" is already a known tag")
    if v["kind"] not in VENDOR_KINDS:
        _fail(where, path + ".kind", f"must be one of {', '.join(VENDOR_KINDS)}")
    out = {"id": v["id"], "name": _text(where, path + ".name", v["name"], 80), "kind": v["kind"],
           "load": [], "hit": [], "source": []}
    for key in ("load", "hit"):
        items = v.get(key, [])
        if not isinstance(items, list):
            _fail(where, f"{path}.{key}", "must be a list")
        out[key] = [_pattern(where, f"{path}.{key}[{i}]", p) for i, p in enumerate(items)]
    source = v.get("source", [])
    if not isinstance(source, list) or not all(isinstance(s, str) and s for s in source):
        _fail(where, path + ".source", "must be a list of text to find in the page's scripts")
    out["source"] = [re.escape(s) for s in source]  # literal text, so a pack can't add a slow pattern
    keys = v.get("events", [])
    if not isinstance(keys, list) or not all(isinstance(k, str) and 0 < len(k) <= 40 for k in keys):
        _fail(where, path + ".events", "must be a list of query keys that name the event, such as \"en\"")
    out["events"] = keys
    if not (out["load"] or out["hit"] or out["source"]):
        _fail(where, path, "needs a load, hit or source pattern")
    return out


def parse(text: str, where: str, config: Config) -> None:
    """Adds one file's rules, suppressions and signatures to config; a mistake raises PackError."""
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise PackError(f"{where}: line {e.lineno}, column {e.colno}: {e.msg}") from None
    _keys(where, "", doc, ("openppc_site",), ("name", "about", "rules", "suppress", "signatures"))
    if doc["openppc_site"] != SPEC:
        _fail(where, "openppc_site", f"this OpenPPC reads version {SPEC} files, not {doc['openppc_site']!r}")
    for key in ("rules", "suppress", "signatures"):
        if not isinstance(doc.get(key, []), list):
            _fail(where, key, "must be a list")
    taken = set(VENDORS) | {v["id"] for v in config.vendors}
    for i, v in enumerate(doc.get("signatures", [])):
        vendor = _vendor(where, f"signatures[{i}]", v, taken)
        taken.add(vendor["id"])
        config.vendors.append(vendor)
    ids = {r.id for r in config.rules}
    for i, r in enumerate(doc.get("rules", [])):
        path = f"rules[{i}]"
        _keys(where, path, r, ("id", "category", "severity", "title", "fix", "require"), ("effort", "pages"))
        rid = r["id"]
        if not isinstance(rid, str) or not ID.match(rid):
            _fail(where, path + ".id", "must be lower-case letters, digits and dashes")
        if rid.startswith("site-"):
            _fail(where, path + ".id", "\"site-\" is kept for the built-in rules; use another prefix")
        if rid in ids:
            _fail(where, path + ".id", f"\"{rid}\" is defined twice")
        if r["category"] not in CATEGORIES or r["category"] == "crawl":
            _fail(where, path + ".category", f"must be one of {', '.join(c for c in CATEGORIES if c != 'crawl')}")
        if r["severity"] not in SEVERITY_RANK:
            _fail(where, path + ".severity", f"must be one of {', '.join(SEVERITY_RANK)}")
        effort = r.get("effort", "low")
        if effort not in EFFORTS:
            _fail(where, path + ".effort", f"must be one of {', '.join(EFFORTS)}")
        req = _require(where, path + ".require", r["require"], taken)
        pages = r.get("pages", [])
        pages = [pages] if isinstance(pages, str) else pages
        if not isinstance(pages, list) or not all(isinstance(p, str) and p for p in pages):
            _fail(where, path + ".pages", "must be a path glob such as \"/blog/*\", or a list of them")
        if pages and "tag" in req:
            _fail(where, path + ".pages", "a tag rule is about the whole site, not some pages")
        spec = Rule(r["category"], r["severity"], _text(where, path + ".title", r["title"], 200),
                    "tags" if "tag" in req else "pages", _text(where, path + ".fix", r["fix"], 1000), effort)
        config.rules.append(PackRule(rid, spec, req, tuple(pages), where))
        ids.add(rid)
    for i, s in enumerate(doc.get("suppress", [])):
        path = f"suppress[{i}]"
        _keys(where, path, s, ("rule", "reason"), ("match",))
        rule = _text(where, path + ".rule", s["rule"], 200)
        match = s.get("match", "")
        if not isinstance(match, str):
            _fail(where, path + ".match", "must be text")
        config.suppress.append(Suppression(rule, match, _text(where, path + ".reason", s["reason"], 500), where))


def load(paths: list[str]) -> Config:
    """Reads every --config file, then makes their tag signatures known to the scan."""
    config = Config()
    for p in paths:
        parse(Path(p).read_text(encoding="utf-8"), p, config)
        config.files.append(p)
    add_vendors(config.vendors)
    return config


def _value(name: str, page: Page) -> str | float:
    i = page.info
    assert i is not None
    if name.startswith("meta:"):
        return i.meta.get(name[5:].lower(), "")
    if name.startswith("header:"):
        return page.resp.headers.get(name[7:].lower(), "")
    parts = urlsplit(page.url)
    values: dict[str, str | float] = {"title": i.title, "description": i.description, "lang": i.lang,
            "canonical": i.canonicals[0] if i.canonicals else "",
            "robots": " ".join(i.robots + [page.resp.headers.get("x-robots-tag", "")]).strip(),
            "source": "\n".join(i.scripts) + "\n" + i.inline,
            "url": parts.path + ("?" + parts.query if parts.query else ""),
            "jsonld": " ".join(i.jsonld), "h1": float(i.h1), "text_chars": float(i.text_chars),
            "images_without_alt": float(i.images_without_alt), "status": float(page.status)}
    return values[name]


def _fails(req: dict[str, Any], value: str | float) -> str:
    """Why value breaks the requirement, or "" when it meets it. Text is compared ignoring case."""
    if isinstance(value, float):
        for op, want in req.items():
            if (op == "min" and value < want) or (op == "max" and value > want) or (op == "equals" and value != want):
                return f"is {code(f'{value:g}')}"
        return ""
    text = value.strip()
    low = text.lower()
    for op, want in req.items():
        w = want.lower() if isinstance(want, str) else want
        if op == "present" and not text:
            return "is empty"
        mismatch = (op == "absent" and text) or (op == "equals" and low != w) or (
            op == "starts_with" and not low.startswith(w))
        if mismatch:
            return f"is {code(text[:NOTE_CHARS])}" if text else "is empty"
        if op == "contains" and w not in low:
            return f"doesn't contain {code(want)}"
        if op == "not_contains" and w in low:
            return f"contains {code(want)}"
        if (op == "min_length" and len(text) < int(want)) or (op == "max_length" and len(text) > int(want)):
            return f"is {code(str(len(text)))} characters long"
    return ""


def evaluate(config: Config, c: Crawl, r: Rendered | None) -> list[Finding]:
    """The packs' findings, on the pages the crawl read (and the tags the browser saw)."""
    out: list[Finding] = []
    pages = c.html_pages()
    tags = tracking(c, r) if any("tag" in x.require for x in config.rules) else {}
    sent = events(r)
    names = {vid: v["name"] for vid, v in VENDORS.items()} | {v["id"]: v["name"] for v in config.vendors}
    for rule in config.rules:
        if "tag" in rule.require:
            vid = rule.require["tag"]
            name = names[vid]
            if vid not in tags:
                note = "" if r else f"not in the home page's HTML; a tag manager may load it, and seeing that needs " \
                                    f"{NOT_RUN}"
                out.append(Finding(rule.id, [name], {name: note} if note else {}, spec=rule.spec))
            elif "event" in rule.require:
                event = rule.require["event"].strip()
                seen = sent.get(vid, [])
                if not r:
                    out.append(Finding(rule.id, [name], {name: f"the {code(event)} event can only be seen with "
                                                               f"{NOT_RUN}"}, spec=rule.spec))
                elif event.lower() not in (s.lower() for s in seen):
                    others = f"; it sent {', '.join(map(code, seen))}" if seen else "; it sent no named events"
                    out.append(Finding(rule.id, [name], {name: f"no {code(event)} event on the rendered pages{others}"},
                                       spec=rule.spec))
            continue
        name = rule.require["field"]
        notes: dict[str, str] = {}
        for p in pages:
            path = urlsplit(p.url).path or "/"
            if rule.pages and not any(fnmatchcase(path, g) for g in rule.pages):
                continue
            why = _fails({k: v for k, v in rule.require.items() if k != "field"}, _value(name, p))
            if why:
                notes[p.url] = f"`{name}` {why}"
        if notes:
            out.append(Finding(rule.id, list(notes), notes, spec=rule.spec))
    return out

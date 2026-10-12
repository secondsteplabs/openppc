"""openppc-online command line.

    openppc-online app
    openppc-online app --port 8800 --no-browser
    openppc-online site https://example.com
    openppc-online site https://example.com --config openppc-site.json --baseline last.json --fail-on high

Exit codes: 0 clean, 1 bad input, as `openppc` uses them. `site` adds 2 a finding at the --fail-on level (with
--baseline, a new one), 3 the report failed its own number check (a bug: please report it), and 4 a scan too broken
to judge with --fail-on (bot protection, robots.txt failing, the start page not loading).
"""
import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import openppc

from . import __version__, site
from .app import PORT, serve
from .siteaudit.crawl import FAST_WORKERS, MAX_PER_PATTERN
from .siteaudit.crux import KEY_ENV


class _Parser(argparse.ArgumentParser):
    """A usage mistake is bad input, so it exits 1, as `openppc` does."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _at_least(kind: Callable[[str], float], low: float, strict: bool = False) -> Callable[[str], float]:
    """An argparse type: a number no smaller than low (larger, when strict)."""
    def parse(text: str) -> float:
        try:
            value = kind(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
        if not (value > low if strict else value >= low):  # NaN fails both
            raise argparse.ArgumentTypeError(f"must be {'more than' if strict else 'at least'} {low}, not {text}")
        return value
    return parse


def _parser() -> argparse.ArgumentParser:
    ap = _Parser(prog="openppc-online",
                 description="The optional OpenPPC companion: the commands that go online, each only when you run it.")
    ap.add_argument("--version", action="version", version=f"openppc-online {__version__} (openppc {openppc.__version__})")
    sub = ap.add_subparsers(dest="command", required=True)
    a = sub.add_parser("app", help="open the OpenPPC app from this computer (it answers on 127.0.0.1 only)")
    a.add_argument("--port", type=int, default=PORT, help=f"port on 127.0.0.1 (default {PORT}; any free one if taken)")
    a.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    s = sub.add_parser("site", help="crawl a website and check its SEO, links, indexing, structured data, HTTPS and "
                                    "tags (connects to that site, and to the hosts it links to)")
    s.add_argument("url", help="the start page, e.g. https://example.com (example.com means https://)")
    s.add_argument("--max-pages", type=_at_least(int, 1), help="stop after this many pages (default: no limit)")
    s.add_argument("--max-time", type=_at_least(float, 0, strict=True),
                   help="stop crawling after this many seconds (default: no limit)")
    s.add_argument("--max-per-pattern", type=_at_least(int, 0), default=MAX_PER_PATTERN,
                   help=f"pages per URL pattern such as /product/* (default {MAX_PER_PATTERN}; 0 lifts the cap)")
    s.add_argument("--fast", action="store_true",
                   help=f"{FAST_WORKERS} requests at a time with no pause; use it on your own site only")
    s.add_argument("--no-external", action="store_true", help="don't check links to other sites")
    s.add_argument("--allow-private", action="store_true",
                   help="allow private and local addresses, to check localhost or a staging server on your network")
    s.add_argument("--crux-key", nargs="?", const="", metavar="KEY",
                   help="add real visitors' Web Vitals from Chrome's UX Report with your own Google API key "
                        f"(connects to chromeuxreport.googleapis.com); give the flag alone to read the key from {KEY_ENV}")
    s.add_argument("--config", action="append", default=[], metavar="FILE",
                   help="a rule pack or project config (rules, suppressions, tag signatures); repeat for more")
    s.add_argument("--baseline", metavar="FILE",
                   help="an earlier --format json result: report what's new and fixed, and fail only on new problems")
    s.add_argument("--fail-on", choices=("high", "medium", "low"),
                   help=f"exit 2 when a finding is this severe or worse; exit {site.INCONCLUSIVE} when the scan was too "
                        "broken to judge")
    s.add_argument("--format", choices=("md", "json", "html", "sarif"), default="md",
                   help="md (default); json: the findings, scores, pages and facts as data; html: one page that "
                        "opens in any browser; sarif: one result per affected page")
    s.add_argument("--out", help="write the report here instead of printing it")
    s.add_argument("--post-to", metavar="URL",
                   help="also POST the JSON result to this webhook when the run ends: https://, or http:// to this "
                        "computer (connects to that host)")
    return ap


def _emit(text: str, out: str | None) -> None:
    if out:
        target = Path(out)
        if target.is_dir():
            raise ValueError(f"{out} is a folder. Give --out a file name, such as {target / 'report.md'}.")
        if not target.parent.is_dir():
            raise ValueError(f"the folder {target.parent} doesn't exist. Create it, or pick another --out.")
        target.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(text)


def _utf8_output() -> None:
    # A Windows console or pipe can default to a legacy code page, where printing a score bar stops the command.
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _progress(msg: str) -> None:
    print(f"\r\x1b[K{msg[:160]}", end="", file=sys.stderr, flush=True)


def _site(args: argparse.Namespace) -> int:
    progress = _progress if sys.stderr.isatty() else None
    result, guard = site.run(args.url, max_pages=args.max_pages, max_seconds=args.max_time,
                             max_per_pattern=args.max_per_pattern, fast=args.fast, external=not args.no_external,
                             allow_private=args.allow_private, crux_key=args.crux_key, config=args.config,
                             baseline=args.baseline, post_to=args.post_to, progress=progress)
    if progress:
        print(file=sys.stderr)
    _emit(result.texts[args.format], args.out)
    if args.post_to:
        payload = site.json_with_summary(result)
        print(site.post(args.post_to, payload, guard), file=sys.stderr)
    return site.exit_code(result, args.fail_on)


def main(argv: list[str] | None = None) -> int:
    _utf8_output()
    args = _parser().parse_args(argv)
    try:
        if args.command == "site":
            return _site(args)
        return serve(args.port, open_browser=not args.no_browser)
    except (ValueError, OSError) as e:
        print(f"openppc-online: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

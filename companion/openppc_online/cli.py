"""openppc-online command line.

    openppc-online app
    openppc-online app --port 8800 --no-browser
    openppc-online site https://example.com
    openppc-online site https://example.com --config openppc-site.json --baseline last.json --fail-on high
    openppc-online site https://example.com --render --render-url /thank-you
    openppc-online site https://example.com/landing --single --psi
    openppc-online site https://staging.example.com/ --single --lighthouse ~/lh --allow-private
    openppc-online fetch google 123-456-7890 --out exports/
    openppc-online fetch meta act_123456789 --conversion lead --out exports/

Exit codes: 0 clean, 1 bad input, as `openppc` uses them. `site` adds 2 a finding at the --fail-on level (with
--baseline, a new one), 3 the report failed its own number check (a bug: please report it), and 4 a scan too broken
to judge with --fail-on (bot protection, robots.txt failing, the start page not loading).
"""
import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import openppc

from . import __version__, site
from .app import PORT, serve
from .fetch import command as fetch_command
from .fetch.files import DAYS
from .siteaudit.crawl import FAST_WORKERS, MAX_PER_PATTERN
from .siteaudit.crux import KEY_ENV
from .siteaudit.lab.psi import KEY_ENV as PSI_KEY_ENV
from .siteaudit.render import MAX_RUNS, RENDER_PAGES, VITALS_PAGES, VITALS_RUNS


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


def _runs(text: str) -> int:
    value = int(_at_least(int, 1)(text))
    if value > MAX_RUNS:
        raise argparse.ArgumentTypeError(f"must be at most {MAX_RUNS}, not {text}")
    return value


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
    s.add_argument("--render", action="store_true",
                   help="also load pages in Chromium: tags, consent, accessibility, Web Vitals (needs "
                        'pip install "openppc-online[render]" and playwright install chromium; connects to the hosts '
                        "the pages load from)")
    s.add_argument("--render-pages", type=_at_least(int, 1), default=RENDER_PAGES,
                   help=f"pages to render (default {RENDER_PAGES}: the home page and one per section)")
    s.add_argument("--vitals-pages", type=_at_least(int, 0), default=VITALS_PAGES,
                   help=f"rendered pages to measure Web Vitals on (default {VITALS_PAGES}: the home page); pages after "
                        "the first get one load each")
    s.add_argument("--runs", type=_runs, default=VITALS_RUNS,
                   help=f"loads of the first measured page per device, the representative one shown (default "
                        f"{VITALS_RUNS}, at most {MAX_RUNS})")
    s.add_argument("--render-url", action="append", default=[], metavar="URL",
                   help="with --render, also render this page of the site, e.g. a thank-you page no link leads to, "
                        "to see which events its tags send; with --psi, also measure it; a path or a full address; "
                        "repeat for more")
    s.add_argument("--consent-selector", default="", metavar="CSS",
                   help="with --render, the CSS selector of your consent banner's accept button")
    s.add_argument("--screenshots", metavar="DIR", default="",
                   help="with --render, save each rendered page as first loaded here (nothing is saved by default)")
    s.add_argument("--crux", action="store_true",
                   help="add real visitors' Web Vitals from Chrome's UX Report with your own Google API key "
                        f"(connects to chromeuxreport.googleapis.com); the key comes from --crux-key or {KEY_ENV}")
    s.add_argument("--crux-key", metavar="KEY", help=f"your CrUX API key, for --crux (it implies it); {KEY_ENV} keeps "
                                                     "it out of your shell history")
    s.add_argument("--psi", action="store_true",
                   help="also measure the start page and each --render-url page with Google PageSpeed Insights, on "
                        "a phone and a desktop: the speed score pagespeed.web.dev shows, Lighthouse's audits and real "
                        "visitors' data (public pages only; sends their addresses to "
                        "pagespeedonline.googleapis.com; works without a key, on a shared quota)")
    s.add_argument("--psi-key", metavar="KEY",
                   help=f"your own PageSpeed Insights API key, for --psi (it implies it); {PSI_KEY_ENV} keeps it out "
                        "of your shell history")
    s.add_argument("--lighthouse", metavar="FOLDER",
                   help="also measure the start page and each --render-url page (5 in all) with your own "
                        "Lighthouse 13 (the folder where you ran npm install lighthouse@13; needs Node.js and the "
                        "render extra), on a phone and a desktop, as PageSpeed Insights does: private and staging "
                        "pages too, nothing sent to Google; the loads fire the page's tags")
    s.add_argument("--single", action="store_true",
                   help="check the start page (and any --render-url pages) only, not the whole site: no sitemap, "
                        "no links followed")
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
    f = sub.add_parser("fetch", help="download an ad account's reports through the platform's API, with your own "
                                     "credentials from environment variables, as the files `openppc audit` reads "
                                     "(connects to that platform only, and changes nothing in the account)")
    f.add_argument("platform", choices=fetch_command.PLATFORMS,
                   help="where the account is; its credentials come from environment variables the companion's "
                        "README lists, never from the command line")
    f.add_argument("account", help="a Google Ads customer ID (123-456-7890), a Microsoft Advertising account ID "
                                   "(149123456) or a Meta ad account (act_123456789)")
    f.add_argument("--out", required=True, metavar="DIR", help="the folder to write the files in")
    f.add_argument("--days", type=_at_least(int, 1), default=DAYS,
                   help=f"the last full days to read (default {DAYS}, at most {fetch_command.MAX_DAYS}); account.json "
                        "compares them with as many days before")
    f.add_argument("--force", action="store_true", help="replace files of the same names already in --out")
    f.add_argument("--conversion", metavar="ACTION_TYPE",
                   help="fetch meta only: the action type that is a conversion for this account, such as lead or "
                        "offsite_conversion.fb_pixel_purchase (without it, the error lists the account's)")
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


def _read(path: str) -> tuple[str, str]:
    return path, Path(path).read_text(encoding="utf-8")


def _site(args: argparse.Namespace) -> int:
    progress = _progress if sys.stderr.isatty() else None
    config = [_read(p) for p in args.config]
    baseline = _read(args.baseline) if args.baseline else None
    crux_key = args.crux_key if args.crux_key is not None else ("" if args.crux else None)
    psi_key = args.psi_key if args.psi_key is not None else ("" if args.psi else None)
    result, guard = site.run(args.url, max_pages=args.max_pages, max_seconds=args.max_time,
                             max_per_pattern=args.max_per_pattern, fast=args.fast, external=not args.no_external,
                             allow_private=args.allow_private, crux_key=crux_key, psi_key=psi_key,
                             single=args.single, config=config,
                             baseline=baseline, post_to=args.post_to, rendered=args.render,
                             render_pages=args.render_pages, vitals_pages=args.vitals_pages, runs=args.runs,
                             render_url=args.render_url, consent_selector=args.consent_selector,
                             screenshots=args.screenshots, progress=progress, lighthouse_dir=args.lighthouse)
    if progress:
        print(file=sys.stderr)
    _emit(result.texts[args.format], args.out)
    if args.post_to:
        payload = site.json_with_summary(result)
        print(site.post(args.post_to, payload, guard), file=sys.stderr)
    return site.exit_code(result, args.fail_on)


def _fetch(args: argparse.Namespace) -> int:
    done = fetch_command.run(args.platform, args.account, args.out, os.environ, force=args.force,
                             days=int(args.days), conversion=args.conversion)
    for path in done.paths:
        print(f"wrote {path}", file=sys.stderr)
    for note in done.notes:
        print(f"note: {note}", file=sys.stderr)
    for path in done.paths:
        print(f"openppc audit {fetch_command.TEMPLATE[path.name]} {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_output()
    args = _parser().parse_args(argv)
    try:
        if args.command == "site":
            return _site(args)
        if args.command == "fetch":
            return _fetch(args)
        return serve(args.port, open_browser=not args.no_browser)
    except (ValueError, OSError) as e:
        print(f"openppc-online: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

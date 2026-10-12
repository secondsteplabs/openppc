"""OpenPPC command line.

    openppc templates
    openppc industries
    openppc audit search-term-waste --sample
    openppc check --sample
    openppc audit search-term-waste exports/search_terms.csv --industry home-services
    openppc audit account-read exports/search_terms_june.csv exports/search_terms_july.csv
    openppc check --audit their_audit.md --data exports/search_terms.csv
    openppc audit search-term-waste exports/search_terms.csv --format html --out report.html

Exit codes: 0 clean, 1 bad input, 2 the check found problems, 3 a bug in OpenPPC: our own report failed
its number check, or the command crashed (--debug prints the traceback). --format changes what is written,
never the exit code.
"""
import argparse
import sys
import traceback
from pathlib import Path

from . import __version__
from .checkfacts import facts_for_check
from .engine import benchmarks
from . import samples
from .engine.trace import render_check, trace
from .formats import audit_as, check_as, check_result
from .ingest import read_text
from .templates import TEMPLATES, run_template_book

ISSUES = "https://github.com/secondsteplabs/openppc/issues"


def _emit(text, out):
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


class _Parser(argparse.ArgumentParser):
    """A usage mistake is bad input, so it exits 1 like any other: 2 means only "the check found problems"."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _parser():
    ap = _Parser(
        prog="openppc", description="Read-only Google Ads audits where every number traces back to your data.")
    ap.add_argument("--version", action="version", version=f"openppc {__version__}")
    ap.add_argument("--debug", action="store_true", help="on a crash, print Python's traceback")
    # --debug also works after the command; SUPPRESS keeps the subcommand from resetting one given before it
    debug = _Parser(add_help=False)
    debug.add_argument("--debug", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("templates", help="list the audit templates", parents=[debug])
    sub.add_parser("industries", help="list the benchmark industries", parents=[debug])
    a = sub.add_parser("audit", help="run a template on an export", parents=[debug])
    a.add_argument("template", choices=sorted(TEMPLATES))
    a.add_argument("data", nargs="*",
                   help="your export (.csv), or for account-read two exports of one report, one per period, or "
                        "two-period totals (.json)")
    a.add_argument("--sample", action="store_true",
                   help="run on the made-up Acme Plumbing account that ships with OpenPPC")
    a.add_argument("--industry", help="compare against an industry average, e.g. home-services")
    a.add_argument("--min-cost", type=float, default=None,
                   help="cost threshold for a waste flag (default: about $20, in the export's currency)")
    a.add_argument("--brand", help="your brand names, comma-separated; brand terms are never flagged as waste")
    a.add_argument("--out", help="write the report here instead of printing it")
    a.add_argument("--format", choices=("md", "html", "json"), default="md",
                   help="md (default); html, one page that opens in any browser; or json, for scripts")
    c = sub.add_parser("check", help="check the numbers in any audit against your data", parents=[debug])
    c.add_argument("--audit", help="the audit to check (.md or .txt)")
    c.add_argument("--data", action="extend", nargs="+",
                   help="the exports or totals files it was written from: --data a.csv b.csv, or repeat --data")
    c.add_argument("--sample", action="store_true",
                   help="check the sample AI audit against the made-up Acme Plumbing export")
    c.add_argument("--industry", help="also accept this industry's published averages")
    c.add_argument("--out", help="write the result here instead of printing it")
    c.add_argument("--format", choices=("md", "html", "json"), default="md",
                   help="md (default); html, one page that opens in any browser; or json, for scripts")
    return ap


def explain(error):
    """The message for an error the user can fix, in words rather than Python's error codes."""
    if isinstance(error, FileNotFoundError):
        return f"no file at {error.filename}. Check the path."
    if isinstance(error, OSError) and error.filename:
        return f"can't open {error.filename}: {error.strerror or error}."
    if isinstance(error, KeyError) and error.args:
        return str(error.args[0])
    return str(error)


def _utf8_output():
    # A Windows console or pipe can default to a legacy code page, where printing ₹ or € stops the command.
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main(argv=None):
    _utf8_output()
    args = _parser().parse_args(argv)
    try:
        if args.command == "templates":
            for t in TEMPLATES.values():
                print(f"{t.NAME:20} {t.TIER:5} reads a {t.INPUT}\n{'':27}{t.SUMMARY}")
            return 0
        if args.command == "industries":
            for key, row in benchmarks.TABLE.items():
                print(f"{key:20} {row[0]}")
            return 0
        if args.command == "audit":
            if args.sample == bool(args.data):
                raise ValueError("give your export's path, or --sample to try the made-up Acme Plumbing account")
            if args.sample:
                args.data = [str(samples.path(samples.EXPORTS[args.template]))]
                args.industry = args.industry or samples.INDUSTRY
            markdown, book, passed = run_template_book(args.template, args.data, industry=args.industry,
                                                       min_cost=args.min_cost, brand=args.brand)
            _emit(audit_as(args.format, TEMPLATES[args.template], markdown, book, passed), args.out)
            return 0 if passed else 3
        if args.command == "check":
            if args.sample and (args.audit or args.data) or not args.sample and not (args.audit and args.data):
                raise ValueError("give --audit and --data, or --sample to check the sample AI audit")
            if args.sample:
                args.audit, args.data = samples.path(samples.AUDIT), [str(samples.path(samples.AUDIT_DATA))]
                args.industry = args.industry or samples.INDUSTRY
            text = read_text(args.audit)
            claims, contradictions = trace(text, facts_for_check(text, args.data, args.industry))
            result = check_result(claims, contradictions, render_check(claims, contradictions))
            _emit(check_as(args.format, result), args.out)
            return 0 if result["passed"] else 2
    except (ValueError, OSError, KeyError) as e:
        print(f"openppc: {explain(e)}", file=sys.stderr)
        return 1
    except Exception as e:  # a bug: one line by default, the whole traceback with --debug
        if args.debug:
            traceback.print_exc()
        else:
            print(f"openppc: something went wrong inside OpenPPC ({type(e).__name__}: {e}). This is a bug: please "
                  f"report it at {ISSUES}, with the output of the same command run with --debug.", file=sys.stderr)
        return 3
    return 1

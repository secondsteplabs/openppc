"""OpenPPC command line.

    openppc templates
    openppc industries
    openppc audit search-term-waste --sample
    openppc check --sample
    openppc audit search-term-waste exports/search_terms.csv --industry home-services
    openppc check --audit their_audit.md --data exports/search_terms.csv

Exit codes: 0 clean, 1 bad input, 2 the check found problems, 3 our own report failed
its number check (a bug in OpenPPC).
"""
import argparse
import sys
from pathlib import Path

from . import __version__
from .checkfacts import facts_for_paths
from .engine import benchmarks
from . import samples
from .engine.trace import render_check, trace
from .templates import TEMPLATES, run_template


def _emit(text, out):
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(text)


def _parser():
    ap = argparse.ArgumentParser(
        prog="openppc", description="Read-only Google Ads audits where every number traces back to your data.")
    ap.add_argument("--version", action="version", version=f"openppc {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("templates", help="list the audit templates")
    sub.add_parser("industries", help="list the benchmark industries")
    a = sub.add_parser("audit", help="run a template on an export")
    a.add_argument("template", choices=sorted(TEMPLATES))
    a.add_argument("data", nargs="?", help="your export (.csv) or two-period totals (.json)")
    a.add_argument("--sample", action="store_true",
                   help="run on the made-up Acme Plumbing account that ships with OpenPPC")
    a.add_argument("--industry", help="compare against an industry average, e.g. home-services")
    a.add_argument("--min-cost", type=float, default=None,
                   help="cost threshold for a waste flag (default: about $20, in the export's currency)")
    a.add_argument("--brand", help="your brand names, comma-separated; brand terms are never flagged as waste")
    a.add_argument("--out", help="write the report here instead of printing it")
    c = sub.add_parser("check", help="check the numbers in any audit against your data")
    c.add_argument("--audit", help="the audit to check (.md or .txt)")
    c.add_argument("--data", action="append", help="an export or totals file; repeat for more")
    c.add_argument("--sample", action="store_true",
                   help="check the sample AI audit against the made-up Acme Plumbing export")
    c.add_argument("--industry", help="also accept this industry's published averages")
    c.add_argument("--out", help="write the result here instead of printing it")
    return ap


def explain(error):
    """The message for an error the user can fix, in words rather than Python's error codes."""
    if isinstance(error, FileNotFoundError):
        return f"no file at {error.filename}. Check the path."
    if isinstance(error, KeyError) and error.args:
        return str(error.args[0])
    return str(error)


def main(argv=None):
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
                args.data = str(samples.path(samples.EXPORTS[args.template]))
                args.industry = args.industry or samples.INDUSTRY
            markdown, _, passed = run_template(args.template, args.data, industry=args.industry,
                                               min_cost=args.min_cost, brand=args.brand)
            _emit(markdown, args.out)
            return 0 if passed else 3
        if args.command == "check":
            if args.sample and (args.audit or args.data) or not args.sample and not (args.audit and args.data):
                raise ValueError("give --audit and --data, or --sample to check the sample AI audit")
            if args.sample:
                args.audit, args.data = samples.path(samples.AUDIT), [str(samples.path(samples.AUDIT_DATA))]
                args.industry = args.industry or samples.INDUSTRY
            text = Path(args.audit).read_text(encoding="utf-8")
            claims, contradictions = trace(text, facts_for_paths(args.data, args.industry))
            _emit(render_check(claims, contradictions), args.out)
            clean = all(c.verdict == "traced" for c in claims) and not contradictions
            return 0 if clean else 2
    except (ValueError, FileNotFoundError, KeyError) as e:
        print(f"openppc: {explain(e)}", file=sys.stderr)
        return 1
    return 1

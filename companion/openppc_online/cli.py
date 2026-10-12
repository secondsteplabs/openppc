"""openppc-online command line.

    openppc-online app
    openppc-online app --port 8800 --no-browser

Exit codes: 0 clean, 1 bad input, as `openppc` uses them.
"""
import argparse
import sys
from typing import NoReturn

import openppc

from . import __version__
from .app import PORT, serve


class _Parser(argparse.ArgumentParser):
    """A usage mistake is bad input, so it exits 1, as `openppc` does."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _parser() -> argparse.ArgumentParser:
    ap = _Parser(prog="openppc-online",
                 description="The optional OpenPPC companion: the commands that go online, each only when you run it.")
    ap.add_argument("--version", action="version", version=f"openppc-online {__version__} (openppc {openppc.__version__})")
    sub = ap.add_subparsers(dest="command", required=True)
    a = sub.add_parser("app", help="open the OpenPPC app from this computer (it answers on 127.0.0.1 only)")
    a.add_argument("--port", type=int, default=PORT, help=f"port on 127.0.0.1 (default {PORT}; any free one if taken)")
    a.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return serve(args.port, open_browser=not args.no_browser)
    except (ValueError, OSError) as e:
        print(f"openppc-online: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

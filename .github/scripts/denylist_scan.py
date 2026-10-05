"""Fail if any file names a client or a Google Ads account ID from the private denylist.

The list never enters the repository. CI reads it from the CLIENT_DENYLIST secret; a local run
reads it from a file passed with --list. Matches are reported by file, line and the list's line
number, never by the term itself, so a public log cannot leak it. Terms match whole words, in
any case. An account ID written as 123-456-7890 is also caught as 1234567890.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


def terms(text):
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        term = line.strip()
        if not term or term.startswith("#"):
            continue
        found.append((number, term))
        if re.fullmatch(r"\d{3}-\d{3}-\d{4}", term):
            found.append((number, term.replace("-", "")))
    return found


def files(root):
    try:
        listed = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
        return [root / name.decode() for name in listed.split(b"\0") if name]
    except (OSError, subprocess.CalledProcessError):  # not a git checkout: scan every file
        return [p for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fail if any file names a client or account ID from the private denylist.")
    parser.add_argument("--list", help="a file with one term per line (default: the CLIENT_DENYLIST environment variable)")
    parser.add_argument("--root", default=".", help="the folder to scan (default: the current one)")
    args = parser.parse_args(argv)
    text = Path(args.list).read_text(encoding="utf-8") if args.list else os.environ.get("CLIENT_DENYLIST", "")
    found = terms(text)
    if not found:
        print("denylist: no terms given; set CLIENT_DENYLIST or pass --list", file=sys.stderr)
        return 2
    pattern = re.compile("|".join(f"(?P<t{i}>(?<!\\w){re.escape(term)}(?!\\w))" for i, (_, term) in enumerate(found)), re.I)
    root = Path(args.root).resolve()
    hits = set()
    for path in files(root):
        rel = path.relative_to(root).as_posix()
        for match in pattern.finditer(rel):
            hits.add((rel, 0, found[int(match.lastgroup[1:])][0]))
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8000]:
            continue  # images, video and other binaries are checked separately
        for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            for match in pattern.finditer(line):
                hits.add((rel, number, found[int(match.lastgroup[1:])][0]))
    for rel, number, term_line in sorted(hits):
        where = f"{rel}:{number}" if number else f"{rel} (file name)"
        print(f"{where}: matches denylist line {term_line}")
    print(f"denylist: {len(found)} terms checked, {len(hits)} matches")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())

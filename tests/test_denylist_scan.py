"""The CI check that keeps client names and account IDs out of the public repository."""
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "denylist_scan.py"


def _scan(tmp_path, files, listed):
    root = tmp_path / "tree"
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
    denylist = tmp_path / "denylist.txt"
    denylist.write_text(listed)
    return subprocess.run([sys.executable, str(SCRIPT), "--list", str(denylist), "--root", str(root)], capture_output=True, text=True)


def test_a_client_name_or_account_id_fails_without_the_term_in_the_log(tmp_path):
    run = _scan(tmp_path, {"notes.md": "fine\nAudit for Northwind Tiles today\n", "data/ids.csv": "id\n1234567890\n"},
                "# private list\nNorthwind Tiles\n123-456-7890\n")
    assert run.returncode == 1
    assert "notes.md:2: matches denylist line 2" in run.stdout
    assert "data/ids.csv:2: matches denylist line 3" in run.stdout
    assert "Northwind" not in run.stdout and "123-456" not in run.stdout and "1234567890" not in run.stdout


def test_only_whole_words_match_and_binaries_are_skipped(tmp_path):
    run = _scan(tmp_path, {"a.txt": "Northwindows is another word\n", "b.png": b"\x89PNG\0Northwind"}, "Northwind\n")
    assert run.returncode == 0, run.stdout


def test_a_file_name_can_match_too(tmp_path):
    run = _scan(tmp_path, {"exports/northwind_terms.txt": "nothing here\n"}, "northwind_terms\n")
    assert run.returncode == 1 and "(file name)" in run.stdout


def test_an_empty_list_is_an_error_not_a_pass(tmp_path):
    run = _scan(tmp_path, {"a.txt": "x"}, "# only a comment\n")
    assert run.returncode == 2 and "no terms" in run.stderr

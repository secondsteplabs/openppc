"""What users see stays as it is unless a change says so: every report, card, check and page title is frozen in
tests/golden/, built by tools/build_golden.py."""
import difflib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden"


def _builder():
    spec = importlib.util.spec_from_file_location("build_golden", ROOT / "tools" / "build_golden.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_what_users_see_is_unchanged():
    built = _builder().golden()
    on_disk = {p.name: p.read_text(encoding="utf-8") for p in GOLDEN.iterdir()}
    assert set(on_disk) == set(built), "run python tools/build_golden.py and review the diff"
    changed = {name: "".join(difflib.unified_diff(on_disk[name].splitlines(True), text.splitlines(True), "before",
                                                  "now", n=1))[:1500]
               for name, text in built.items() if on_disk[name] != text}
    assert not changed, ("output changed; if intended, run python tools/build_golden.py and review the diff:\n"
                         + "\n".join(f"== {name}\n{diff}" for name, diff in changed.items()))

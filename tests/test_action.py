"""The GitHub Action (action.yml) installs its own commit and never pastes an input into a script. CI runs it for
real (the action job in .github/workflows/tests.yml)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTION = (ROOT / "action.yml").read_text(encoding="utf-8")


def test_inputs_reach_the_script_through_the_environment_only():
    scripts = re.findall(r"run: \|\n((?:(?: {8}.*)?\n)+)", ACTION) + re.findall(r"run: (?!\|)(.+)", ACTION)
    assert len(scripts) == 2
    assert not any("${{" in s for s in scripts)


def test_it_installs_the_commit_it_was_pinned_to_and_pins_what_it_uses():
    assert 'pip install --quiet --disable-pip-version-check "$GITHUB_ACTION_PATH"' in ACTION
    uses = re.findall(r"uses: (\S+)", ACTION)
    assert uses and all(re.search(r"@[0-9a-f]{40}$", u) for u in uses)

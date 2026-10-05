"""The made-up sample ships in the package, so a plain pip install can try every template and the checker."""
from pathlib import Path

import pytest

from openppc import cli, samples

ROOT = Path(__file__).resolve().parent.parent


def test_every_template_runs_on_its_sample(capsys):
    for template in sorted(samples.EXPORTS):
        assert cli.main(["audit", template, "--sample"]) == 0, template
    assert "# Search-term waste audit" in capsys.readouterr().out


def test_the_sample_audit_is_checked_against_its_export(capsys):
    assert cli.main(["check", "--sample"]) == 2  # the sample audit has wrong numbers on purpose
    assert "# Number check" in capsys.readouterr().out


def test_a_command_with_neither_a_file_nor_sample_says_what_to_give(capsys):
    assert cli.main(["audit", "search-term-waste"]) == 1
    assert cli.main(["check", "--audit", "x.md"]) == 1
    assert cli.main(["audit", "search-term-waste", "x.csv", "--sample"]) == 1
    assert capsys.readouterr().err.count("--sample") == 3


def test_the_wheel_carries_every_sample_file():
    tomllib = pytest.importorskip("tomllib")
    wheel = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]["build"]["targets"]["wheel"]
    forced = wheel["force-include"]
    assert {Path(dest).name for dest in forced.values()} == set(samples.EXPORTS.values()) | {samples.AUDIT}
    for src, dest in forced.items():
        assert (ROOT / src).is_file() and dest.startswith("openppc/samples/"), src

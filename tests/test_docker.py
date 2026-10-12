"""The Dockerfile builds from exactly what the wheel needs, and .dockerignore lets in only that. CI builds both
images and runs them with --network none (the docker job in .github/workflows/tests.yml)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
IGNORE = [line.strip() for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
          if line.strip() and not line.startswith("#")]


def _copied():
    joined = DOCKERFILE.replace("\\\n", " ")
    return [src for line in re.findall(r"^COPY (.+)$", joined, re.M) for src in line.split()[:-1]]


def test_the_image_gets_every_sample_the_wheel_bundles():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    bundled = set(re.findall(r'^"(examples/[^"]+)" = ', pyproject, re.M))
    assert bundled and {s for s in _copied() if s.startswith("examples/")} == bundled


def test_the_build_context_is_an_allowlist_of_what_the_dockerfile_copies():
    assert IGNORE[0] == "*"
    allowed = {line[1:] for line in IGNORE if line.startswith("!")}
    assert set(_copied()) == allowed
    assert all((ROOT / path).exists() for path in allowed)


def test_the_base_image_is_pinned_and_the_images_do_not_run_as_root():
    assert re.findall(r"^FROM python:\S+@sha256:[0-9a-f]{64} AS source$", DOCKERFILE, re.M)
    assert DOCKERFILE.count("USER openppc") == 2
    assert DOCKERFILE.rstrip().splitlines()[-1].startswith("CMD")  # a plain build makes the command line image
    assert re.search(r"FROM source AS cli\n(?:.*\n)*?RUN pip install \. ", DOCKERFILE)  # no MCP SDK in it

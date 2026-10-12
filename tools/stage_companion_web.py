"""Copy the web app and the license into the companion, for its wheel, so `openppc-online app` works after a plain
pip install:

    python tools/stage_companion_web.py
    python -m build companion

The copies are gitignored. In a clone, `openppc-online app` serves web/ itself.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPANION = ROOT / "companion"


def stage(companion=COMPANION):
    web = Path(companion) / "openppc_online" / "web"
    shutil.rmtree(web, ignore_errors=True)
    shutil.copytree(ROOT / "web", web)
    shutil.copyfile(ROOT / "LICENSE", Path(companion) / "LICENSE")
    return sorted(p.name for p in web.iterdir())


if __name__ == "__main__":
    print("staged", ", ".join(stage()))

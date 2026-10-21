import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_current_version_has_visual_release_notes() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    release_notes = ROOT / "docs" / "releases" / f"v{version}.md"

    assert release_notes.exists()
    content = release_notes.read_text(encoding="utf-8")
    for heading in (
        "## In one sentence",
        "## Visual tour",
        "## What changed",
        "## Upgrade notes",
        "## Verified with",
        "## Links",
    ):
        assert heading in content


def test_readme_showcase_assets_exist() -> None:
    assets = ROOT / "docs" / "assets"
    for name in (
        "streamfetch-mark.svg",
        "product-tour.gif",
        "download-studio.png",
        "library-home.png",
        "player-queue.png",
    ):
        assert (assets / name).is_file()

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    notes = ROOT / "docs" / "releases" / f"v{project['project']['version']}.md"
    references = re.findall(r'\.\./assets/[^\s"\)]+', notes.read_text(encoding="utf-8"))
    assert references, "Release notes must include real product images."
    for reference in references:
        assert (notes.parent / reference).is_file()

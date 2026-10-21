"""Safe GitHub release checks and data-preserving update helpers."""

from __future__ import annotations

import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

REPOSITORY = "mxweir/streamlit-media-downloader"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"


class InstallationMode(StrEnum):
    SOURCE = "source"
    PACKAGE = "package"
    FROZEN = "frozen"


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    name: str
    url: str
    notes: str = ""
    assets: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class UpdateResult:
    success: bool
    message: str
    restart_required: bool = False
    downloaded_file: Path | None = None
    backup_file: Path | None = None


def fetch_latest_release(timeout: float = 5) -> ReleaseInfo:
    request = urllib.request.Request(
        LATEST_RELEASE_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "StreamFetch"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.load(response)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise RuntimeError("The latest release could not be checked.") from exc
    tag = str(payload.get("tag_name", "")).lstrip("v")
    if not tag:
        raise RuntimeError("GitHub returned a release without a version.")
    assets = tuple(
        {
            "name": str(asset.get("name", "")),
            "url": str(asset.get("browser_download_url", "")),
        }
        for asset in payload.get("assets", ())
        if asset.get("browser_download_url")
    )
    return ReleaseInfo(
        version=tag,
        name=str(payload.get("name") or f"StreamFetch {tag}"),
        url=str(payload.get("html_url") or f"https://github.com/{REPOSITORY}/releases"),
        notes=str(payload.get("body") or ""),
        assets=assets,
    )


def is_newer_version(current: str, candidate: str) -> bool:
    try:
        return Version(candidate) > Version(current)
    except InvalidVersion:
        return False


def cached_update_check(
    current_version: str,
    state_dir: Path,
    *,
    force: bool = False,
    max_age_seconds: int = 6 * 60 * 60,
) -> ReleaseInfo | None:
    cache_path = state_dir / "update-cache.json"
    payload: dict[str, Any] | None = None
    if not force:
        with suppress(OSError, ValueError):
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if payload and time.time() - float(payload.get("checked_at", 0)) > max_age_seconds:
            payload = None
    if payload is None:
        release = fetch_latest_release()
        payload = {
            "checked_at": time.time(),
            "version": release.version,
            "name": release.name,
            "url": release.url,
            "notes": release.notes,
            "assets": list(release.assets),
        }
        state_dir.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(cache_path)
    release = ReleaseInfo(
        version=str(payload["version"]),
        name=str(payload.get("name", "StreamFetch update")),
        url=str(payload["url"]),
        notes=str(payload.get("notes", "")),
        assets=tuple(payload.get("assets", ())),
    )
    return release if is_newer_version(current_version, release.version) else None


def installation_mode(project_root: Path | None = None) -> InstallationMode:
    if getattr(sys, "frozen", False):
        return InstallationMode.FROZEN
    root = project_root or Path(__file__).resolve().parents[2]
    return InstallationMode.SOURCE if (root / ".git").exists() else InstallationMode.PACKAGE


def create_pre_update_backup(
    state_dir: Path,
    library_root: Path | None,
    target_version: str,
) -> Path:
    backup_dir = state_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"before-{target_version}-{int(time.time())}.zip"
    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename in ("settings.json", "download-jobs.json", "update-cache.json"):
            path = state_dir / filename
            if path.is_file():
                archive.write(path, f"state/{filename}")
        database = library_root / ".streamfetch" / "library.db" if library_root else None
        if database and database.is_file():
            with tempfile.TemporaryDirectory(prefix="streamfetch-backup-") as temporary:
                snapshot = Path(temporary) / "library.db"
                source = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
                destination = sqlite3.connect(snapshot)
                try:
                    source.backup(destination)
                finally:
                    destination.close()
                    source.close()
                archive.write(snapshot, "library/library.db")
        archive.writestr(
            "RESTORE.txt",
            "Close StreamFetch before restoring these files. Media files are never modified.\n",
        )
    return backup_path


def apply_update(
    release: ReleaseInfo,
    *,
    state_dir: Path,
    library_root: Path | None = None,
    project_root: Path | None = None,
) -> UpdateResult:
    """Install or stage an update after backing up all mutable app data."""

    try:
        backup = create_pre_update_backup(state_dir, library_root, release.version)
    except (OSError, sqlite3.Error, zipfile.BadZipFile):
        return UpdateResult(
            False,
            "The safety backup could not be created, so the update was not started.",
        )
    mode = installation_mode(project_root)
    if mode is InstallationMode.FROZEN:
        try:
            downloaded = _download_packaged_asset(release, state_dir)
        except RuntimeError as exc:
            return UpdateResult(False, str(exc), backup_file=backup)
        return UpdateResult(
            True,
            "The new desktop build is ready. Close StreamFetch, then open the downloaded update.",
            downloaded_file=downloaded,
            backup_file=backup,
        )

    if mode is InstallationMode.SOURCE:
        root = project_root or Path(__file__).resolve().parents[2]
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
        )
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
        )
        if dirty.returncode or dirty.stdout.strip() or branch.stdout.strip() != "main":
            return UpdateResult(
                False,
                "Automatic updates need a clean checkout on main. Your files were not changed.",
                backup_file=backup,
            )
        commands = (
            ["git", "pull", "--ff-only", "origin", "main"],
            [sys.executable, "-m", "pip", "install", "-e", ".[desktop]"],
        )
        cwd = root
    else:
        archive_url = (
            f"https://github.com/{REPOSITORY}/archive/refs/tags/v{release.version}.zip"
        )
        commands = ([sys.executable, "-m", "pip", "install", "--upgrade", archive_url],)
        cwd = None

    for command in commands:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
            timeout=300,
        )
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip().splitlines()
            suffix = f" {detail[-1]}" if detail else ""
            return UpdateResult(
                False,
                f"The update could not be installed.{suffix}",
                backup_file=backup,
            )
    return UpdateResult(
        True,
        "Update installed. Restart StreamFetch to load the new version.",
        restart_required=True,
        backup_file=backup,
    )


def _download_packaged_asset(release: ReleaseInfo, state_dir: Path) -> Path:
    system = platform.system().lower()
    marker = "macos" if system == "darwin" else "windows" if system == "windows" else "linux"
    asset = next(
        (asset for asset in release.assets if marker in asset["name"].lower()),
        None,
    )
    if asset is None:
        raise RuntimeError("No desktop update is available for this operating system yet.")
    target_dir = state_dir / "updates" / f"v{release.version}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / Path(asset["name"]).name
    request = urllib.request.Request(asset["url"], headers={"User-Agent": "StreamFetch"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as output:  # noqa: S310
            shutil.copyfileobj(response, output)
    except (OSError, urllib.error.URLError) as exc:
        target.unlink(missing_ok=True)
        raise RuntimeError("The desktop update could not be downloaded.") from exc
    return target


def launch_downloaded_update(path: Path) -> bool:
    """Open a staged installer or its archive with the operating system."""

    try:
        if platform.system() == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)], start_new_session=True)  # noqa: S603, S607
        else:
            subprocess.Popen(["xdg-open", str(path)], start_new_session=True)  # noqa: S603, S607
    except OSError:
        return False
    return True

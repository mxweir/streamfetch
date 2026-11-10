"""Safe GitHub release checks and data-preserving update helpers."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
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

from .network import verified_context

REPOSITORY = "mxweir/streamfetch"
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
        with urllib.request.urlopen(
            request, timeout=timeout, context=verified_context()
        ) as response:  # noqa: S310
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
            "digest": str(asset.get("digest") or ""),
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
        for filename in ("settings.json", "download-jobs.json", "update-cache.json",
                         "watched-folders.json", "download-presets.json"):
            path = state_dir / filename
            if path.is_file():
                archive.write(path, f"state/{filename}")
        databases = {}
        inbox = state_dir / "inbox.db"
        if inbox.is_file():
            databases["state/inbox.db"] = inbox
        if library_root:
            databases["library/library.db"] = library_root / ".streamfetch" / "library.db"
        watched = state_dir / "watched-folders.json"
        if watched.is_file():
            for index, root in enumerate(json.loads(watched.read_text())):
                databases[f"libraries/watched-{index}/library.db"] = (
                    Path(root) / ".streamfetch" / "library.db"
                )
        subscriptions = state_dir / "subscriptions.db"
        if subscriptions.is_file():
            databases["state/subscriptions.db"] = subscriptions
            with sqlite3.connect(f"file:{subscriptions}?mode=ro", uri=True) as connection:
                for index, (root,) in enumerate(
                    connection.execute("SELECT DISTINCT root FROM sources")
                ):
                    databases[f"libraries/source-{index}/library.db"] = (
                        Path(root) / ".streamfetch" / "library.db"
                    )
        for member, database in databases.items():
            if not database.is_file():
                continue
            with tempfile.TemporaryDirectory(prefix="streamfetch-backup-") as temporary:
                snapshot = Path(temporary) / "library.db"
                source = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
                destination = sqlite3.connect(snapshot)
                try:
                    source.backup(destination)
                finally:
                    destination.close()
                    source.close()
                archive.write(snapshot, member)
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
        archive_url = f"https://github.com/{REPOSITORY}/archive/refs/tags/v{release.version}.zip"
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
    machine = platform.machine().lower()
    arch = {"aarch64": "arm64", "arm64": "arm64", "amd64": "x64", "x86_64": "x64"}.get(machine)
    platform_asset = {"darwin": ("macos", "dmg"), "windows": ("windows", "exe"),
                      "linux": ("linux", "tar.gz")}.get(system)
    if platform_asset is None or arch is None:
        raise RuntimeError("No desktop update is available for this platform.")
    if not re.fullmatch(r"[0-9][a-zA-Z0-9.+-]*", release.version):
        raise RuntimeError("Invalid desktop update version.")
    marker, extension = platform_asset
    name = f"StreamFetch-{marker}-{arch}.{extension}"
    asset = next((entry for entry in release.assets if entry["name"] == name), None)
    if asset is None:
        raise RuntimeError("No desktop update is available for this operating system and CPU.")
    expected = asset.get("digest", "")
    if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", expected):
        raise RuntimeError("GitHub did not publish a valid checksum for this desktop update.")
    url = f"https://github.com/{REPOSITORY}/releases/download/v{release.version}/{name}"
    if asset["url"] != url:
        raise RuntimeError("Unexpected desktop update download URL.")
    target_dir = state_dir / "updates" / f"v{release.version}"
    target = target_dir / name
    staged = None
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "StreamFetch"})
        with tempfile.NamedTemporaryFile(dir=target_dir, delete=False) as output:
            staged = Path(output.name)
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=60, context=verified_context()
            ) as response:
                shutil.copyfileobj(response, output)
        with staged.open("rb") as downloaded:
            actual = hashlib.file_digest(downloaded, "sha256").hexdigest()
        if actual != expected[7:].lower():
            raise RuntimeError("The desktop update checksum did not match. The file was discarded.")
        staged.replace(target)
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError("The desktop update could not be downloaded.") from exc
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
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

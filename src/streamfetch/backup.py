"""Portable library snapshots restored alongside the live workspace."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from streamfetch.library import MEDIA_EXTENSIONS, MediaLibrary


def _digest(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _inventory(root: Path) -> dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Workspace backups cannot contain symbolic links.")
        if path.is_file() and path != root / "manifest.json":
            files[path.relative_to(root).as_posix()] = _digest(path)
    return files


def _snapshot(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with (
        closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as database,
        closing(sqlite3.connect(target)) as snapshot,
    ):
        database.backup(snapshot)


def create_workspace_backup(
    libraries: tuple[MediaLibrary, ...], destination: Path, *, include_originals: bool = False
) -> Path:
    """Write a directory backup, publishing it only after its manifest is complete."""
    destination = destination.expanduser().resolve()
    indexed = tuple({library.root: library for library in libraries
                     if library.database_path.is_file()}.values())
    if not indexed:
        raise ValueError("Choose at least one indexed library.")
    if destination.exists() or any(destination.is_relative_to(lib.root) for lib in indexed):
        raise ValueError("Choose a new backup folder outside the libraries.")
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".streamfetch-backup-") as tmp:
        staged = Path(tmp) / "workspace"
        for index, library in enumerate(indexed, 1):
            target = staged / "libraries" / f"{index:03d}"
            _snapshot(library.database_path, target / ".streamfetch" / "library.db")
            if library.cover_dir.is_dir():
                shutil.copytree(library.cover_dir, target / ".streamfetch" / "covers")
            if include_originals:
                for source in library._media_files():
                    if not source.resolve().is_relative_to(library.root):
                        continue
                    output = target / source.relative_to(library.root)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, output)
        manifest = {
            "version": 1,
            "libraries": [library.root.name for library in indexed],
            "originals": include_originals,
            "files": _inventory(staged),
        }
        (staged / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        staged.rename(destination)
    return destination


def inspect_workspace_backup(source: Path) -> tuple[tuple[str, ...], bool, int]:
    source = source.expanduser().resolve()
    manifest_path = source / "manifest.json"
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 32_000_000:
        raise ValueError("Invalid workspace backup manifest.")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("Unsupported workspace backup format.")
    names, originals, expected = (
        payload.get("libraries"), payload.get("originals"), payload.get("files")
    )
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        raise ValueError("Invalid library list in workspace backup.")
    if not isinstance(originals, bool) or not isinstance(expected, dict):
        raise ValueError("Invalid workspace backup manifest.")
    actual = _inventory(source)
    if actual != expected:
        raise ValueError("The workspace backup is incomplete or its checksums do not match.")
    folders = {f"{index:03d}" for index in range(1, len(names) + 1)}
    for relative in actual:
        path = Path(relative)
        if len(path.parts) < 3 or path.parts[0] != "libraries" or path.parts[1] not in folders:
            raise ValueError("Unexpected file in workspace backup.")
        remainder = path.parts[2:]
        if remainder[0] == ".streamfetch":
            if remainder != (".streamfetch", "library.db") and (
                len(remainder) != 3 or remainder[1] != "covers"
                or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
            ):
                raise ValueError("Unexpected state file in workspace backup.")
        elif not originals or path.suffix.lower() not in MEDIA_EXTENSIONS:
            raise ValueError("Unexpected media file in workspace backup.")
    for folder in folders:
        database = source / "libraries" / folder / ".streamfetch" / "library.db"
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("A library database is damaged.")
            for row in connection.execute("SELECT path, cover_path FROM media_items"):
                for value in (entry for entry in row if entry is not None):
                    relative = Path(value)
                    if relative.is_absolute() or ".." in relative.parts:
                        raise ValueError("A library path is outside the backup.")
    return tuple(names), originals, len(actual)


def restore_workspace_backup(source: Path, destination: Path) -> tuple[Path, ...]:
    source, destination = source.expanduser().resolve(), destination.expanduser().resolve()
    if destination.exists() or destination.is_relative_to(source):
        raise ValueError("Choose a new destination outside the backup folder.")
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".streamfetch-restore-") as tmp:
        staged = Path(tmp) / "workspace"
        shutil.copytree(source, staged, symlinks=True)
        names, _, _ = inspect_workspace_backup(staged)
        for index in range(1, len(names) + 1):
            MediaLibrary(staged / "libraries" / f"{index:03d}").scan()
        staged.rename(destination)
    return tuple(destination / "libraries" / f"{index:03d}" for index in range(1, len(names) + 1))

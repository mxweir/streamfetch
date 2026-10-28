"""Atomic library collection actions and bounded portable original-media exports."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import time
import unicodedata
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from .library import MEDIA_EXTENSIONS, MediaItem, MediaLibrary
from .settings import default_state_dir

MAX_COLLECTION_TRACKS = 200
MAX_EXPORT_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class CollectionExport:
    path: Path
    item_count: int
    size_bytes: int

    def remove(self) -> None:
        """Remove only the artifact returned by this export operation."""
        self.path.unlink(missing_ok=True)


class Collections:
    """Operate on explicit indexed selections, preserving order and original files."""

    def __init__(self, library: MediaLibrary):
        self.library = library

    def items(self, paths: Iterable[Path | str]) -> tuple[MediaItem, ...]:
        keys = tuple(dict.fromkeys(self.library.relative_path(path) for path in paths))
        if not keys:
            raise ValueError("Select at least one track.")
        if len(keys) > MAX_COLLECTION_TRACKS:
            raise ValueError("Select at most 200 tracks per collection.")
        items = tuple(self.library.item_for_path(key) for key in keys)
        if any(item is None for item in items):
            raise ValueError("A selected track is no longer indexed. Refresh the library.")
        return tuple(item for item in items if item is not None)

    def apply(
        self,
        paths: Iterable[Path | str],
        action: str,
        *,
        playlist_id: int | None = None,
        playlist_name: str = "",
    ) -> int:
        """Apply one idempotent bulk action in a single transaction, or change nothing."""
        keys = tuple(self.library.relative_path(item.path) for item in self.items(paths))
        if action not in {"favorite", "unfavorite", "queue", "playlist"}:
            raise ValueError("Unknown collection action.")
        with self.library._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for key in keys:
                if not connection.execute(
                    "SELECT 1 FROM media_items WHERE path = ?", (key,)
                ).fetchone():
                    raise ValueError("A selected track is no longer indexed. Refresh the library.")
            now = time.time()
            before = connection.total_changes
            if action == "favorite":
                connection.executemany(
                    "INSERT OR IGNORE INTO favorites(path, created_at) VALUES (?, ?)",
                    ((key, now) for key in keys),
                )
            elif action == "unfavorite":
                connection.executemany("DELETE FROM favorites WHERE path = ?", ((k,) for k in keys))
            elif action == "queue":
                position = connection.execute(
                    "SELECT COALESCE(MAX(position), 0) FROM queue"
                ).fetchone()[0]
                for key in keys:
                    position += 1
                    connection.execute(
                        "INSERT INTO queue(path, position, created_at) "
                        "SELECT ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM queue WHERE path = ?)",
                        (key, position, now, key),
                    )
            else:
                if playlist_id is None:
                    name = " ".join(playlist_name.split())
                    if not name or len(name) > 120:
                        raise ValueError("Use a playlist name between 1 and 120 characters.")
                    connection.execute(
                        "INSERT OR IGNORE INTO playlists(name, created_at) VALUES (?, ?)",
                        (name, now),
                    )
                    playlist_id = connection.execute(
                        "SELECT id FROM playlists WHERE name = ?", (name,)
                    ).fetchone()[0]
                if not connection.execute(
                    "SELECT 1 FROM playlists WHERE id = ?", (playlist_id,)
                ).fetchone():
                    raise ValueError("The selected playlist no longer exists.")
                position = connection.execute(
                    "SELECT COALESCE(MAX(position), 0) FROM playlist_items WHERE playlist_id = ?",
                    (playlist_id,),
                ).fetchone()[0]
                before = connection.total_changes
                connection.executemany(
                    "INSERT OR IGNORE INTO playlist_items(playlist_id, path, position, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    ((playlist_id, key, position + i, now) for i, key in enumerate(keys, 1)),
                )
            return connection.total_changes - before

    def export(
        self,
        paths: Iterable[Path | str],
        *,
        export_dir: Path | None = None,
        max_bytes: int = MAX_EXPORT_BYTES,
    ) -> CollectionExport:
        """Stream originals to an atomic ZIP on disk; never buffer media in memory.

        Only explicit indexed files below the resolved library root are permitted.
        The manifest is a whitelist, not a serialization of database records.
        """
        if not 1 <= max_bytes <= MAX_EXPORT_BYTES:
            raise ValueError("Export limit must be between 1 byte and 200 MiB.")
        items = self.items(paths)
        sources: list[Path] = []
        total = 0
        for item in items:
            source = item.path.resolve(strict=True)
            try:
                source.relative_to(self.library.root.resolve())
            except ValueError as exc:
                raise ValueError("Selected media must stay inside the library folder.") from exc
            if source.suffix.lower() not in MEDIA_EXTENSIONS or not source.is_file():
                raise ValueError("Only indexed original media files can be exported.")
            total += source.stat().st_size
            sources.append(source)
        if total > max_bytes:
            raise ValueError("The selected originals exceed the export size limit.")
        directory = (export_dir or default_state_dir() / "exports").expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="collection-", suffix=".partial", dir=directory
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        destination = temporary.with_suffix(".zip")
        try:
            manifest_items = []
            playlist = ["#EXTM3U"]
            copied = 0
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
                for index, (item, source) in enumerate(zip(items, sources, strict=True), 1):
                    # Numeric prefixes guarantee uniqueness even on case-insensitive filesystems.
                    member = (
                        f"media/{index:03d} - {_safe_name(item.artist)} - "
                        f"{_safe_name(item.title)}{source.suffix.lower()}"
                    )
                    digest = hashlib.sha256()
                    item_size = 0
                    with (
                        _open_original(self.library.root, source) as input_file,
                        archive.open(member, "w") as output_file,
                    ):
                        while block := input_file.read(1024 * 1024):
                            copied += len(block)
                            item_size += len(block)
                            if copied > max_bytes:
                                raise ValueError(
                                    "The selected originals exceed the export size limit."
                                )
                            output_file.write(block)
                            digest.update(block)
                    manifest_items.append(
                        {
                            "file": member,
                            "title": item.title,
                            "artist": item.artist,
                            "album": item.album,
                            "tags": list(item.tags),
                            "rating": item.rating,
                            "duration_seconds": item.duration_seconds,
                            "size_bytes": item_size,
                            "sha256": digest.hexdigest(),
                        }
                    )
                    label = " ".join(f"{item.artist} - {item.title}".split())
                    duration = (
                        int(item.duration_seconds) if item.duration_seconds is not None else -1
                    )
                    playlist.extend((f"#EXTINF:{duration},{label}", member))
                archive.writestr("playlist.m3u8", "\n".join(playlist) + "\n")
                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "schema": "streamfetch.collection",
                            "version": 1,
                            "created_at": datetime.now(UTC).isoformat(),
                            "items": manifest_items,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
            if temporary.stat().st_size > max_bytes:
                raise ValueError("The selected originals exceed the export size limit.")
            temporary.replace(destination)
            return CollectionExport(destination, len(items), destination.stat().st_size)
        except BaseException:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise


def _open_original(root: Path, source: Path) -> BinaryIO:
    """Open a regular original without a check/open symlink traversal window.

    POSIX traverses every directory from an anchored root descriptor with openat
    and NOFOLLOW. Windows verifies the final path of the *opened handle* before
    reading any byte, which also detects junction/reparse-point replacements.
    """
    relative = source.relative_to(root)
    if os.name == "nt":
        descriptor = os.open(source, os.O_RDONLY | os.O_BINARY)
        try:
            actual = _windows_final_path(descriptor)
            actual.relative_to(root)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("Only indexed original media files can be exported.")
            return os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)
            raise
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise OSError("This platform cannot safely open original media for export.")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.open(root.anchor, directory_flags)
    try:
        # Resolve is deliberately not repeated: every component is opened without
        # following links. A replaced ancestor cannot redirect this descriptor.
        for component in (*root.parts[1:], *relative.parts[:-1]):
            child = os.open(component, directory_flags, dir_fd=parent)
            os.close(parent)
            parent = child
        descriptor = os.open(
            relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("Only indexed original media files can be exported.")
            return os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)
            raise
    finally:
        os.close(parent)


def _windows_final_path(descriptor: int) -> Path:
    """Get the normalized name of an opened Windows handle, never a pathname stat."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get_final_path = kernel.GetFinalPathNameByHandleW
    get_final_path.argtypes = (wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD)
    get_final_path.restype = wintypes.DWORD
    handle = msvcrt.get_osfhandle(descriptor)
    needed = get_final_path(handle, None, 0, 0)
    if not needed:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_unicode_buffer(needed + 1)
    length = get_final_path(handle, buffer, len(buffer), 0)
    if not length or length >= len(buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    name = buffer.value
    if name.startswith("\\\\?\\UNC\\"):
        name = "\\\\" + name[8:]
    elif name.startswith("\\\\?\\"):
        name = name[4:]
    return Path(name)


def _safe_name(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = "".join(char for char in value if not unicodedata.category(char).startswith("C"))
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", value)
    value = " ".join(value.split()).strip(". ")
    # Bound UTF-8 bytes, not code points: long emoji/CJK names must extract on disk too.
    value = value.encode("utf-8")[:80].decode("utf-8", errors="ignore").rstrip(". ")
    return value or "Track"

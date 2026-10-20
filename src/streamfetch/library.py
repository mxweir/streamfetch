"""Persistent, rebuildable index for locally downloaded media."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from mutagen import File as MutagenFile

AUDIO_EXTENSIONS = {".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"}
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".webm"}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
LibraryMediaType = Literal["all", "audio", "video"]


@dataclass(frozen=True)
class MediaItem:
    path: Path
    title: str
    artist: str
    album: str
    duration_seconds: float | None
    size_bytes: int
    media_type: str
    format: str
    modified_at: float
    added_at: float
    cover_path: Path | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class ScanSummary:
    added: int
    updated: int
    removed: int
    total: int


@dataclass(frozen=True)
class LibraryStats:
    total: int
    audio: int
    video: int
    artists: int
    size_bytes: int


class MediaLibrary:
    """Index a media folder in a small SQLite database stored inside it."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.state_dir = self.root / ".streamfetch"
        self.cover_dir = self.state_dir / "covers"
        self.database_path = self.state_dir / "library.db"

    def scan(self) -> ScanSummary:
        self.root.mkdir(parents=True, exist_ok=True)
        now = time.time()
        added = updated = 0
        seen: set[str] = set()

        with self._connection() as connection:
            existing = {
                row["path"]: (row["size_bytes"], row["modified_at"])
                for row in connection.execute(
                    "SELECT path, size_bytes, modified_at FROM media_items"
                )
            }
            for path in self._media_files():
                relative_path = path.relative_to(self.root).as_posix()
                seen.add(relative_path)
                stat = path.stat()
                previous = existing.get(relative_path)
                if previous == (stat.st_size, stat.st_mtime):
                    continue

                metadata = self._inspect(path)
                cover_path = self._store_cover(metadata.pop("cover"))
                connection.execute(
                    """
                    INSERT INTO media_items (
                        path, title, artist, album, duration_seconds, size_bytes,
                        media_type, format, modified_at, added_at, cover_path,
                        source_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        title = excluded.title,
                        artist = excluded.artist,
                        album = excluded.album,
                        duration_seconds = excluded.duration_seconds,
                        size_bytes = excluded.size_bytes,
                        media_type = excluded.media_type,
                        format = excluded.format,
                        modified_at = excluded.modified_at,
                        cover_path = excluded.cover_path,
                        source_url = excluded.source_url
                    """,
                    (
                        relative_path,
                        metadata["title"],
                        metadata["artist"],
                        metadata["album"],
                        metadata["duration_seconds"],
                        stat.st_size,
                        metadata["media_type"],
                        path.suffix.lstrip(".").upper(),
                        stat.st_mtime,
                        now,
                        cover_path,
                        metadata["source_url"],
                    ),
                )
                if previous is None:
                    added += 1
                else:
                    updated += 1

            missing = set(existing) - seen
            connection.executemany(
                "DELETE FROM media_items WHERE path = ?",
                ((path,) for path in missing),
            )
            total = connection.execute("SELECT COUNT(*) FROM media_items").fetchone()[0]
            self._clean_cover_cache(connection)

        return ScanSummary(added, updated, len(missing), total)

    def list_items(
        self,
        search: str = "",
        media_type: LibraryMediaType = "all",
        sort: str = "newest",
        limit: int = 120,
    ) -> tuple[MediaItem, ...]:
        clauses: list[str] = []
        parameters: list[str | int] = []
        if search.strip():
            clauses.append(
                "(title LIKE ? OR artist LIKE ? OR album LIKE ? OR path LIKE ?)"
            )
            pattern = f"%{search.strip()}%"
            parameters.extend([pattern] * 4)
        if media_type in {"audio", "video"}:
            clauses.append("media_type = ?")
            parameters.append(media_type)

        order_by = {
            "artist": "artist COLLATE NOCASE, title COLLATE NOCASE",
            "largest": "size_bytes DESC, title COLLATE NOCASE",
            "oldest": "modified_at ASC, title COLLATE NOCASE",
            "title": "title COLLATE NOCASE",
        }.get(sort, "modified_at DESC, title COLLATE NOCASE")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM media_items {where} ORDER BY {order_by} LIMIT ?",  # noqa: S608
                parameters,
            ).fetchall()
        return tuple(self._item_from_row(row) for row in rows)

    def count_items(self, search: str = "", media_type: LibraryMediaType = "all") -> int:
        clauses: list[str] = []
        parameters: list[str] = []
        if search.strip():
            clauses.append(
                "(title LIKE ? OR artist LIKE ? OR album LIKE ? OR path LIKE ?)"
            )
            parameters.extend([f"%{search.strip()}%"] * 4)
        if media_type in {"audio", "video"}:
            clauses.append("media_type = ?")
            parameters.append(media_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as connection:
            return connection.execute(
                f"SELECT COUNT(*) FROM media_items {where}",  # noqa: S608
                parameters,
            ).fetchone()[0]

    def stats(self) -> LibraryStats:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN media_type = 'audio' THEN 1 ELSE 0 END) AS audio,
                    SUM(CASE WHEN media_type = 'video' THEN 1 ELSE 0 END) AS video,
                    COUNT(DISTINCT CASE
                        WHEN artist != 'Unknown artist' THEN artist
                    END) AS artists,
                    COALESCE(SUM(size_bytes), 0) AS size_bytes
                FROM media_items
                """
            ).fetchone()
        return LibraryStats(
            total=row["total"],
            audio=row["audio"] or 0,
            video=row["video"] or 0,
            artists=row["artists"] or 0,
            size_bytes=row["size_bytes"],
        )

    def _connect(self) -> sqlite3.Connection:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS media_items (
                path TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                album TEXT NOT NULL,
                duration_seconds REAL,
                size_bytes INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                format TEXT NOT NULL,
                modified_at REAL NOT NULL,
                added_at REAL NOT NULL,
                cover_path TEXT,
                source_url TEXT
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS media_search ON media_items(title, artist, album)"
        )
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _media_files(self) -> tuple[Path, ...]:
        files = (
            path
            for path in self.root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in MEDIA_EXTENSIONS
            and self.state_dir not in path.parents
        )
        return tuple(sorted(files))

    def _inspect(self, path: Path) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "title": path.stem,
            "artist": "Unknown artist",
            "album": "Singles",
            "duration_seconds": None,
            "media_type": "audio" if path.suffix.lower() in AUDIO_EXTENSIONS else "video",
            "source_url": None,
            "cover": None,
        }
        try:
            media = MutagenFile(path, easy=True)
            if media is not None:
                tags = media.tags or {}
                metadata["title"] = _first_tag(tags, "title") or metadata["title"]
                metadata["artist"] = _first_tag(tags, "artist") or metadata["artist"]
                metadata["album"] = _first_tag(tags, "album") or metadata["album"]
                metadata["source_url"] = _first_tag(tags, "purl")
                length = getattr(getattr(media, "info", None), "length", None)
                metadata["duration_seconds"] = float(length) if length else None
            raw_media = MutagenFile(path)
            metadata["cover"] = _cover_from_media(raw_media)
        except Exception:
            pass

        if metadata["duration_seconds"] is None:
            metadata.update(_ffprobe_metadata(path, metadata))
        return metadata

    def _store_cover(self, cover: tuple[bytes, str] | None) -> str | None:
        if cover is None:
            return None
        data, extension = cover
        digest = hashlib.sha256(data).hexdigest()[:24]
        relative_path = Path(".streamfetch") / "covers" / f"{digest}.{extension}"
        destination = self.root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(data)
        return relative_path.as_posix()

    def _clean_cover_cache(self, connection: sqlite3.Connection) -> None:
        if not self.cover_dir.exists():
            return
        used = {
            row[0]
            for row in connection.execute(
                "SELECT cover_path FROM media_items WHERE cover_path IS NOT NULL"
            )
        }
        for cover in self.cover_dir.iterdir():
            relative_path = cover.relative_to(self.root).as_posix()
            if cover.is_file() and relative_path not in used:
                cover.unlink()

    def _item_from_row(self, row: sqlite3.Row) -> MediaItem:
        cover_path = self.root / row["cover_path"] if row["cover_path"] else None
        return MediaItem(
            path=self.root / row["path"],
            title=row["title"],
            artist=row["artist"],
            album=row["album"],
            duration_seconds=row["duration_seconds"],
            size_bytes=row["size_bytes"],
            media_type=row["media_type"],
            format=row["format"],
            modified_at=row["modified_at"],
            added_at=row["added_at"],
            cover_path=cover_path,
            source_url=row["source_url"],
        )


def _first_tag(tags: Any, key: str) -> str | None:
    value = tags.get(key)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return str(value).strip() if value else None


def _cover_from_media(media: Any) -> tuple[bytes, str] | None:
    if media is None:
        return None
    pictures = getattr(media, "pictures", None)
    if pictures:
        return pictures[0].data, _image_extension(pictures[0].data)
    tags = getattr(media, "tags", None)
    if not tags:
        return None
    for key, value in tags.items():
        if str(key).startswith("APIC") and getattr(value, "data", None):
            return value.data, _image_extension(value.data)
    covers = tags.get("covr")
    if covers:
        data = bytes(covers[0])
        return data, _image_extension(data)
    return None


def _image_extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def _ffprobe_metadata(path: Path, current: dict[str, Any]) -> dict[str, Any]:
    if shutil.which("ffprobe") is None:
        return {}
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:format_tags=title,artist,album",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return {}
        details = json.loads(result.stdout).get("format", {})
        tags = details.get("tags", {})
        duration = details.get("duration")
        return {
            "title": tags.get("title") or current["title"],
            "artist": tags.get("artist") or current["artist"],
            "album": tags.get("album") or current["album"],
            "duration_seconds": float(duration) if duration else None,
        }
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}

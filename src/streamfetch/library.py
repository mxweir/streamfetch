"""Persistent, rebuildable index for locally downloaded media."""

from __future__ import annotations

import hashlib
import json
import random
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
    rating: int = 0
    tags: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class Playlist:
    id: int
    name: str
    item_count: int


@dataclass(frozen=True)
class QueueEntry:
    id: int
    item: MediaItem


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    item: MediaItem
    played_at: float


@dataclass(frozen=True)
class LibraryFacet:
    name: str
    item_count: int


@dataclass(frozen=True)
class ImportSummary:
    imported: int
    skipped: int
    destination: Path


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
                "(COALESCE(custom_title, title) LIKE ? "
                "OR COALESCE(custom_artist, artist) LIKE ? "
                "OR COALESCE(custom_album, album) LIKE ? OR path LIKE ? "
                "OR tags_json LIKE ?)"
            )
            pattern = f"%{search.strip()}%"
            parameters.extend([pattern] * 5)
        if media_type in {"audio", "video"}:
            clauses.append("media_type = ?")
            parameters.append(media_type)

        order_by = {
            "artist": (
                "COALESCE(custom_artist, artist) COLLATE NOCASE, "
                "COALESCE(custom_title, title) COLLATE NOCASE"
            ),
            "largest": "size_bytes DESC, COALESCE(custom_title, title) COLLATE NOCASE",
            "oldest": "modified_at ASC, COALESCE(custom_title, title) COLLATE NOCASE",
            "title": "COALESCE(custom_title, title) COLLATE NOCASE",
        }.get(sort, "modified_at DESC, COALESCE(custom_title, title) COLLATE NOCASE")
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
                "(COALESCE(custom_title, title) LIKE ? "
                "OR COALESCE(custom_artist, artist) LIKE ? "
                "OR COALESCE(custom_album, album) LIKE ? OR path LIKE ? "
                "OR tags_json LIKE ?)"
            )
            parameters.extend([f"%{search.strip()}%"] * 5)
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
                        WHEN COALESCE(custom_artist, artist) != 'Unknown artist'
                            THEN COALESCE(custom_artist, artist)
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

    def relative_path(self, path: Path | str) -> str:
        candidate = Path(path)
        if candidate.is_absolute():
            candidate = candidate.expanduser().resolve().relative_to(self.root)
        if ".." in candidate.parts:
            raise ValueError("Media paths must stay inside the library folder.")
        return candidate.as_posix()

    def update_metadata(
        self,
        path: Path | str,
        *,
        title: str,
        artist: str,
        album: str,
        rating: int = 0,
        tags: tuple[str, ...] | list[str] = (),
    ) -> MediaItem:
        relative_path = self.relative_path(path)
        clean_title = " ".join(title.split())
        clean_artist = " ".join(artist.split())
        clean_album = " ".join(album.split())
        if not clean_title:
            raise ValueError("Title cannot be empty.")
        if not 0 <= rating <= 5:
            raise ValueError("Rating must be between 0 and 5.")
        clean_tags = tuple(
            dict.fromkeys(
                tag
                for value in tags
                if (tag := " ".join(value.strip().split()))
            )
        )
        if len(clean_tags) > 20 or any(len(tag) > 40 for tag in clean_tags):
            raise ValueError("Use at most 20 tags with 40 characters each.")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE media_items
                SET custom_title = ?, custom_artist = ?, custom_album = ?,
                    rating = ?, tags_json = ?
                WHERE path = ?
                """,
                (
                    clean_title,
                    clean_artist or "Unknown artist",
                    clean_album or "Singles",
                    rating,
                    json.dumps(clean_tags),
                    relative_path,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("The selected item is not indexed in this library.")
        item = self.item_for_path(relative_path)
        if item is None:  # pragma: no cover - guarded by the update above
            raise ValueError("The selected item is not indexed in this library.")
        return item

    def recently_added(self, limit: int = 120) -> tuple[MediaItem, ...]:
        return self._items_for_query(
            "SELECT * FROM media_items ORDER BY added_at DESC, path LIMIT ?",
            (limit,),
        )

    def most_played(self, limit: int = 120) -> tuple[MediaItem, ...]:
        return self._items_for_query(
            """
            SELECT media_items.*, COUNT(play_history.id) AS play_count
            FROM media_items
            JOIN play_history ON play_history.path = media_items.path
            GROUP BY media_items.path
            ORDER BY play_count DESC, MAX(play_history.played_at) DESC
            LIMIT ?
            """,
            (limit,),
        )

    def highly_rated(self, minimum: int = 4, limit: int = 120) -> tuple[MediaItem, ...]:
        return self._items_for_query(
            """
            SELECT * FROM media_items
            WHERE rating >= ?
            ORDER BY rating DESC, COALESCE(custom_title, title) COLLATE NOCASE
            LIMIT ?
            """,
            (minimum, limit),
        )

    def unplayed(self, limit: int = 120) -> tuple[MediaItem, ...]:
        return self._items_for_query(
            """
            SELECT media_items.*
            FROM media_items
            LEFT JOIN play_history ON play_history.path = media_items.path
            WHERE play_history.id IS NULL
            ORDER BY media_items.added_at DESC, media_items.path
            LIMIT ?
            """,
            (limit,),
        )

    def artists(self) -> tuple[LibraryFacet, ...]:
        return self._facets("COALESCE(custom_artist, artist)")

    def albums(self) -> tuple[LibraryFacet, ...]:
        return self._facets("COALESCE(custom_album, album)")

    def items_for_artist(self, artist: str) -> tuple[MediaItem, ...]:
        return self._items_for_query(
            """
            SELECT * FROM media_items
            WHERE COALESCE(custom_artist, artist) = ? COLLATE NOCASE
            ORDER BY COALESCE(custom_album, album) COLLATE NOCASE,
                     COALESCE(custom_title, title) COLLATE NOCASE
            """,
            (artist,),
        )

    def items_for_album(self, album: str) -> tuple[MediaItem, ...]:
        return self._items_for_query(
            """
            SELECT * FROM media_items
            WHERE COALESCE(custom_album, album) = ? COLLATE NOCASE
            ORDER BY COALESCE(custom_artist, artist) COLLATE NOCASE,
                     COALESCE(custom_title, title) COLLATE NOCASE
            """,
            (album,),
        )

    def duplicate_groups(self) -> tuple[tuple[MediaItem, ...], ...]:
        with self._connection() as connection:
            candidates = connection.execute(
                """
                SELECT * FROM media_items
                WHERE size_bytes IN (
                    SELECT size_bytes FROM media_items
                    GROUP BY size_bytes HAVING COUNT(*) > 1
                )
                ORDER BY size_bytes DESC, path
                """
            ).fetchall()
        groups: dict[tuple[int, str], list[MediaItem]] = {}
        for row in candidates:
            item = self._item_from_row(row)
            try:
                digest = _file_digest(item.path)
            except OSError:
                continue
            groups.setdefault((item.size_bytes, digest), []).append(item)
        return tuple(tuple(group) for group in groups.values() if len(group) > 1)

    def import_folder(self, source: Path | str) -> ImportSummary:
        if not str(source).strip():
            raise ValueError("Choose an existing folder to import.")
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_dir():
            raise ValueError("Choose an existing folder to import.")
        if (
            source_path == self.root
            or source_path in self.root.parents
            or self.root in source_path.parents
        ):
            raise ValueError("The import folder must be outside the library folder.")

        destination = self.root / "Imported" / source_path.name
        imported = skipped = 0
        for source_file in sorted(source_path.rglob("*")):
            if not source_file.is_file() or source_file.suffix.lower() not in MEDIA_EXTENSIONS:
                continue
            relative = source_file.relative_to(source_path)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.stat().st_size == source_file.stat().st_size:
                    skipped += 1
                    continue
                target = _available_path(target)
            shutil.copy2(source_file, target)
            imported += 1
        return ImportSummary(imported, skipped, destination)

    def item_for_path(self, path: Path | str) -> MediaItem | None:
        relative_path = self.relative_path(path)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM media_items WHERE path = ?",
                (relative_path,),
            ).fetchone()
        return self._item_from_row(row) if row else None

    def set_current_item(self, path: Path | str) -> None:
        relative_path = self.relative_path(path)
        with self._connection() as connection:
            if not connection.execute(
                "SELECT 1 FROM media_items WHERE path = ?",
                (relative_path,),
            ).fetchone():
                raise ValueError("The selected item is not indexed in this library.")
            connection.execute(
                """
                INSERT INTO settings(key, value) VALUES ('current_item', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (relative_path,),
            )

    def current_item(self) -> MediaItem | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT media_items.*
                FROM settings
                JOIN media_items ON media_items.path = settings.value
                WHERE settings.key = 'current_item'
                """
            ).fetchone()
        return self._item_from_row(row) if row else None

    def record_play(self, path: Path | str) -> None:
        relative_path = self.relative_path(path)
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO play_history(path, played_at) VALUES (?, ?)",
                (relative_path, time.time()),
            )
            connection.execute(
                """
                DELETE FROM play_history
                WHERE id NOT IN (
                    SELECT id FROM play_history ORDER BY id DESC LIMIT 5000
                )
                """
            )

    def history(self, limit: int = 100) -> tuple[HistoryEntry, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT media_items.*, play_history.id AS history_id,
                       play_history.played_at AS history_played_at
                FROM play_history
                JOIN media_items ON media_items.path = play_history.path
                ORDER BY play_history.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return tuple(
            HistoryEntry(row["history_id"], self._item_from_row(row), row["history_played_at"])
            for row in rows
        )

    def previous_item(self, current_path: Path | str) -> MediaItem | None:
        relative_path = self.relative_path(current_path)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT media_items.*
                FROM play_history
                JOIN media_items ON media_items.path = play_history.path
                WHERE play_history.path != ?
                ORDER BY play_history.id DESC
                LIMIT 1
                """,
                (relative_path,),
            ).fetchone()
        return self._item_from_row(row) if row else None

    def toggle_favorite(self, path: Path | str) -> bool:
        relative_path = self.relative_path(path)
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM favorites WHERE path = ?",
                (relative_path,),
            ).fetchone()
            if exists:
                connection.execute("DELETE FROM favorites WHERE path = ?", (relative_path,))
                return False
            connection.execute(
                "INSERT INTO favorites(path, created_at) VALUES (?, ?)",
                (relative_path, time.time()),
            )
        return True

    def favorite_paths(self) -> set[str]:
        with self._connection() as connection:
            return {row[0] for row in connection.execute("SELECT path FROM favorites")}

    def favorite_items(self) -> tuple[MediaItem, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT media_items.*
                FROM favorites
                JOIN media_items ON media_items.path = favorites.path
                ORDER BY favorites.created_at DESC
                """
            ).fetchall()
        return tuple(self._item_from_row(row) for row in rows)

    def enqueue(self, path: Path | str, *, play_next: bool = False) -> int:
        relative_path = self.relative_path(path)
        with self._connection() as connection:
            if play_next:
                position = connection.execute(
                    "SELECT COALESCE(MIN(position), 1) - 1 FROM queue"
                ).fetchone()[0]
            else:
                position = connection.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 FROM queue"
                ).fetchone()[0]
            cursor = connection.execute(
                "INSERT INTO queue(path, position, created_at) VALUES (?, ?, ?)",
                (relative_path, position, time.time()),
            )
            return cursor.lastrowid

    def queue(self) -> tuple[QueueEntry, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT media_items.*, queue.id AS queue_id
                FROM queue
                JOIN media_items ON media_items.path = queue.path
                ORDER BY queue.position, queue.id
                """
            ).fetchall()
        return tuple(QueueEntry(row["queue_id"], self._item_from_row(row)) for row in rows)

    def take_queue_entry(self, entry_id: int | None = None) -> MediaItem | None:
        with self._connection() as connection:
            if entry_id is None:
                row = connection.execute(
                    """
                    SELECT media_items.*, queue.id AS queue_id
                    FROM queue
                    JOIN media_items ON media_items.path = queue.path
                    ORDER BY queue.position, queue.id
                    LIMIT 1
                    """
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT media_items.*, queue.id AS queue_id
                    FROM queue
                    JOIN media_items ON media_items.path = queue.path
                    WHERE queue.id = ?
                    """,
                    (entry_id,),
                ).fetchone()
            if row:
                connection.execute("DELETE FROM queue WHERE id = ?", (row["queue_id"],))
        return self._item_from_row(row) if row else None

    def remove_queue_entry(self, entry_id: int) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM queue WHERE id = ?", (entry_id,))

    def clear_queue(self) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM queue")

    def reorder_queue(self, entry_ids: list[int] | tuple[int, ...]) -> None:
        with self._connection() as connection:
            current_ids = {
                row[0] for row in connection.execute("SELECT id FROM queue")
            }
            if len(entry_ids) != len(current_ids) or set(entry_ids) != current_ids:
                raise ValueError("Queue order must contain every queued item exactly once.")
            connection.executemany(
                "UPDATE queue SET position = ? WHERE id = ?",
                ((position, entry_id) for position, entry_id in enumerate(entry_ids, start=1)),
            )

    def shuffle_queue(self, randomizer: random.Random | None = None) -> None:
        entry_ids = [entry.id for entry in self.queue()]
        (randomizer or random.SystemRandom()).shuffle(entry_ids)
        self.reorder_queue(entry_ids)

    def replace_queue(self, paths: tuple[Path, ...] | list[Path]) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM queue")
            now = time.time()
            rows = [
                (self.relative_path(path), position, now)
                for position, path in enumerate(paths, start=1)
            ]
            connection.executemany(
                "INSERT INTO queue(path, position, created_at) VALUES (?, ?, ?)",
                rows,
            )

    def player_setting(self, key: str, default: str) -> str:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                (f"player.{key}",),
            ).fetchone()
        return row[0] if row else default

    def set_player_setting(self, key: str, value: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (f"player.{key}", value),
            )

    def playback_position(self, path: Path | str) -> float:
        relative_path = self.relative_path(path)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT position_seconds FROM playback_positions WHERE path = ?",
                (relative_path,),
            ).fetchone()
        return float(row[0]) if row else 0.0

    def set_playback_position(self, path: Path | str, position_seconds: float) -> None:
        relative_path = self.relative_path(path)
        with self._connection() as connection:
            if position_seconds <= 0:
                connection.execute(
                    "DELETE FROM playback_positions WHERE path = ?",
                    (relative_path,),
                )
                return
            connection.execute(
                """
                INSERT INTO playback_positions(path, position_seconds, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    position_seconds = excluded.position_seconds,
                    updated_at = excluded.updated_at
                """,
                (relative_path, position_seconds, time.time()),
            )

    def create_playlist(self, name: str) -> Playlist:
        clean_name = " ".join(name.split())
        if not clean_name:
            raise ValueError("Enter a playlist name.")
        if len(clean_name) > 80:
            raise ValueError("Playlist names must be 80 characters or fewer.")
        try:
            with self._connection() as connection:
                cursor = connection.execute(
                    "INSERT INTO playlists(name, created_at) VALUES (?, ?)",
                    (clean_name, time.time()),
                )
                playlist_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise ValueError("A playlist with this name already exists.") from exc
        return Playlist(playlist_id, clean_name, 0)

    def playlists(self) -> tuple[Playlist, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT playlists.id, playlists.name, COUNT(playlist_items.path) AS item_count
                FROM playlists
                LEFT JOIN playlist_items ON playlist_items.playlist_id = playlists.id
                GROUP BY playlists.id
                ORDER BY playlists.name COLLATE NOCASE
                """
            ).fetchall()
        return tuple(Playlist(row["id"], row["name"], row["item_count"]) for row in rows)

    def delete_playlist(self, playlist_id: int) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))

    def add_to_playlist(self, playlist_id: int, path: Path | str) -> None:
        relative_path = self.relative_path(path)
        with self._connection() as connection:
            position = connection.execute(
                """
                SELECT COALESCE(MAX(position), 0) + 1
                FROM playlist_items
                WHERE playlist_id = ?
                """,
                (playlist_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT OR IGNORE INTO playlist_items(
                    playlist_id, path, position, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (playlist_id, relative_path, position, time.time()),
            )

    def sync_source_playlist(self, name: str, paths: list[Path]) -> None:
        """Replace a source-owned playlist in source order, preserving all media."""
        relative = list(dict.fromkeys(self.relative_path(path) for path in paths))
        with self._connection() as connection:
            connection.execute("INSERT OR IGNORE INTO playlists(name,created_at) VALUES (?,?)",
                               (name, time.time()))
            playlist_id = connection.execute("SELECT id FROM playlists WHERE name=?",
                                             (name,)).fetchone()[0]
            connection.execute("DELETE FROM playlist_items WHERE playlist_id=?", (playlist_id,))
            for position, path in enumerate(relative):
                connection.execute("""INSERT INTO playlist_items
                    (playlist_id,path,position,created_at)
                    SELECT ?,path,?,? FROM media_items WHERE path=?""",
                                   (playlist_id, position, time.time(), path))

    def remove_from_playlist(self, playlist_id: int, path: Path | str) -> None:
        relative_path = self.relative_path(path)
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM playlist_items WHERE playlist_id = ? AND path = ?",
                (playlist_id, relative_path),
            )

    def playlist_items(self, playlist_id: int) -> tuple[MediaItem, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT media_items.*
                FROM playlist_items
                JOIN media_items ON media_items.path = playlist_items.path
                WHERE playlist_items.playlist_id = ?
                ORDER BY playlist_items.position, playlist_items.created_at
                """,
                (playlist_id,),
            ).fetchall()
        return tuple(self._item_from_row(row) for row in rows)

    def _items_for_query(
        self,
        query: str,
        parameters: tuple[Any, ...] = (),
    ) -> tuple[MediaItem, ...]:
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(self._item_from_row(row) for row in rows)

    def _facets(self, expression: str) -> tuple[LibraryFacet, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {expression} AS name, COUNT(*) AS item_count
                FROM media_items
                GROUP BY {expression}
                ORDER BY name COLLATE NOCASE
                """  # noqa: S608
            ).fetchall()
        return tuple(LibraryFacet(row["name"], row["item_count"]) for row in rows)

    def _connect(self) -> sqlite3.Connection:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
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
                source_url TEXT,
                custom_title TEXT,
                custom_artist TEXT,
                custom_album TEXT,
                rating INTEGER NOT NULL DEFAULT 0,
                tags_json TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS media_search ON media_items(title, artist, album)"
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS favorites (
                path TEXT PRIMARY KEY REFERENCES media_items(path) ON DELETE CASCADE,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL REFERENCES media_items(path) ON DELETE CASCADE,
                position INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS playlist_items (
                playlist_id INTEGER NOT NULL
                    REFERENCES playlists(id) ON DELETE CASCADE,
                path TEXT NOT NULL REFERENCES media_items(path) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (playlist_id, path)
            );
            CREATE TABLE IF NOT EXISTS play_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL REFERENCES media_items(path) ON DELETE CASCADE,
                played_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS playback_positions (
                path TEXT PRIMARY KEY REFERENCES media_items(path) ON DELETE CASCADE,
                position_seconds REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS history_order ON play_history(id DESC);
            """
        )
        queue_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(queue)")
        }
        if "position" not in queue_columns:
            connection.execute(
                "ALTER TABLE queue ADD COLUMN position INTEGER NOT NULL DEFAULT 0"
            )
            connection.execute("UPDATE queue SET position = id")
        connection.execute("DROP INDEX IF EXISTS queue_order")
        connection.execute("CREATE INDEX queue_order ON queue(position, id)")
        media_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(media_items)")
        }
        for column, definition in (
            ("custom_title", "TEXT"),
            ("custom_artist", "TEXT"),
            ("custom_album", "TEXT"),
            ("rating", "INTEGER NOT NULL DEFAULT 0"),
            ("tags_json", "TEXT NOT NULL DEFAULT '[]'"),
        ):
            if column not in media_columns:
                connection.execute(
                    f"ALTER TABLE media_items ADD COLUMN {column} {definition}"  # noqa: S608
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
        keys = set(row.keys())
        tags_value = row["tags_json"] if "tags_json" in keys else "[]"
        try:
            tags = tuple(json.loads(tags_value or "[]"))
        except (TypeError, json.JSONDecodeError):
            tags = ()
        return MediaItem(
            path=self.root / row["path"],
            title=(row["custom_title"] if "custom_title" in keys else None) or row["title"],
            artist=(row["custom_artist"] if "custom_artist" in keys else None)
            or row["artist"],
            album=(row["custom_album"] if "custom_album" in keys else None) or row["album"],
            duration_seconds=row["duration_seconds"],
            size_bytes=row["size_bytes"],
            media_type=row["media_type"],
            format=row["format"],
            modified_at=row["modified_at"],
            added_at=row["added_at"],
            cover_path=cover_path,
            source_url=row["source_url"],
            rating=row["rating"] if "rating" in keys else 0,
            tags=tags,
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


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _available_path(path: Path) -> Path:
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


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

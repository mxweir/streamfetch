"""Bounded, offline and read-only queries for the personal media workspace."""

from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

from streamfetch.library import MediaItem, MediaLibrary
from streamfetch.transcripts import signature


@dataclass(frozen=True)
class SearchHit:
    item: MediaItem
    kind: str
    text: str
    seconds: float | None
    identity: str


@dataclass(frozen=True)
class SearchPage:
    hits: tuple[SearchHit, ...]
    next_offset: int | None


@dataclass(frozen=True)
class ResumeItem:
    item: MediaItem
    seconds: float


@dataclass(frozen=True)
class Overview:
    total: int
    audio: int
    video: int
    resume: tuple[ResumeItem, ...]
    recent: tuple[MediaItem, ...]


@contextmanager
def _reader(library):
    """Do not create/migrate a database, even on an empty or offline folder."""
    if not library.database_path.is_file():
        yield None
        return
    db = sqlite3.connect(library.database_path.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def _tables(db):
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _available(library, row):
    item = library._item_from_row(row)
    try:
        if not item.path.resolve().is_relative_to(library.root) or not item.path.is_file():
            return None
    except OSError:
        return None
    return item


def _position(value, duration):
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    if duration is not None and math.isfinite(duration) and duration > 0:
        value = min(value, max(0.0, duration - 0.25))
    return value


def overview(library: MediaLibrary, limit: int = 6) -> Overview:
    limit = min(24, max(1, int(limit)))
    with _reader(library) as db:
        if db is None or "media_items" not in _tables(db):
            return Overview(0, 0, 0, (), ())
        counts = db.execute("""SELECT COUNT(*),
            COALESCE(SUM(media_type='audio'),0), COALESCE(SUM(media_type='video'),0)
            FROM media_items""").fetchone()
        recent = tuple(
            item
            for row in db.execute(
                "SELECT * FROM media_items ORDER BY added_at DESC,path LIMIT ?", (limit,)
            )
            if (item := _available(library, row)) is not None
        )
        resume = []
        for row in db.execute(
            """SELECT m.*,p.position_seconds FROM playback_positions p
            JOIN media_items m ON m.path=p.path
            WHERE p.position_seconds>0 AND
            (m.duration_seconds IS NULL OR p.position_seconds < m.duration_seconds-1)
            ORDER BY p.updated_at DESC,m.path LIMIT ?""",
            (limit * 4,),
        ):
            item = _available(library, row)
            seconds = _position(row["position_seconds"], row["duration_seconds"])
            if item and seconds is not None:
                resume.append(ResumeItem(item, seconds))
            if len(resume) == limit:
                break
        return Overview(*counts, tuple(resume), recent)


def search(
    library: MediaLibrary, query: str, *, limit: int = 20, offset: int = 0, kind: str = "all"
) -> SearchPage:
    """Literal substring search. Cursor offsets count candidates, not stale hits.

    At most 1,000 matching candidates are inspected per call. Old transcript
    signatures and missing media never become playable search results.
    """
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("Use a search query up to 200 characters.")
    if kind not in {"all", "metadata", "bookmark", "transcript"}:
        raise ValueError("Unknown search category.")
    if not isinstance(offset, int) or not 0 <= offset <= 10_000_000:
        raise ValueError("Invalid search cursor.")
    limit = min(100, max(1, int(limit)))
    query = query.strip()
    if not query:
        return SearchPage((), None)
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    with _reader(library) as db:
        if db is None or "media_items" not in (tables := _tables(db)):
            return SearchPage((), None)
        queries, parameters = [], []
        if kind in {"all", "metadata"}:
            queries.append("""SELECT m.*, 'metadata' AS kind, '' AS text,
                NULL AS seconds, m.path AS identity, NULL AS signature
                FROM media_items m WHERE
                COALESCE(custom_title,title) LIKE ? ESCAPE '\\' OR
                COALESCE(custom_artist,artist) LIKE ? ESCAPE '\\' OR
                COALESCE(custom_album,album) LIKE ? ESCAPE '\\' OR
                m.path LIKE ? ESCAPE '\\' OR tags_json LIKE ? ESCAPE '\\'""")
            parameters.extend([pattern] * 5)
        if kind in {"all", "bookmark"} and "bookmarks" in tables:
            queries.append("""SELECT m.*, 'bookmark' AS kind, b.label AS text,
                b.seconds, CAST(b.id AS TEXT) AS identity, NULL AS signature
                FROM bookmarks b JOIN media_items m ON m.path=b.path
                WHERE b.label LIKE ? ESCAPE '\\'""")
            parameters.append(pattern)
        if kind in {"all", "transcript"} and {"transcripts", "transcript_segments"} <= tables:
            queries.append("""SELECT m.*, 'transcript' AS kind, s.text,
                s.start AS seconds, CAST(s.id AS TEXT) AS identity,t.signature
                FROM transcript_segments s JOIN transcripts t ON t.path=s.path
                JOIN media_items m ON m.path=s.path
                WHERE t.status='ready' AND s.text LIKE ? ESCAPE '\\'""")
            parameters.append(pattern)
        if not queries:
            return SearchPage((), None)
        sql = (
            "SELECT * FROM ("
            + " UNION ALL ".join(queries)
            + ") ORDER BY kind,path,seconds,identity LIMIT ? OFFSET ?"
        )
        hits, checked, cursor = [], 0, offset
        while checked < 1000:
            rows = db.execute(sql, (*parameters, 100, cursor)).fetchall()
            if not rows:
                return SearchPage(tuple(hits), None)
            for row in rows:
                item = _available(library, row)
                valid = item is not None
                seconds = None
                if row["kind"] != "metadata":
                    seconds = _position(row["seconds"], row["duration_seconds"])
                    valid = valid and seconds is not None
                if valid and row["kind"] == "transcript":
                    try:
                        valid = signature(item.path) == row["signature"]
                    except OSError:
                        valid = False
                    duration = item.duration_seconds
                    if duration and row["seconds"] >= duration:
                        valid = False
                if valid:
                    if len(hits) == limit:
                        return SearchPage(tuple(hits), cursor)
                    hits.append(
                        SearchHit(
                            item,
                            row["kind"],
                            row["text"],
                            seconds,
                            f"{row['kind']}:{row['identity']}",
                        )
                    )
                cursor += 1
                checked += 1
            if len(rows) < 100:
                return SearchPage(tuple(hits), None)
        return SearchPage(tuple(hits), cursor)

"""Typed models shared by the UI and downloader service."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class MediaType(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"


@dataclass(frozen=True)
class DownloadRequest:
    urls: tuple[str, ...]
    output_dir: Path
    media_type: MediaType
    container: str
    quality: str
    allow_playlists: bool = True
    max_items: int | None = 50
    embed_metadata: bool = True
    embed_thumbnail: bool = True
    embed_subtitles: bool = False
    subtitle_languages: tuple[str, ...] = ("en",)
    cookie_browser: str | None = None


@dataclass(frozen=True)
class ProgressEvent:
    status: str
    message: str
    progress: float | None = None
    filename: str | None = None


@dataclass(frozen=True)
class PreviewEntry:
    title: str
    duration: int | None = None
    webpage_url: str | None = None


@dataclass(frozen=True)
class SourcePreview:
    title: str
    source_type: str
    uploader: str | None
    entry_count: int | None
    entries: tuple[PreviewEntry, ...] = ()
    thumbnail: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True)
class DownloadResult:
    output_dir: Path
    files: tuple[Path, ...]
    started_at: float
    finished_at: float

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self.finished_at - self.started_at)

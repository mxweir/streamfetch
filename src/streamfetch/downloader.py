"""Thin, testable wrapper around yt-dlp's Python API."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import build_ydl_options, new_media_files, validate_media_url
from .models import DownloadRequest, DownloadResult, PreviewEntry, ProgressEvent, SourcePreview

ProgressCallback = Callable[[ProgressEvent], None]


class DownloaderError(RuntimeError):
    """Friendly wrapper for downloader and extractor failures."""


class Downloader:
    def inspect(self, url: str, limit: int = 12) -> SourcePreview:
        validate_media_url(url)
        yt_dlp = _import_yt_dlp()
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "playlistend": limit,
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:  # yt-dlp exposes many extractor-specific errors
            raise DownloaderError(str(exc)) from exc
        if not info:
            raise DownloaderError("No downloadable media was found.")
        return _preview_from_info(info)

    def download(
        self,
        request: DownloadRequest,
        callback: ProgressCallback | None = None,
    ) -> DownloadResult:
        yt_dlp = _import_yt_dlp()
        output_dir = Path(request.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        started_at = time.time()

        def hook(data: dict) -> None:
            if callback is None:
                return
            status = data.get("status", "working")
            filename = data.get("filename") or data.get("info_dict", {}).get("title")
            if status == "downloading":
                downloaded = data.get("downloaded_bytes", 0)
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                progress = min(downloaded / total, 1.0) if total else None
                callback(ProgressEvent(status, "Downloading", progress, filename))
            elif status == "finished":
                callback(
                    ProgressEvent(status, "Download finished; processing media", 1.0, filename)
                )
            elif status == "error":
                callback(ProgressEvent(status, "A download failed", None, filename))

        options = build_ydl_options(request, hook)
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                error_code = ydl.download(list(request.urls))
        except Exception as exc:
            raise DownloaderError(str(exc)) from exc
        if error_code not in (None, 0):
            raise DownloaderError(
                "One or more downloads failed. Check the URL, network, cookies, and FFmpeg setup."
            )

        finished_at = time.time()
        files = new_media_files(output_dir, started_at)
        return DownloadResult(output_dir, files, started_at, finished_at)


def _preview_from_info(info: dict[str, Any]) -> SourcePreview:
    raw_entries = info.get("entries") or []
    entries = tuple(
        PreviewEntry(
            title=entry.get("title") or "Untitled",
            duration=entry.get("duration"),
            webpage_url=entry.get("webpage_url") or entry.get("url"),
        )
        for entry in raw_entries
        if entry
    )
    count = info.get("playlist_count") or info.get("n_entries")
    if count is None and entries:
        count = len(entries)
    source_type = info.get("_type") or ("playlist" if entries else "video")
    return SourcePreview(
        title=info.get("title") or "Untitled",
        source_type=source_type,
        uploader=info.get("uploader") or info.get("channel"),
        entry_count=count,
        entries=entries,
        thumbnail=info.get("thumbnail"),
        raw=info,
    )


def _import_yt_dlp():
    try:
        import yt_dlp
    except ImportError as exc:
        raise DownloaderError(
            "yt-dlp is not installed. Install the project dependencies first."
        ) from exc
    return yt_dlp

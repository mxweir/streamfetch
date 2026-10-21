"""Thin, testable wrapper around yt-dlp's Python API."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
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
        return _preview_from_info(info, source_url=url)

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
                callback(
                    ProgressEvent(
                        status,
                        "Downloading",
                        progress,
                        filename,
                        data.get("speed"),
                        data.get("eta"),
                    )
                )
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


def _preview_from_info(info: dict[str, Any], source_url: str = "") -> SourcePreview:
    raw_entries = info.get("entries") or []
    entries = tuple(
        PreviewEntry(
            title=entry.get("title") or "Untitled",
            duration=entry.get("duration"),
            webpage_url=_entry_url(entry, source_url),
            identifier=entry.get("id"),
            size_bytes=entry.get("filesize") or entry.get("filesize_approx"),
        )
        for entry in raw_entries
        if entry
    )
    count = info.get("playlist_count") or info.get("n_entries")
    if count is None and entries:
        count = len(entries)
    source_type = info.get("_type") or ("playlist" if entries else "video")
    return SourcePreview(
        source_url=source_url,
        title=info.get("title") or "Untitled",
        source_type=source_type,
        uploader=info.get("uploader") or info.get("channel"),
        entry_count=count,
        entries=entries,
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        size_bytes=info.get("filesize") or info.get("filesize_approx"),
        raw=info,
    )


def _entry_url(entry: dict[str, Any], source_url: str) -> str | None:
    value = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        return value
    identifier = entry.get("id")
    if identifier and ("youtube.com" in source_url or "youtu.be" in source_url):
        return f"https://www.youtube.com/watch?v={identifier}"
    return None


def resolve_selected_urls(
    source_urls: Sequence[str],
    previews: Sequence[SourcePreview],
    selections: Mapping[str, Sequence[str]],
) -> tuple[str, ...]:
    """Replace analyzed collections with their selected entry URLs."""

    previews_by_source = {preview.source_url: preview for preview in previews}
    result: list[str] = []
    for source_url in source_urls:
        preview = previews_by_source.get(source_url)
        ordered_entries = tuple(
            entry.webpage_url for entry in preview.entries if entry.webpage_url
        ) if preview else ()
        available = set(ordered_entries)
        if not available:
            result.append(source_url)
            continue
        result.extend(
            value for value in selections.get(source_url, ordered_entries) if value in available
        )
    return tuple(dict.fromkeys(result))


def estimate_download_bytes(
    previews: Sequence[SourcePreview],
    selected_urls: Sequence[str],
    media_type: str,
    quality: str,
) -> int | None:
    """Estimate selected output size from extractor data or conservative bitrates."""

    selected = set(selected_urls)
    total = 0
    found = False
    audio_kbps = 192 if quality == "0" else int(quality.removesuffix("K"))
    video_mbps = {
        "360p": 1.0,
        "480p": 1.8,
        "720p": 4.0,
        "1080p": 8.0,
        "1440p": 16.0,
        "2160p": 35.0,
        "best": 20.0,
    }

    def approximate(duration: int | None) -> int | None:
        if not duration:
            return None
        bits_per_second = (
            audio_kbps * 1000
            if media_type == "audio"
            else video_mbps.get(quality, 8.0) * 1_000_000
        )
        return int(duration * bits_per_second / 8)

    for preview in previews:
        matching = [
            entry
            for entry in preview.entries
            if entry.webpage_url and entry.webpage_url in selected
        ]
        if matching:
            for entry in matching:
                value = entry.size_bytes or approximate(entry.duration)
                if value:
                    total += value
                    found = True
        elif preview.source_url in selected:
            value = preview.size_bytes or approximate(preview.duration)
            if value:
                total += value
                found = True
    return total if found else None


def _import_yt_dlp():
    try:
        import yt_dlp
    except ImportError as exc:
        raise DownloaderError(
            "yt-dlp is not installed. Install the project dependencies first."
        ) from exc
    return yt_dlp

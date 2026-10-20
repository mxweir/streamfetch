"""Input validation and yt-dlp option construction."""

from __future__ import annotations

import ipaddress
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from .models import DownloadRequest, MediaType

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}

SOUNDCLOUD_HOSTS = {
    "soundcloud.com",
    "on.soundcloud.com",
    "snd.sc",
}

MediaSource = Literal["youtube", "soundcloud"]

VIDEO_CONTAINERS = {"mp4", "mkv", "webm"}
AUDIO_CONTAINERS = {"mp3", "m4a", "opus", "flac", "wav"}
VIDEO_HEIGHTS = {"best": None, "2160p": 2160, "1440p": 1440, "1080p": 1080,
                 "720p": 720, "480p": 480, "360p": 360}


class ValidationError(ValueError):
    """Raised when a user-provided download setting is invalid."""


def parse_urls(raw: str) -> tuple[str, ...]:
    """Parse, validate, and de-duplicate newline-separated media URLs."""
    values = [line.strip() for line in raw.splitlines() if line.strip()]
    if not values:
        raise ValidationError("Add at least one YouTube or SoundCloud URL.")

    urls: list[str] = []
    for value in values:
        validate_media_url(value)
        if value not in urls:
            urls.append(value)
    return tuple(urls)


def detect_source(url: str) -> MediaSource:
    """Validate a URL and return the supported media platform it belongs to."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValidationError(f"Not a valid HTTP(S) URL: {url}")

    hostname = parsed.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local):
        raise ValidationError("Local and private network addresses are not allowed.")
    if hostname in YOUTUBE_HOSTS or hostname.endswith(".youtube.com"):
        return "youtube"
    if hostname in SOUNDCLOUD_HOSTS or hostname.endswith(".soundcloud.com"):
        return "soundcloud"
    raise ValidationError(f"Only YouTube and SoundCloud URLs are supported: {url}")


def validate_media_url(url: str) -> None:
    detect_source(url)


def validate_youtube_url(url: str) -> None:
    """Validate that a URL belongs specifically to YouTube."""
    if detect_source(url) != "youtube":
        raise ValidationError(f"Only YouTube URLs are supported here: {url}")


def parse_subtitle_languages(raw: str) -> tuple[str, ...]:
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    return values or ("en",)


def build_ydl_options(
    request: DownloadRequest,
    progress_hook: Callable[[dict], None] | None = None,
) -> dict:
    """Translate a validated request into yt-dlp Python API options."""
    validate_request(request)
    output_dir = Path(request.output_dir).expanduser().resolve()

    options: dict = {
        "paths": {"home": str(output_dir)},
        "outtmpl": {
            "default": (
                "%(uploader|Unknown)s/%(playlist|Singles)s/"
                "%(playlist_index|0)05d - %(title).180B [%(id)s].%(ext)s"
            )
        },
        "windowsfilenames": True,
        "continuedl": True,
        "ignoreerrors": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 4,
        "noplaylist": not request.allow_playlists,
        "download_archive": str(output_dir / ".streamfetch-archive.txt"),
        "quiet": True,
        "no_warnings": True,
    }
    if request.max_items is not None:
        options["playlistend"] = request.max_items
    if progress_hook is not None:
        options["progress_hooks"] = [progress_hook]
    if request.cookie_browser:
        options["cookiesfrombrowser"] = (request.cookie_browser,)

    postprocessors: list[dict] = []
    if request.media_type is MediaType.AUDIO:
        options["format"] = "bestaudio/best"
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": request.container,
                "preferredquality": request.quality,
            }
        )
    else:
        options["format"] = _video_format_selector(request.container, request.quality)
        options["merge_output_format"] = request.container

    if request.embed_metadata:
        postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})
    if request.embed_thumbnail:
        options["writethumbnail"] = True
        postprocessors.append({"key": "EmbedThumbnail"})
    if request.embed_subtitles and request.media_type is MediaType.VIDEO:
        options.update(
            {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": list(request.subtitle_languages),
            }
        )
        postprocessors.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})
    if postprocessors:
        options["postprocessors"] = postprocessors
    return options


def _video_format_selector(container: str, quality: str) -> str:
    height = VIDEO_HEIGHTS[quality]
    height_filter = "" if height is None else f"[height<={height}]"
    if container == "mp4":
        return (
            f"bv*[ext=mp4]{height_filter}+ba[ext=m4a]/"
            f"b[ext=mp4]{height_filter}/bv*{height_filter}+ba/b{height_filter}/best"
        )
    if container == "webm":
        return (
            f"bv*[ext=webm]{height_filter}+ba[ext=webm]/"
            f"b[ext=webm]{height_filter}/bv*{height_filter}+ba/b{height_filter}/best"
        )
    return f"bv*{height_filter}+ba/b{height_filter}/best"


def validate_request(request: DownloadRequest) -> None:
    if not request.urls:
        raise ValidationError("At least one URL is required.")
    sources = {detect_source(url) for url in request.urls}
    if "soundcloud" in sources and request.media_type is MediaType.VIDEO:
        raise ValidationError("SoundCloud supports audio downloads only. Select Audio.")
    allowed = AUDIO_CONTAINERS if request.media_type is MediaType.AUDIO else VIDEO_CONTAINERS
    if request.container not in allowed:
        raise ValidationError(f"Unsupported {request.media_type.value} format: {request.container}")
    if request.media_type is MediaType.VIDEO and request.quality not in VIDEO_HEIGHTS:
        raise ValidationError(f"Unsupported video quality: {request.quality}")
    if request.max_items is not None and not 1 <= request.max_items <= 10_000:
        raise ValidationError("The item limit must be between 1 and 10,000.")


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def new_media_files(
    output_dir: Path,
    since: float,
    ignored: Iterable[str] = (),
) -> tuple[Path, ...]:
    ignored_names = set(ignored) | {".streamfetch-archive.txt"}
    files = [
        path
        for path in output_dir.rglob("*")
        if path.is_file()
        and path.name not in ignored_names
        and not path.name.endswith((".part", ".ytdl", ".temp"))
        and path.stat().st_mtime >= since - 1
    ]
    return tuple(sorted(files))

from pathlib import Path

import pytest

from streamfetch.config import (
    ValidationError,
    build_ydl_options,
    human_size,
    parse_subtitle_languages,
    parse_urls,
)
from streamfetch.models import DownloadRequest, MediaType


def make_request(**overrides):
    values = {
        "urls": ("https://www.youtube.com/watch?v=abc123",),
        "output_dir": Path("downloads"),
        "media_type": MediaType.VIDEO,
        "container": "mp4",
        "quality": "1080p",
    }
    values.update(overrides)
    return DownloadRequest(**values)


def test_parse_urls_deduplicates_and_preserves_order():
    raw = "https://youtu.be/abc\nhttps://www.youtube.com/watch?v=xyz\nhttps://youtu.be/abc"
    assert parse_urls(raw) == (
        "https://youtu.be/abc",
        "https://www.youtube.com/watch?v=xyz",
    )


@pytest.mark.parametrize(
    "raw",
    ["", "file:///tmp/video", "http://127.0.0.1/video", "https://example.com/video"],
)
def test_parse_urls_rejects_unsupported_sources(raw):
    with pytest.raises(ValidationError):
        parse_urls(raw)


def test_build_video_options_limits_resolution_and_playlist():
    options = build_ydl_options(make_request(max_items=25))
    assert "height<=1080" in options["format"]
    assert options["merge_output_format"] == "mp4"
    assert options["playlistend"] == 25
    assert options["noplaylist"] is False


def test_build_audio_options_adds_extractor():
    request = make_request(
        media_type=MediaType.AUDIO,
        container="mp3",
        quality="192K",
        embed_thumbnail=False,
    )
    options = build_ydl_options(request)
    extractor = options["postprocessors"][0]
    assert options["format"] == "bestaudio/best"
    assert extractor["key"] == "FFmpegExtractAudio"
    assert extractor["preferredcodec"] == "mp3"
    assert extractor["preferredquality"] == "192K"


def test_disable_playlist_and_unlimited_items():
    options = build_ydl_options(make_request(allow_playlists=False, max_items=None))
    assert options["noplaylist"] is True
    assert "playlistend" not in options


def test_subtitle_language_parsing_and_size_formatting():
    assert parse_subtitle_languages("en, de, ") == ("en", "de")
    assert parse_subtitle_languages("") == ("en",)
    assert human_size(1024) == "1.0 KB"

from pathlib import Path

import pytest

from streamfetch.config import (
    ValidationError,
    build_ydl_options,
    detect_source,
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
    ("url", "source"),
    [
        ("https://youtu.be/abc", "youtube"),
        ("https://soundcloud.com/artist/track", "soundcloud"),
        ("https://soundcloud.com/artist/sets/collection", "soundcloud"),
        ("https://on.soundcloud.com/example", "soundcloud"),
        ("https://snd.sc/example", "soundcloud"),
    ],
)
def test_detect_source_accepts_supported_urls(url, source):
    assert detect_source(url) == source


def test_parse_urls_accepts_mixed_audio_sources():
    raw = "https://youtu.be/abc\nhttps://soundcloud.com/artist/track"
    assert parse_urls(raw) == (
        "https://youtu.be/abc",
        "https://soundcloud.com/artist/track",
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


def test_soundcloud_audio_options_are_supported():
    request = make_request(
        urls=("https://soundcloud.com/artist/track",),
        media_type=MediaType.AUDIO,
        container="mp3",
        quality="192K",
    )
    assert build_ydl_options(request)["format"] == "bestaudio/best"


def test_soundcloud_video_request_is_rejected():
    request = make_request(urls=("https://soundcloud.com/artist/track",))
    with pytest.raises(ValidationError, match="audio downloads only"):
        build_ydl_options(request)


def test_disable_playlist_and_unlimited_items():
    options = build_ydl_options(make_request(allow_playlists=False, max_items=None))
    assert options["noplaylist"] is True
    assert "playlistend" not in options


def test_conflict_policy_controls_existing_files():
    overwrite = build_ydl_options(make_request(conflict_policy="overwrite"))
    assert overwrite["overwrites"] is True
    assert "download_archive" not in overwrite
    skip = build_ydl_options(make_request(conflict_policy="skip"))
    assert skip["nooverwrites"] is True
    assert skip["continuedl"] is False

    with pytest.raises(ValidationError, match="conflict policy"):
        build_ydl_options(make_request(conflict_policy="unknown"))


def test_advanced_download_options_are_forwarded():
    request = make_request(
        concurrent_fragments=8,
        rate_limit=2 * 1024 * 1024,
        download_sections=("10-40",),
        split_chapters=True,
        sponsorblock_remove=("sponsor", "intro"),
    )

    options = build_ydl_options(request)

    assert options["concurrent_fragment_downloads"] == 8
    assert options["ratelimit"] == 2 * 1024 * 1024
    assert list(options["download_ranges"]({}, None)) == [
        {"start_time": 10.0, "end_time": 40.0}
    ]
    assert options["sponsorblock_remove"] == {"sponsor", "intro"}
    assert {processor["key"] for processor in options["postprocessors"]} >= {
        "FFmpegSplitChapters",
        "FFmpegMetadata",
    }


def test_subtitle_language_parsing_and_size_formatting():
    assert parse_subtitle_languages("en, de, ") == ("en", "de")
    assert parse_subtitle_languages("") == ("en",)
    assert human_size(1024) == "1.0 KB"

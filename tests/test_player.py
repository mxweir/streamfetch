from pathlib import Path

from streamfetch.library import MediaItem, QueueEntry
from streamfetch.player import (
    PLAYER_HTML,
    PLAYER_JS,
    build_player_data,
    media_mime_type,
    media_url,
)


class FakeMediaManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def add(self, path: str, mime_type: str, coordinate: str) -> str:
        self.calls.append((path, mime_type, coordinate))
        return f"/media/{Path(path).name}"


def media_item(path: str, media_type: str = "audio", format_name: str = "MP3") -> MediaItem:
    return MediaItem(
        path=Path(path),
        title=Path(path).stem.title(),
        artist="Open Audio",
        album="Player Tests",
        duration_seconds=30.0,
        size_bytes=1024,
        media_type=media_type,
        format=format_name,
        modified_at=1.0,
        added_at=1.0,
    )


def test_media_mime_type_supports_audio_and_video() -> None:
    assert media_mime_type(media_item("track.opus", format_name="OPUS")) == "audio/ogg"
    assert (
        media_mime_type(media_item("clip.webm", media_type="video", format_name="WEBM"))
        == "video/webm"
    )


def test_media_url_registers_local_file() -> None:
    manager = FakeMediaManager()
    item = media_item("/tmp/track.mp3")

    url = media_url(item, "player-current", manager)

    assert url == "/media/track.mp3"
    assert manager.calls == [("/tmp/track.mp3", "audio/mpeg", "player-current")]


def test_build_player_data_preloads_next_queue_entry() -> None:
    manager = FakeMediaManager()
    current = media_item("/music/current.mp3")
    queued = QueueEntry(42, media_item("/music/next.mp3"))

    data = build_player_data(
        current,
        (queued,),
        favorite=True,
        can_previous=False,
        autoplay=True,
        repeat_mode="all",
        crossfade_seconds=4,
        resume_position=12.5,
        visualizer_mode="spectrum",
        labels={"shuffle": "MISCHEN"},
        media_manager=manager,
        playback_speed=1.5,
        seek_request={"nonce": "test", "seconds": 8, "path": str(current.path)},
        library_key="local-test-library",
    )

    assert data["current"]["url"] == "/media/current.mp3"
    assert data["next"]["url"] == "/media/next.mp3"
    assert data["next"]["entry_id"] == 42
    assert data["favorite"] is True
    assert data["can_previous"] is False
    assert data["autoplay"] is True
    assert data["queue_count"] == 1
    assert data["repeat_mode"] == "all"
    assert data["crossfade_seconds"] == 4
    assert data["resume_position"] == 12.5
    assert data["playback_speed"] == 1.5
    assert data["seek_request"]["seconds"] == 8
    assert data["library_key"] == "local-test-library"
    assert data["visualizer_mode"] == "spectrum"
    assert data["labels"]["shuffle"] == "MISCHEN"
    assert data["queue"] == [
        {"entry_id": 42, "title": "Next", "artist": "Open Audio"}
    ]
    assert [call[2] for call in manager.calls] == [
        "streamfetch-player-current",
        "streamfetch-player-next",
    ]


def test_build_player_data_without_queue_has_no_next_track() -> None:
    data = build_player_data(
        media_item("/music/current.mp3"),
        (),
        favorite=False,
        can_previous=True,
        autoplay=False,
        repeat_mode="off",
        crossfade_seconds=0,
        resume_position=0,
        media_manager=FakeMediaManager(),
    )

    assert data["next"] is None
    assert data["queue_count"] == 0


def test_player_is_a_floating_expandable_queue_controller() -> None:
    assert "data-expand" in PLAYER_HTML
    assert "data-shuffle" in PLAYER_HTML
    assert "data-clear" in PLAYER_HTML
    assert "data-visualizer" in PLAYER_HTML
    assert "createAnalyser" in PLAYER_JS
    assert 'emit("visualization"' in PLAYER_JS
    assert 'emit("remove"' in PLAYER_JS
    assert 'emit("shuffle")' in PLAYER_JS
    assert 'emit("clear")' in PLAYER_JS

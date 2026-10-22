import random
import sqlite3
import wave
from concurrent.futures import ThreadPoolExecutor

import pytest

from streamfetch.library import MediaLibrary


def test_parallel_library_readers_keep_indexes_stable(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    library = MediaLibrary(tmp_path)
    library.scan()
    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(workers.map(lambda _: MediaLibrary(tmp_path).favorite_paths(), range(60)))
    assert results == [set()] * 60


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    return MediaLibrary(tmp_path)


def write_wav(path, seconds=1):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 8_000 * seconds)


def test_scan_indexes_supported_media_and_stats(library):
    write_wav(library.root / "Sample Track.wav")
    (library.root / "clip.mp4").write_bytes(b"not a real video")
    (library.root / "notes.txt").write_text("ignore me")

    summary = library.scan()
    items = library.list_items(sort="title")
    stats = library.stats()

    assert summary.added == 2
    assert summary.total == 2
    assert [item.title for item in items] == ["clip", "Sample Track"]
    assert items[1].duration_seconds == pytest.approx(1.0)
    assert stats.total == 2
    assert stats.audio == 1
    assert stats.video == 1
    assert stats.size_bytes > 0
    assert library.database_path.exists()


def test_search_filter_and_rescan_remove_missing_files(library):
    first = library.root / "First Song.mp3"
    second = library.root / "Second Song.flac"
    video = library.root / "concert.webm"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    video.write_bytes(b"three")
    library.scan()

    assert library.count_items(search="Second") == 1
    assert [item.path.name for item in library.list_items(media_type="video")] == [
        "concert.webm"
    ]

    first.unlink()
    replacement = library.root / "Replacement Song.mp3"
    replacement.write_bytes(b"new")
    summary = library.scan()

    assert summary.added == 1
    assert summary.removed == 1
    assert summary.total == 3
    assert library.count_items(search="First") == 0


def test_rescan_updates_changed_file_without_resetting_library(library):
    track = library.root / "changing.mp3"
    track.write_bytes(b"before")
    library.scan()
    track.write_bytes(b"after and larger")

    summary = library.scan()

    assert summary.added == 0
    assert summary.updated == 1
    assert summary.removed == 0
    assert library.list_items()[0].size_bytes == len(b"after and larger")


def test_favorites_queue_and_current_item_persist(library):
    first = library.root / "first.mp3"
    second = library.root / "second.mp3"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    library.scan()

    assert library.toggle_favorite(first) is True
    library.enqueue(first)
    second_queue_id = library.enqueue(second)
    library.set_current_item(second)

    reopened = MediaLibrary(library.root)
    assert reopened.favorite_paths() == {"first.mp3"}
    assert reopened.current_item().path == second
    assert [entry.item.path.name for entry in reopened.queue()] == ["first.mp3", "second.mp3"]
    assert reopened.take_queue_entry(second_queue_id).path == second
    assert [entry.item.path.name for entry in reopened.queue()] == ["first.mp3"]
    reopened.clear_queue()
    assert reopened.queue() == ()
    assert reopened.toggle_favorite(first) is False


def test_playlists_and_history(library):
    first = library.root / "first.mp3"
    second = library.root / "second.mp3"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    library.scan()

    playlist = library.create_playlist("Road Trip")
    library.add_to_playlist(playlist.id, first)
    library.add_to_playlist(playlist.id, second)
    library.add_to_playlist(playlist.id, first)
    library.record_play(first)
    library.record_play(second)

    assert library.playlists()[0].item_count == 2
    assert [item.path.name for item in library.playlist_items(playlist.id)] == [
        "first.mp3",
        "second.mp3",
    ]
    assert [entry.item.path.name for entry in library.history()] == [
        "second.mp3",
        "first.mp3",
    ]
    assert library.previous_item(second).path == first

    library.remove_from_playlist(playlist.id, first)
    assert [item.path.name for item in library.playlist_items(playlist.id)] == ["second.mp3"]
    with pytest.raises(ValueError, match="already exists"):
        library.create_playlist("road trip")
    library.delete_playlist(playlist.id)
    assert library.playlists() == ()


def test_missing_media_cascades_through_collections(library):
    track = library.root / "temporary.mp3"
    track.write_bytes(b"temporary")
    library.scan()
    playlist = library.create_playlist("Temporary")
    library.add_to_playlist(playlist.id, track)
    library.toggle_favorite(track)
    library.enqueue(track)
    library.record_play(track)
    library.set_current_item(track)

    track.unlink()
    library.scan()

    assert library.favorite_items() == ()
    assert library.queue() == ()
    assert library.playlist_items(playlist.id) == ()
    assert library.history() == ()
    assert library.current_item() is None


def test_smart_queue_supports_play_next_reorder_shuffle_and_replace(library):
    tracks = [library.root / f"{name}.mp3" for name in ("one", "two", "three")]
    for track in tracks:
        track.write_bytes(track.stem.encode())
    library.scan()

    one_id = library.enqueue(tracks[0])
    two_id = library.enqueue(tracks[1])
    three_id = library.enqueue(tracks[2], play_next=True)
    assert [entry.item.path.name for entry in library.queue()] == [
        "three.mp3",
        "one.mp3",
        "two.mp3",
    ]

    library.reorder_queue([two_id, three_id, one_id])
    assert [entry.id for entry in library.queue()] == [two_id, three_id, one_id]
    with pytest.raises(ValueError, match="every queued item"):
        library.reorder_queue([one_id])

    library.shuffle_queue(random.Random(7))
    assert {entry.id for entry in library.queue()} == {one_id, two_id, three_id}
    library.replace_queue([tracks[2], tracks[0]])
    assert [entry.item.path.name for entry in library.queue()] == ["three.mp3", "one.mp3"]


def test_player_settings_and_resume_position_persist(library):
    track = library.root / "resume.mp3"
    track.write_bytes(b"resume")
    library.scan()

    assert library.player_setting("repeat", "off") == "off"
    assert library.playback_position(track) == 0
    library.set_player_setting("repeat", "all")
    library.set_playback_position(track, 42.5)

    reopened = MediaLibrary(library.root)
    assert reopened.player_setting("repeat", "off") == "all"
    assert reopened.playback_position(track) == 42.5
    reopened.set_playback_position(track, 0)
    assert reopened.playback_position(track) == 0


def test_metadata_smart_collections_and_artist_album_views(library):
    first = library.root / "first.mp3"
    second = library.root / "second.mp3"
    third = library.root / "third.mp3"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    third.write_bytes(b"three")
    library.scan()

    updated = library.update_metadata(
        first,
        title="First edit",
        artist="Codex Club",
        album="Local Hits",
        rating=5,
        tags=["focus", "night", "focus"],
    )
    library.update_metadata(
        second,
        title="Second edit",
        artist="Codex Club",
        album="Local Hits",
        rating=4,
        tags=["workout"],
    )
    library.record_play(first)
    library.record_play(second)
    library.record_play(first)

    assert updated.title == "First edit"
    assert updated.rating == 5
    assert updated.tags == ("focus", "night")
    assert [item.path.name for item in library.list_items(search="focus")] == ["first.mp3"]
    assert [item.path.name for item in library.most_played()] == ["first.mp3", "second.mp3"]
    assert {item.path.name for item in library.highly_rated()} == {"first.mp3", "second.mp3"}
    assert [item.path.name for item in library.unplayed()] == ["third.mp3"]
    assert library.artists()[0].name == "Codex Club"
    assert library.artists()[0].item_count == 2
    assert [item.path.name for item in library.items_for_artist("codex club")] == [
        "first.mp3",
        "second.mp3",
    ]
    assert [item.path.name for item in library.items_for_album("LOCAL HITS")] == [
        "first.mp3",
        "second.mp3",
    ]

    library.scan()
    assert library.item_for_path(first).title == "First edit"
    with pytest.raises(ValueError, match="Title cannot be empty"):
        library.update_metadata(first, title=" ", artist="", album="")
    with pytest.raises(ValueError, match="Rating"):
        library.update_metadata(first, title="Title", artist="", album="", rating=6)


def test_duplicate_detection_hashes_content(library):
    original = library.root / "original.mp3"
    copy = library.root / "copy.mp3"
    same_size = library.root / "different.mp3"
    original.write_bytes(b"same-content")
    copy.write_bytes(b"same-content")
    same_size.write_bytes(b"other-bytes!")
    library.scan()

    groups = library.duplicate_groups()

    assert len(groups) == 1
    assert {item.path.name for item in groups[0]} == {"original.mp3", "copy.mp3"}


def test_import_folder_copies_media_and_skips_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    library = MediaLibrary(tmp_path / "library")
    source = tmp_path / "source"
    (source / "Album").mkdir(parents=True)
    (source / "Album" / "song.mp3").write_bytes(b"song")
    (source / "notes.txt").write_text("ignore")

    first = library.import_folder(source)
    second = library.import_folder(source)
    summary = library.scan()

    assert first.imported == 1
    assert first.skipped == 0
    assert second.imported == 0
    assert second.skipped == 1
    assert summary.total == 1
    assert library.list_items()[0].path.relative_to(library.root).as_posix() == (
        "Imported/source/Album/song.mp3"
    )
    with pytest.raises(ValueError, match="existing folder"):
        library.import_folder("")
    with pytest.raises(ValueError, match="outside"):
        library.import_folder(library.root / "Imported")


def test_existing_database_is_migrated_for_library_annotations(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    library = MediaLibrary(tmp_path)
    library.state_dir.mkdir(parents=True)

    with sqlite3.connect(library.database_path) as connection:
        connection.execute(
            """
            CREATE TABLE media_items (
                path TEXT PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL,
                album TEXT NOT NULL, duration_seconds REAL, size_bytes INTEGER NOT NULL,
                media_type TEXT NOT NULL, format TEXT NOT NULL, modified_at REAL NOT NULL,
                added_at REAL NOT NULL, cover_path TEXT, source_url TEXT
            )
            """
        )

    assert library.stats().total == 0
    with sqlite3.connect(library.database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(media_items)")}
    assert {"custom_title", "custom_artist", "custom_album", "rating", "tags_json"} <= columns

"""Cross-feature upgrade, offline and explicit-selection release gates for 2.0."""

import hashlib
import sqlite3

import pytest
from streamlit.testing.v1 import AppTest

from streamfetch.collections import Collections
from streamfetch.inbox import InboxStore
from streamfetch.library import MediaLibrary
from streamfetch.listening import ListeningLibrary
from streamfetch.transcripts import TranscriptStore
from streamfetch.workspace import overview, search


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    root = tmp_path / "media"
    root.mkdir()
    (root / "existing.mp3").write_bytes(b"existing original media")
    library = MediaLibrary(root)
    library.scan()
    with library._connection() as db:
        db.execute("UPDATE media_items SET duration_seconds=3600")
    return library


def test_new_queries_preserve_existing_library_bytes_and_user_state(library, monkeypatch):
    """1.9 state must be readable without migrations, probes or transcription."""
    item = library.list_items()[0]
    library.update_metadata(
        item.path, title="Personal needle", artist="Existing artist", album="Existing album",
        tags=["Keep"], rating=5
    )
    Collections(library).apply([item.path], "favorite")
    Collections(library).apply([item.path], "queue")
    Collections(library).apply([item.path], "playlist", playlist_name="Existing collection")
    library.set_playback_position(item.path, 42)
    ListeningLibrary(library).add_bookmark(item.path, 17, "needle bookmark")
    TranscriptStore(library).save(
        item.path, [{"start": 22, "end": 23, "text": "needle transcript"}]
    )
    before = hashlib.sha256(library.database_path.read_bytes()).digest()
    originals = item.path.read_bytes()

    def unexpected(*args, **kwargs):
        pytest.fail("A read-only workspace query attempted a mutating/probing connection")

    monkeypatch.setattr(library, "_connection", unexpected)
    monkeypatch.setattr("streamfetch.transcripts.TranscriptStore.__init__", unexpected)
    for _ in range(2):
        assert overview(library).resume[0].seconds == 42
        assert {hit.kind for hit in search(library, "needle").hits} == {
            "metadata", "bookmark", "transcript"
        }
    assert hashlib.sha256(library.database_path.read_bytes()).digest() == before
    assert item.path.read_bytes() == originals
    reopened = MediaLibrary(library.root)
    assert reopened.favorite_paths() == {"existing.mp3"}
    assert reopened.queue()[0].item.title == "Personal needle"
    assert reopened.playlists()[0].item_count == 1
    assert reopened.list_items()[0].rating == 5


def test_search_bounded_stale_page_cursor_reaches_valid_candidates(library):
    """The 1,000-candidate budget cannot make later matches inaccessible."""
    item = library.list_items()[0]
    TranscriptStore(library).save(item.path, [
        {"start": i, "end": i + 1, "text": "needle"} for i in range(1007)
    ])
    with library._connection() as db:
        db.execute("UPDATE transcript_segments SET start=-1 WHERE id <= 1002")
    first = search(library, "needle", kind="transcript", limit=3)
    assert not first.hits
    assert first.next_offset == 1000
    second = search(library, "needle", kind="transcript", limit=3, offset=first.next_offset)
    assert len(second.hits) == 3
    third = search(library, "needle", kind="transcript", limit=3, offset=second.next_offset)
    assert len(third.hits) == 2 and third.next_offset is None
    assert len({hit.identity for hit in (*second.hits, *third.hits)}) == 5


def test_inbox_handoff_does_not_create_jobs_or_touch_library(tmp_path, library):
    """Capture/review remains a plan; it must not silently start any download."""
    original = library.database_path.read_bytes()
    state = tmp_path / "state"
    store = InboxStore(state)
    store.add_batch("https://youtu.be/aqz-KE-bpKQ", "Review before downloading")
    entry, = store.list_entries()
    assert store.handoff([entry.id]) == ("https://www.youtube.com/watch?v=aqz-KE-bpKQ",)
    reviewed, = InboxStore(state).list_entries()
    assert reviewed.status == "handed_off" and reviewed.job_ids == ()
    assert library.database_path.read_bytes() == original
    assert {path.name for path in state.iterdir()} == {"inbox.db"}
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_collection_filter_from_last_page_keeps_explicit_selection(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    root = tmp_path / "media"
    root.mkdir()
    for index in range(28):
        (root / f"track-{index:03d}.mp3").write_bytes(b"original")
    app = AppTest.from_string(f"""
from pathlib import Path
from streamfetch.library import MediaLibrary
from streamfetch.collections_ui import render_collections
library=MediaLibrary(Path({str(root)!r}))
library.scan()
render_collections(library, lambda value: value)
""", default_timeout=15).run()
    app.selectbox(key="collections_sort").select("title").run()
    app.selectbox(key="collections_page").select(2).run()
    app.button(key="collections_select_page").click().run()
    selected = list(app.session_state["collections_selected"])
    assert len(selected) == 3
    app.text_input(key="collections_search").input("track-000").run()
    assert not app.exception
    assert app.selectbox(key="collections_page").value == 1
    assert list(app.session_state["collections_selected"]) == selected
    app.button(key="collections_favorite").click().run()
    assert not app.exception
    assert MediaLibrary(root).favorite_paths() == set(selected)

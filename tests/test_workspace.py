import math

import pytest
from streamlit.testing.v1 import AppTest

from streamfetch.library import MediaLibrary
from streamfetch.listening import ListeningLibrary
from streamfetch.transcripts import TranscriptStore
from streamfetch.workspace import overview, search


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    library = MediaLibrary(tmp_path)
    (tmp_path / "Track 100%_best.mp3").write_bytes(b"sample")
    library.scan()
    item = library.list_items()[0]
    library.update_metadata(
        item.path, title="Track 100%_best", artist="Artist", album="Album", tags=["Jazz"]
    )
    with library._connection() as db:
        db.execute("UPDATE media_items SET duration_seconds=120")
    return library


def test_metadata_search_literal_and_fields(library):
    for query in ["100%_", "Artist", "Album", "Jazz", "best.mp3"]:
        assert len(search(library, query).hits) == 1
    assert not search(library, "x' OR 1=1 --").hits
    assert not search(library, "\\").hits
    assert not search(library, "").hits
    with pytest.raises(ValueError):
        search(library, "x" * 201)
    with pytest.raises(ValueError):
        search(library, "Track", offset=-1)
    with pytest.raises(ValueError):
        search(library, "Track", kind="invalid")


def test_bookmarks_and_transcript_exact_positions(library):
    path = library.list_items()[0].path
    ListeningLibrary(library).add_bookmark(path, 24.5, "The 100%_ moment")
    TranscriptStore(library).save(path, [{"start": 42.75, "end": 44, "text": "The 100%_ moment"}])
    hits = search(library, "100%_").hits
    assert {hit.kind for hit in hits} == {"metadata", "bookmark", "transcript"}
    assert {hit.kind: hit.seconds for hit in hits} == {
        "metadata": None,
        "bookmark": 24.5,
        "transcript": 42.75,
    }
    assert len(search(library, "moment", kind="transcript").hits) == 1
    assert len(search(library, "moment", kind="bookmark").hits) == 1
    assert not search(library, "100%_not").hits


def test_stale_missing_and_not_ready_transcripts_excluded(library):
    path = library.list_items()[0].path
    store = TranscriptStore(library)
    store.save(path, [{"start": 1, "end": 2, "text": "needle"}])
    path.write_bytes(b"changed length")
    assert not search(library, "needle").hits
    store.save(path, [{"start": 1, "end": 2, "text": "needle"}])
    store.set_status(path, "failed", "tiny")
    assert not search(library, "needle").hits
    store.save(path, [{"start": 1, "end": 2, "text": "needle"}])
    path.unlink()
    assert not search(library, "needle").hits
    assert not search(library, "Track").hits


def test_search_pagination_has_no_repeat_or_missing_hit(library):
    path = library.list_items()[0].path
    store = TranscriptStore(library)
    store.save(path, [{"start": index, "end": index + 1, "text": "needle"} for index in range(65)])
    hits, offset = [], 0
    while True:
        page = search(library, "needle", limit=7, offset=offset)
        assert len(page.hits) <= 7
        hits.extend(page.hits)
        if page.next_offset is None:
            break
        assert page.next_offset > offset
        offset = page.next_offset
    assert len(hits) == len({hit.identity for hit in hits}) == 65


def test_missing_optional_tables_and_uninitialized_database(tmp_path, library):
    assert search(library, "Track", kind="transcript").hits == ()
    assert search(library, "Track", kind="bookmark").hits == ()
    empty = MediaLibrary(tmp_path / "does-not-exist")
    assert overview(empty).total == 0
    assert search(empty, "anything").hits == ()
    assert not empty.root.exists()


def test_clipped_bookmarks_invalid_positions_and_out_of_bounds_transcript(library):
    path = library.list_items()[0].path
    ListeningLibrary(library).add_bookmark(path, 1000, "needle")
    TranscriptStore(library).save(path, [{"start": 200, "end": 201, "text": "needle"}])
    hits = search(library, "needle").hits
    assert len(hits) == 1
    assert hits[0].seconds == 119.75
    with library._connection() as db:
        db.execute("UPDATE bookmarks SET seconds=?", (math.inf,))
    assert not search(library, "needle").hits


def test_overview_real_resume_and_completed_positions(library):
    path = library.list_items()[0].path
    assert not overview(library).resume
    library.set_playback_position(path, 35.2)
    data = overview(library)
    assert (data.total, data.audio, data.video) == (1, 1, 0)
    assert data.resume[0].seconds == 35.2
    assert data.recent[0].path == path
    library.set_playback_position(path, 120)
    assert not overview(library).resume
    path.unlink()
    assert not overview(library).recent


def _app(library, view):
    return AppTest.from_string(f"""
from pathlib import Path
from types import SimpleNamespace
import streamlit as st
from streamfetch.library import MediaLibrary
from streamfetch.workspace_ui import render_overview, render_search
library = MediaLibrary(Path({str(library.root)!r}))
def t(value): return value
def play(item,seconds): st.session_state['played']=(item.title,seconds)
def navigate(workspace,section=None): st.session_state['navigated']=(workspace,section)
manager=SimpleNamespace(snapshots=lambda: ())
{view}
""", default_timeout=15).run()


def test_overview_ui_callbacks(library):
    library.set_playback_position(library.list_items()[0].path, 33)
    app = _app(library, "render_overview(library,manager,t,navigate,play)")
    assert not app.exception
    app.button(key="overview-resume-0").click().run()
    assert app.session_state["played"][1] == 33
    app.button(key="overview-go-studio").click().run()
    assert app.session_state["navigated"] == ("studio", "sharing")


def test_search_ui_bookmark_seek_and_query_reset(library):
    ListeningLibrary(library).add_bookmark(library.list_items()[0].path, 22.25, "needle")
    app = _app(library, "render_search(library,t,play)")
    assert not app.exception
    app.text_input(key="workspace-query").input("needle").run()
    assert not app.exception
    app.button(key="search-bookmark:1").click().run()
    assert app.session_state["played"][1] == 22.25
    app.text_input(key="workspace-query").input("nothing matches").run()
    assert not app.exception
    assert app.session_state["workspace-search-offset"] == 0


def test_empty_overview_ui(tmp_path):
    app = _app(
        MediaLibrary(tmp_path / "absent"), "render_overview(library,manager,t,navigate,play)"
    )
    assert not app.exception
    assert app.info


def test_stale_candidates_do_not_hide_later_valid_page(library):
    path = library.list_items()[0].path
    TranscriptStore(library).save(
        path, [{"start": i, "end": i + 1, "text": "needle"} for i in range(110)]
    )
    # Invalid timestamps may come from an older/imported database. They cannot
    # consume the result page or cause the next cursor to repeat valid entries.
    with library._connection() as db:
        db.execute("UPDATE transcript_segments SET start=-1 WHERE id <= 105")
    first = search(library, "needle", limit=3)
    assert len(first.hits) == 3
    second = search(library, "needle", limit=3, offset=first.next_offset)
    assert len(second.hits) == 2
    assert second.next_offset is None
    assert not {hit.identity for hit in first.hits} & {hit.identity for hit in second.hits}


def test_search_ui_page_navigation(library):
    path = library.list_items()[0].path
    TranscriptStore(library).save(
        path, [{"start": i, "end": i + 1, "text": "needle"} for i in range(25)]
    )
    app = _app(library, "render_search(library,t,play)")
    app.text_input(key="workspace-query").input("needle").run()
    app.button(key="search-next").click().run()
    assert not app.exception
    assert app.session_state["workspace-search-offset"] == 20
    app.button(key="search-previous").click().run()
    assert not app.exception
    assert app.session_state["workspace-search-offset"] == 0

from streamlit.testing.v1 import AppTest


def test_collections_ui_render_select_and_bulk(tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMFETCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    root = tmp_path / "media"
    root.mkdir()
    (root / "track.mp3").write_bytes(b"original")
    source = f"""
from pathlib import Path
from streamfetch.library import MediaLibrary
from streamfetch.collections_ui import render_collections
library = MediaLibrary(Path({str(root)!r}))
library.scan()
render_collections(library, lambda value: value)
"""
    app = AppTest.from_string(source, default_timeout=15).run()
    assert not app.exception
    app.button(key="collections_select_page").click().run()
    assert not app.exception
    assert app.session_state["collections_selected"] == ["track.mp3"]
    app.button(key="collections_favorite").click().run()
    assert not app.exception
    assert "Tracks updated: 1" in [result.value for result in app.success]
    app.button(key="collections_export").click().run()
    assert not app.exception
    artifact = app.session_state["collections_export_artifact"]
    assert artifact.path.is_file()
    app.button(key="collections_remove_export").click().run()
    assert not app.exception
    assert not artifact.path.exists()


def test_selection_persists_across_pages_and_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMFETCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    root = tmp_path / "media"
    root.mkdir()
    for index in range(31):
        (root / f"track-{index:03d}.mp3").write_bytes(b"original")
    source = f"""
from pathlib import Path
from streamfetch.library import MediaLibrary
from streamfetch.collections_ui import render_collections
library = MediaLibrary(Path({str(root)!r}))
library.scan()
render_collections(library, lambda value: value)
"""
    app = AppTest.from_string(source, default_timeout=15).run()
    app.selectbox(key="collections_sort").select("title").run()
    app.button(key="collections_select_page").click().run()
    first = list(app.session_state["collections_selected"])
    assert len(first) == 25
    app.selectbox(key="collections_page").select(2).run()
    app.button(key="collections_select_page").click().run()
    selected = list(app.session_state["collections_selected"])
    assert selected[:25] == first and len(selected) == 31
    app.selectbox(key="collections_page").select(1).run()
    assert list(app.session_state["collections_selected"]) == selected
    app.text_input(key="collections_search").input("no results").run()
    assert not app.exception
    assert list(app.session_state["collections_selected"]) == selected
    app.button(key="collections_clear").click().run()
    assert app.session_state["collections_selected"] == []


def test_failed_rebuild_keeps_previous_downloadable_export(tmp_path, monkeypatch):
    from streamfetch.collections import Collections

    monkeypatch.setenv("STREAMFETCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    root = tmp_path / "media"
    root.mkdir()
    (root / "track.mp3").write_bytes(b"original")
    source = f"""
from pathlib import Path
from streamfetch.library import MediaLibrary
from streamfetch.collections_ui import render_collections
library = MediaLibrary(Path({str(root)!r}))
library.scan()
render_collections(library, lambda value: value)
"""
    app = AppTest.from_string(source, default_timeout=15).run()
    app.button(key="collections_select_page").click().run()
    app.button(key="collections_export").click().run()
    previous = app.session_state["collections_export_artifact"]
    original_export = Collections.export

    def fail(*args, **kwargs):
        raise OSError("Disk full")

    monkeypatch.setattr(Collections, "export", fail)
    app.button(key="collections_export").click().run()
    assert not app.exception
    assert app.session_state["collections_export_artifact"] == previous
    assert previous.path.is_file()
    monkeypatch.setattr(Collections, "export", original_export)
    app.button(key="collections_export").click().run()
    assert not app.exception
    assert app.session_state["collections_export_artifact"] != previous
    assert not previous.path.exists()

from streamlit.testing.v1 import AppTest

from streamfetch.inbox import InboxStore

SOURCE = """
import streamlit as st
from streamfetch.inbox_ui import render_inbox
def t(text, **values):
    return text.format(**values)
def opened(urls):
    st.session_state.opened_urls = urls
render_inbox(t, opened)
"""


def test_inbox_capture_review_and_note(tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMFETCH_STATE_DIR", str(tmp_path))
    app = AppTest.from_string(SOURCE, default_timeout=15).run()
    assert not app.exception
    app.text_area(key="inbox_links").set_value("https://youtu.be/aqz-KE-bpKQ")
    app.text_input(key="inbox_new_note").set_value("Film night")
    next(b for b in app.button if b.label == "Save to inbox").click().run()
    assert not app.exception
    entry, = InboxStore(tmp_path).list_entries()
    app.multiselect(key="inbox_selected").select(entry.id).run()
    app.button(key="inbox_handoff").click().run()
    assert not app.exception
    assert app.session_state.opened_urls == (entry.url,)
    assert InboxStore(tmp_path).list_entries()[0].status == "handed_off"


def test_inbox_invalid_batch_has_no_partial_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMFETCH_STATE_DIR", str(tmp_path))
    app = AppTest.from_string(SOURCE, default_timeout=15).run()
    app.text_area(key="inbox_links").set_value(
        "https://youtu.be/aqz-KE-bpKQ\nhttps://evil.test/file")
    next(b for b in app.button if b.label == "Save to inbox").click().run()
    assert not app.exception
    assert app.error
    assert not InboxStore(tmp_path).list_entries()


def test_inbox_note_archive_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMFETCH_STATE_DIR", str(tmp_path))
    store = InboxStore(tmp_path)
    store.add_batch("https://soundcloud.com/artist/track")
    entry, = store.list_entries()
    app = AppTest.from_string(SOURCE, default_timeout=15).run()
    app.text_area(key=f"inbox_note_{entry.id}").set_value("Keep this recording")
    next(b for b in app.button if b.label == "Save note").click().run()
    assert not app.exception
    assert store.list_entries()[0].note == "Keep this recording"
    app.multiselect(key="inbox_selected").select(entry.id).run()
    app.button(key="inbox_archive").click().run()
    assert not app.exception
    assert store.list_entries()[0].status == "archived"
    app.selectbox(key="inbox_status").set_value("archived").run()
    app.multiselect(key="inbox_selected").select(entry.id).run()
    app.button(key="inbox_restore").click().run()
    assert not app.exception
    assert store.list_entries()[0].status == "ready"

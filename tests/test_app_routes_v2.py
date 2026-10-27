"""Exercise 2.0 routing through the real Streamlit entry point, not a mock page."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from streamfetch.engine_updates import EngineStatus
from streamfetch.i18n import translate
from streamfetch.inbox import InboxStore
from streamfetch.library import MediaLibrary
from streamfetch.listening import ListeningLibrary
from streamfetch.settings import AppSettings, save_settings


@pytest.fixture(params=["English", "Deutsch"])
def app_context(tmp_path, monkeypatch, request):
    state = tmp_path / "state"
    root = tmp_path / "media"
    root.mkdir()
    (root / "existing.mp3").write_bytes(b"tiny existing original")
    monkeypatch.setenv("STREAMFETCH_STATE_DIR", str(state))
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    save_settings(AppSettings(
        first_run_completed=True, language=request.param, download_dir=str(root),
        check_updates=False, auto_update=False,
    ))
    library = MediaLibrary(root)
    library.scan()
    with library._connection() as db:
        db.execute("UPDATE media_items SET duration_seconds=120")
    ListeningLibrary(library).add_bookmark("existing.mp3", 27.5, "needle moment")
    # Disable external work only; all navigation and surface rendering stay real.
    monkeypatch.setattr("streamfetch.engine_updates.ensure_engine", lambda: None)
    monkeypatch.setattr("streamfetch.engine_updates.engine_status", lambda: EngineStatus("test"))
    monkeypatch.setattr("streamfetch.system.run_health_checks", lambda *_: ())
    monkeypatch.setattr("streamfetch.studio_ui.folder_watcher", lambda *_: None)
    monkeypatch.setattr("streamfetch.subscriptions.SubscriptionService", lambda *_: object())
    monkeypatch.setattr(
        "streamfetch.studio_ui.sharing_service", lambda: SimpleNamespace(player=None)
    )
    monkeypatch.setattr("streamfetch.studio_ui.local_address", lambda: "127.0.0.1")
    monkeypatch.setattr("streamfetch.player.render_continuous_player", lambda *_: None)
    # AppTest evaluates widget format_func again outside ScriptRunContext, where
    # session_state has no language. Preserve the fixture locale in that case;
    # actual app rendering continues to pass its real session language.
    monkeypatch.setattr(
        "streamfetch.i18n.translate",
        lambda text, language=None, **values: translate(
            text, language or request.param, **values
        ),
    )
    submitted = []

    def unexpected_submit(self, download):
        submitted.append(download)
        pytest.fail("Navigation must not enqueue an implicit download")

    monkeypatch.setattr("streamfetch.jobs.DownloadJobManager.submit", unexpected_submit)
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15
    ).run()
    assert not app.exception
    return app, library, state, request.param, submitted


def test_overview_inbox_review_opens_real_download_without_jobs(app_context):
    app, library, state, language, submitted = app_context
    assert translate("Your media, ready when you are", language) in [h.value for h in app.header]
    app.button(key="overview-go-inbox").click().run()
    assert not app.exception
    assert app.session_state["workspace"] == "Inbox"
    app.text_area(key="inbox_links").input("https://youtu.be/aqz-KE-bpKQ")
    save = next(
        button for button in app.button if button.label == translate("Save to inbox", language)
    )
    save.click().run()
    entry, = InboxStore(state).list_entries()
    app.multiselect(key="inbox_selected").select(entry.id).run()
    app.button(key="inbox_handoff").click().run()
    assert not app.exception
    assert app.session_state["workspace"] == "Download"
    assert app.text_area(key="download_urls").value == entry.url
    assert InboxStore(state).list_entries()[0].status == "handed_off"
    assert InboxStore(state).list_entries()[0].job_ids == ()
    assert not submitted
    assert library.list_items()[0].path.read_bytes() == b"tiny existing original"


def test_home_network_shortcut_targets_actual_studio_home_player(app_context):
    app, _, _, language, submitted = app_context
    app.button(key="overview-go-studio").click().run()
    assert not app.exception
    assert app.session_state["workspace"] == "Library"
    assert app.session_state["library_section"] == "Studio"
    assert app.session_state["studio_section"] == "Home player"
    assert translate("Start home player", language) in [button.label for button in app.button]
    assert not submitted


def test_global_search_bookmark_opens_library_and_seeks_exact_moment(app_context):
    app, library, _, language, submitted = app_context
    app.radio(key="workspace").set_value("Search").run()
    assert not app.exception
    app.text_input(key="workspace-query").input("needle moment").run()
    assert not app.exception
    app.button(key="search-bookmark:1").click().run()
    assert not app.exception
    assert app.session_state["workspace"] == "Library"
    assert app.session_state["player_seek_request"]["seconds"] == 27.5
    assert app.session_state["player_seek_request"]["path"] == str(library.root / "existing.mp3")
    assert library.current_item().path.name == "existing.mp3"
    assert library.playback_position("existing.mp3") == 27.5
    assert app.session_state["ui_language"] == language
    assert not submitted

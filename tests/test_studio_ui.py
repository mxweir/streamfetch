import wave

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize(
    "view",
    [
        "render_smart",
        "render_listening",
        "render_folders",
        "render_speech",
        "render_file_tags",
        "render_sharing",
    ],
)
def test_studio_views_render_without_errors(tmp_path, monkeypatch, view):
    monkeypatch.setenv("STREAMFETCH_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "media"
    root.mkdir()
    with wave.open(str(root / "sample.wav"), "wb") as media:
        media.setnchannels(1)
        media.setsampwidth(2)
        media.setframerate(8000)
        media.writeframes(b"\x00\x00" * 8000)
    source = f"""
from pathlib import Path
from streamfetch.library import MediaLibrary
from streamfetch.studio_ui import {view}
library = MediaLibrary(Path({str(root)!r}))
library.scan()
def t(text, **values):
    return text.format(**values)
{view}(library, t{", lambda *a, **k: None" if view == "render_smart" else ""})
"""
    result = AppTest.from_string(source).run()
    assert not result.exception

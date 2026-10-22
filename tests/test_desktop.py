from streamfetch.desktop import find_free_port, find_streamlit_app, streamlit_options


def test_entrypoint_dispatches_frozen_helpers_before_server(monkeypatch):
    import streamfetch.desktop as desktop

    calls = []
    monkeypatch.setattr(desktop.multiprocessing, "freeze_support", lambda: calls.append("helpers"))
    monkeypatch.setattr(desktop, "run_frozen_server", lambda port: calls.append(port) or 0)
    monkeypatch.setattr(desktop.sys, "argv", ["StreamFetch", "--streamfetch-server", "8517"])
    assert desktop.entrypoint() == 0
    assert calls == ["helpers", 8517]


def test_desktop_launcher_finds_checkout_app():
    assert find_streamlit_app().name == "app.py"


def test_desktop_launcher_allocates_local_port():
    assert 0 < find_free_port() < 65536


def test_frozen_server_options_pin_loopback_and_port():
    options = streamlit_options(8765)

    assert options["global_developmentMode"] is False
    assert options["server_address"] == "127.0.0.1"
    assert options["server_port"] == 8765

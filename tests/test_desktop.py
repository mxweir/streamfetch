from streamfetch.desktop import find_free_port, find_streamlit_app


def test_desktop_launcher_finds_checkout_app():
    assert find_streamlit_app().name == "app.py"


def test_desktop_launcher_allocates_local_port():
    assert 0 < find_free_port() < 65536

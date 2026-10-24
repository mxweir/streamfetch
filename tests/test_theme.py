from streamfetch.theme import APP_CSS, HERO_HTML, LEGAL_HTML


def test_theme_contains_premium_palette_and_surfaces():
    for color in ("#17151c", "#fffdf7", "#75b8ff", "#8ce0b7", "#d9b8ff", "#ffd95a"):
        assert color in APP_CSS
    assert "backdrop-filter: blur" in APP_CSS
    assert "border-radius: 30px" in APP_CSS
    assert 'stBidiComponentIsolated' in APP_CSS
    assert "position: fixed" in APP_CSS
    assert "box-shadow: none" in APP_CSS


def test_hero_and_legal_copy_remain_accessible():
    assert "StreamFetch" in HERO_HTML
    assert 'aria-label="StreamFetch"' in HERO_HTML
    assert "sf-logo" in HERO_HTML
    assert "YouTube" in HERO_HTML
    assert "SoundCloud" in HERO_HTML
    assert "permission to download" in LEGAL_HTML


def test_sidebar_presets_keep_text_contrast_and_current_version():
    from streamfetch import __version__

    assert __version__ in HERO_HTML
    assert '[data-testid="stSidebar"] button[kind="secondary"] p' in APP_CSS
    assert "background: #25212e !important" in APP_CSS

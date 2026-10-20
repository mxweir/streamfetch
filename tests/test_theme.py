from streamfetch.theme import APP_CSS, HERO_HTML, LEGAL_HTML


def test_theme_contains_reference_palette_and_shapes():
    for color in ("#dceeff", "#4da2ff", "#55db9c", "#e9ccff", "#fb4903", "#ffd731"):
        assert color in APP_CSS
    assert "border-radius: 9999px" in APP_CSS
    assert "box-shadow: none" in APP_CSS


def test_hero_and_legal_copy_remain_accessible():
    assert "StreamFetch" in HERO_HTML
    assert "YouTube" in HERO_HTML
    assert "SoundCloud" in HERO_HTML
    assert "permission to download" in LEGAL_HTML

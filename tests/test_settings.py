import json

from streamfetch.settings import AppSettings, load_settings, save_settings


def test_settings_round_trip(tmp_path):
    settings = AppSettings(True, "Deutsch", "/media/music", False, True)

    path = save_settings(settings, tmp_path)

    assert path == tmp_path / "settings.json"
    assert load_settings(tmp_path) == settings


def test_invalid_settings_fall_back_to_defaults(tmp_path):
    (tmp_path / "settings.json").write_text("not json", encoding="utf-8")
    assert load_settings(tmp_path) == AppSettings()

    (tmp_path / "settings.json").write_text(
        json.dumps({"unknown": True, "language": "Deutsch"}), encoding="utf-8"
    )
    assert load_settings(tmp_path).language == "Deutsch"

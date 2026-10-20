from streamfetch.i18n import LANGUAGES, language_code, player_labels, translate


def test_translation_falls_back_to_english_copy() -> None:
    assert translate("Download studio", "English") == "Download studio"
    assert translate("Unknown copy", "Deutsch") == "Unknown copy"


def test_german_translation_interpolates_named_values() -> None:
    assert translate(
        "{count} of {total} selected",
        "Deutsch",
        count=2,
        total=5,
    ) == "2 von 5 ausgewählt"


def test_player_labels_follow_selected_language() -> None:
    assert LANGUAGES["Deutsch"] == "de"
    assert language_code("Deutsch") == "de"
    assert player_labels("Deutsch")["shuffle"] == "MISCHEN"

from streamfetch.downloader import _preview_from_info


def test_preview_normalizes_playlist_entries():
    preview = _preview_from_info(
        {
            "_type": "playlist",
            "title": "Example playlist",
            "channel": "Example channel",
            "playlist_count": 42,
            "entries": [
                {"title": "First", "duration": 90, "url": "https://youtu.be/one"},
                None,
                {"title": "Second", "duration": 120, "webpage_url": "https://youtu.be/two"},
            ],
        }
    )
    assert preview.title == "Example playlist"
    assert preview.uploader == "Example channel"
    assert preview.entry_count == 42
    assert [entry.title for entry in preview.entries] == ["First", "Second"]

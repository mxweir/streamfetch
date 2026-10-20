from streamfetch.downloader import _preview_from_info, resolve_selected_urls


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


def test_preview_builds_selectable_youtube_entry_urls():
    preview = _preview_from_info(
        {"title": "Mix", "entries": [{"id": "abc", "title": "One"}]},
        source_url="https://www.youtube.com/playlist?list=mix",
    )
    assert preview.entries[0].webpage_url == "https://www.youtube.com/watch?v=abc"


def test_collection_selection_replaces_source_and_preserves_direct_urls():
    collection = "https://www.youtube.com/playlist?list=mix"
    direct = "https://youtu.be/direct"
    preview = _preview_from_info(
        {
            "title": "Mix",
            "entries": [
                {"id": "one", "title": "One"},
                {"id": "two", "title": "Two"},
            ],
        },
        source_url=collection,
    )

    assert resolve_selected_urls(
        (collection, direct),
        (preview,),
        {collection: ("https://www.youtube.com/watch?v=two",)},
    ) == ("https://www.youtube.com/watch?v=two", direct)

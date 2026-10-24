import json

import pytest

from streamfetch.presets import PresetStore


def options(**values):
    return {"media_type": "audio", "audio_format": "mp3", "audio_quality": "192K", **values}


def test_presets_persist_without_sensitive_fields(tmp_path):
    store = PresetStore(tmp_path)
    store.save("My music", options(output_dir="/private/media", cookie_browser="Chrome",
                                   urls=["https://example.invalid/secret"], token="secret",
                                   embed_thumbnail=True, concurrent_fragments=2))
    restored = PresetStore(tmp_path).load()
    assert restored["My music"] == options(embed_thumbnail=True, concurrent_fragments=2)
    raw = store.path.read_text()
    assert "secret" not in raw and "Chrome" not in raw and "/private" not in raw
    store.save("My music", options(audio_quality="320K"))
    assert store.load()["My music"]["audio_quality"] == "320K"
    store.delete("My music")
    assert store.load() == {}


@pytest.mark.parametrize("values", [
    {"audio_format": "exe"}, {"media_type": "other"}, {"concurrent_fragments": 0},
    {"max_items": 4.5}, {"embed_thumbnail": "true"}, {"rate_limit_mbps": float("nan")},
    {"sponsorblock_remove": ["arbitrary"]}, {"use_clip_range": True, "clip_end": 0},
])
def test_invalid_options_never_overwrite_existing_preset(tmp_path, values):
    store = PresetStore(tmp_path)
    store.save("Keep", options())
    with pytest.raises(ValueError):
        store.save("Keep", options(**values))
    assert store.load()["Keep"] == options()


def test_bad_names_limits_and_corrupt_storage(tmp_path):
    store = PresetStore(tmp_path)
    for name in ("", "a" * 49, "line\nbreak"):
        with pytest.raises(ValueError):
            store.save(name, options())
    store.path.write_text('{"version":1,"presets":{"broken":null}}')
    assert store.load() == {}
    for number in range(30):
        store.save(str(number), options())
    with pytest.raises(ValueError):
        store.save("too many", options())
    assert len(json.loads(store.path.read_text())["presets"]) == 30

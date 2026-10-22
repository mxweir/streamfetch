import math

import pytest

from streamfetch.connected import PlaybackHub, bounded_number


def test_owner_lease_and_command_acknowledgement(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("streamfetch.connected.time.monotonic", lambda: now[0])
    hub = PlaybackHub()
    with pytest.raises(ValueError, match="Open the computer"):
        hub.send("play")
    assert hub.publish("pc", "/library/music.mp3", position=12, paused=False)
    assert not hub.publish("other-browser", "/library/other.mp3")
    nonce = hub.send("pause")
    assert hub.take("other-browser") is None
    command = hub.take("pc")
    assert command["nonce"] == nonce
    assert hub.take("pc") is None
    hub.publish("pc", "/library/music.mp3", position=13, paused=True, ack=nonce)
    assert hub.snapshot()["results"][nonce] == "applied"
    now[0] += 11
    assert not hub.snapshot()["online"]
    assert hub.publish("other-browser", "/library/other.mp3")


def test_pending_commands_expire_and_revoke(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("streamfetch.connected.time.monotonic", lambda: now[0])
    hub = PlaybackHub()
    hub.publish("pc", "/music")
    nonce = hub.send("play")
    now[0] += 11
    assert hub.take("pc") is None
    assert hub.snapshot()["results"][nonce] == "expired"
    hub.revoke()
    assert not hub.snapshot()["results"]


def test_blocked_audio_is_not_a_successful_handoff():
    hub = PlaybackHub()
    hub.publish("pc", "/music")
    nonce = hub.send("play", position=10)
    hub.publish("pc", "/music", paused=True, blocked=True, ack=nonce)
    assert hub.snapshot()["results"][nonce] == "blocked"


@pytest.mark.parametrize("value", [True, None, "1", -1, 2, math.nan, math.inf])
def test_reject_invalid_remote_volume(value):
    with pytest.raises(ValueError):
        bounded_number(value, 0, 1)


def test_queue_is_bounded():
    hub = PlaybackHub()
    hub.publish("pc", "/music")
    for _ in range(16):
        hub.send("pause")
    with pytest.raises(ValueError, match="busy"):
        hub.send("pause")

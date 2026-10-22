import http.client
import json
import time
from urllib.parse import urlencode

import pytest

from streamfetch.library import MediaLibrary
from streamfetch.sharing import HomePlayer, byte_range


@pytest.fixture
def player(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    (tmp_path / "track.mp3").write_bytes(b"0123456789")
    library = MediaLibrary(tmp_path)
    library.scan()
    playlist = library.create_playlist("At home")
    library.add_to_playlist(playlist.id, library.list_items()[0].path)
    player = HomePlayer(library, host="127.0.0.1", port=0)
    yield player
    player.stop()


def request(player, method, path, body=None, headers=None):
    client = http.client.HTTPConnection("127.0.0.1", player.port, timeout=3)
    client.request(method, path, body=body, headers=headers or {})
    response = client.getresponse()
    result = response.status, dict(response.headers), response.read()
    client.close()
    return result


def login(player):
    status, headers, _ = request(
        player,
        "POST",
        "/login",
        urlencode({"secret": player.secret}),
        headers={"Origin": f"http://127.0.0.1:{player.port}", "Sec-Fetch-Site": "same-origin"},
    )
    assert status == 303
    cookie = headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    return {"Cookie": cookie.split(";", 1)[0]}


def test_login_library_and_path_privacy(player):
    status, headers, _ = request(player, "GET", "/api/library")
    assert status == 303 and headers["Location"] == "/login"
    status, headers, _ = request(player, "GET", "/login")
    assert status == 200
    assert headers["Referrer-Policy"] == "same-origin"
    assert request(player, "POST", "/login", "secret=wrong")[0] == 403
    cookie = login(player)
    status, _, body = request(player, "GET", "/api/library", headers=cookie)
    assert status == 200
    assert str(player.library.root).encode() not in body
    item = json.loads(body)[0]
    assert item["playlists"] == ["At home"]
    assert "path" not in item
    assert request(player, "GET", "/", headers=cookie)[0] == 200
    assert request(player, "GET", "/player.js")[0] == 200
    assert request(player, "GET", "/style.css")[0] == 200
    assert request(player, "GET", "/logo.svg")[0] == 200
    assert request(player, "GET", "/settings", headers=cookie)[0] == 404


def test_streaming_range_head_and_auth(player):
    identifier = player.items()[0]["id"]
    path = f"/media/{identifier}"
    assert request(player, "GET", path)[0] == 303
    cookie = login(player)
    status, headers, body = request(player, "GET", path, headers={**cookie, "Range": "bytes=2-5"})
    assert status == 206 and body == b"2345"
    assert headers["Content-Range"] == "bytes 2-5/10"
    assert request(player, "GET", path, headers={**cookie, "Range": "bytes=-3"})[2] == b"789"
    assert request(player, "GET", path, headers=cookie)[2] == b"0123456789"
    assert request(player, "HEAD", path, headers=cookie)[2] == b""
    assert request(player, "GET", path, headers={**cookie, "Range": "bytes=99-"})[0] == 416
    assert request(player, "GET", "/media/../../etc/passwd", headers=cookie)[0] == 404
    assert request(player, "POST", "/logout", headers=cookie)[0] == 303
    assert request(player, "GET", path, headers=cookie)[0] == 303


def test_host_origin_rate_limit_and_expiry(player):
    assert request(player, "GET", "/login", headers={"Host": "evil.example"})[0] == 403
    assert (
        request(player, "POST", "/login", "secret=x", headers={"Origin": "https://evil.example"})[0]
        == 403
    )
    cookie = login(player)
    for key in player._sessions:
        player._sessions[key] = time.time() - 1
    assert request(player, "GET", "/api/library", headers=cookie)[0] == 303
    for _ in range(4):
        assert request(player, "POST", "/login", "secret=x")[0] == 403
    assert request(player, "POST", "/login", "secret=x")[0] == 429


@pytest.mark.parametrize(
    "value", ["bytes=12-", "bytes=2-1", "bytes=-0", "bytes=", "items=1-2", "bytes=0-1,3-4"]
)
def test_invalid_ranges(value):
    with pytest.raises(ValueError):
        byte_range(value, 10)


def test_symlink_retarget_cannot_expose_other_files(player, tmp_path):
    outside = tmp_path.parent / f"outside-{tmp_path.name}.mp3"
    outside.write_bytes(b"private data")
    path = player.library.list_items()[0].path
    identifier = player.identifier(path)
    path.unlink()
    path.symlink_to(outside)
    status, _, body = request(player, "GET", f"/media/{identifier}", headers=login(player))
    assert b"private data" not in body
    assert status != 200
    assert request(player, "GET", "/api/library", headers=login(player))[2] == b"[]"

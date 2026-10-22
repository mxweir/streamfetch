import http.client
import json
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import pytest
from cryptography.hazmat.primitives import serialization

from streamfetch.home_tls import HomeIdentity
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
    player = HomePlayer(
        library,
        identity=HomeIdentity(tmp_path / "state"),
        host="127.0.0.1",
        address="127.0.0.1",
        port=0,
    )
    yield player
    player.stop()


def request(player, method, path, body=None, headers=None):
    context = ssl.create_default_context(
        cadata=player.identity.cert.public_bytes(serialization.Encoding.PEM).decode()
    )
    context.verify_flags |= ssl.VERIFY_X509_STRICT
    client = http.client.HTTPSConnection("127.0.0.1", player.port, timeout=3, context=context)
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
        headers={"Origin": f"https://127.0.0.1:{player.port}", "Sec-Fetch-Site": "same-origin"},
    )
    assert status == 303
    cookie = headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Secure" in cookie
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


def pair(player, url):
    return request(
        player,
        "POST",
        "/pair",
        urlencode({"token": url.split("#")[1]}),
        {"Origin": f"https://127.0.0.1:{player.port}"},
    )


def test_qr_pairing_is_one_use_and_streams_over_tls(player):
    url = player.pairing_url()
    assert url.startswith("https://") and "?" not in url
    assert request(player, "GET", "/pair?token=" + url.split("#")[1])[0] == 200
    assert not player._sessions  # Visiting a link cannot redeem it.
    status, headers, _ = pair(player, url)
    assert status == 200 and player.pair_used
    assert "Secure" in headers["Set-Cookie"]
    cookie = {"Cookie": headers["Set-Cookie"].split(";", 1)[0]}
    assert request(player, "GET", "/api/library", headers=cookie)[0] == 200
    path = "/media/" + player.items()[0]["id"]
    assert request(player, "GET", path, headers={**cookie, "Range": "bytes=2-5"})[2] == b"2345"
    assert pair(player, url)[0] == 403


def test_qr_expiry_and_rotation(player):
    old = player.pairing_url()
    current = player.pairing_url()
    assert pair(player, old)[0] == 403
    player.pair_expires = time.time() - 1
    assert pair(player, current)[0] == 403
    fresh = player.pairing_url()
    assert pair(player, fresh)[0] == 200


def test_concurrent_qr_redemption_has_one_winner(player):
    url = player.pairing_url()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: pair(player, url)[0], range(2)))
    assert sorted(results) == [200, 403]
    assert len(player._sessions) == 1


def test_tls_rejects_untrusted_and_plaintext_clients(player):
    client = http.client.HTTPSConnection("127.0.0.1", player.port, timeout=3)
    with pytest.raises(ssl.SSLCertVerificationError):
        client.request("GET", "/login")
    client.close()
    client = http.client.HTTPConnection("127.0.0.1", player.port, timeout=3)
    with pytest.raises((OSError, http.client.HTTPException)):
        client.request("GET", "/login")
        client.getresponse()
    client.close()


def test_http_origin_cannot_redeem_pairing(player):
    url = player.pairing_url()
    assert (
        request(
            player,
            "POST",
            "/pair",
            urlencode({"token": url.split("#")[1]}),
            {"Origin": f"http://127.0.0.1:{player.port}"},
        )[0]
        == 403
    )
    assert not player._sessions


def test_pair_script_scrubs_fragment_before_request(player):
    script = request(player, "GET", "/pair.js")[2].decode()
    assert script.index("history.replaceState") < script.index("fetch(")
    assert "new URLSearchParams({token})" in script


def post_json(player, route, payload, cookie):
    return request(
        player,
        "POST",
        route,
        json.dumps(payload),
        {
            **cookie,
            "Content-Type": "application/json",
            "Origin": f"https://127.0.0.1:{player.port}",
        },
    )


def test_remote_and_downloads_are_separate_explicit_permissions(player):
    cookie = login(player)
    item = player.items()[0]
    assert request(player, "GET", "/download/" + item["id"])[0] == 303
    assert request(player, "GET", "/download/" + item["id"], headers=cookie)[0] == 403
    assert post_json(player, "/api/control", {"action": "play"}, cookie)[0] == 403
    player.allow_downloads = True
    status, headers, body = request(player, "GET", "/download/" + item["id"], headers=cookie)
    assert status == 200 and body == b"0123456789"
    assert headers["Content-Disposition"].startswith("attachment; filename*=UTF-8''")
    assert "track.mp3" in headers["Content-Disposition"]
    player.allow_downloads = False
    assert request(player, "GET", "/download/" + item["id"], headers=cookie)[0] == 403
    state = json.loads(request(player, "GET", "/api/playback", headers=cookie)[2])
    assert state == dict(remote_allowed=False, downloads_allowed=False, online=False)


def test_remote_commands_and_state_never_expose_filesystem_paths(player):
    cookie = login(player)
    player.allow_remote = True
    item = player.library.list_items()[0]
    player.hub.publish("pc", item.path, position=2, paused=False)
    status, _, body = post_json(
        player,
        "/api/control",
        {"action": "seek", "item": player.identifier(item.path), "position": 5},
        cookie,
    )
    assert status == 202
    nonce = json.loads(body)["command"]
    command = player.hub.take("pc")
    assert command["position"] == 5
    player.hub.publish("pc", item.path, position=5, paused=False, ack=nonce)
    status, _, body = request(player, "GET", "/api/playback", headers=cookie)
    assert status == 200 and str(item.path).encode() not in body
    assert json.loads(body)["results"][nonce] == "applied"
    assert post_json(player, "/api/control", {"action": "shell"}, cookie)[0] == 400
    assert post_json(player, "/api/control", {"action": "volume", "volume": 10}, cookie)[0] == 400
    assert (
        post_json(player, "/api/control", {"action": "play", "item": "../secret"}, cookie)[0] == 400
    )
    assert post_json(player, "/api/control", {"action": "pause"}, {})[0] == 401


def test_phone_progress_is_persistent_but_requires_a_valid_track(player):
    cookie = login(player)
    item = player.items()[0]
    assert post_json(player, "/api/progress", {"item": item["id"], "position": 3}, cookie)[0] == 200
    assert player.items()[0]["resume"] == 3
    assert (
        post_json(player, "/api/progress", {"item": item["id"], "position": -1}, cookie)[0] == 400
    )
    assert post_json(player, "/api/progress", {"position": 1}, cookie)[0] == 400

import io
import json
import ssl

from streamfetch import engine_updates, network, updates


def test_packaged_ca_bundle_works_without_system_ca_file(monkeypatch):
    # Reproduce official frozen Python: valid TLS implementation, no usable OS CA path.
    empty = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    initial_count = len(empty.get_ca_certs())
    monkeypatch.setattr(network.ssl, "create_default_context", lambda: empty)
    context = network.verified_context()
    assert context is empty and len(context.get_ca_certs()) > initial_count
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_engine_fetch_uses_verified_packaged_trust(monkeypatch):
    context = network.verified_context()

    class Response(io.BytesIO):
        url = "https://pypi.org/pypi/yt-dlp/json"

    def opened(request, *, timeout, context):
        assert request.full_url == Response.url and timeout == 5
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        return Response(b"engine metadata")

    monkeypatch.setattr(engine_updates, "verified_context", lambda: context)
    monkeypatch.setattr(engine_updates.urllib.request, "urlopen", opened)
    assert engine_updates._fetch(Response.url) == b"engine metadata"


def test_github_check_and_installer_use_verified_packaged_trust(monkeypatch, tmp_path):
    context = network.verified_context()
    seen = []

    def opened(request, *, timeout, context):
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        seen.append((request.full_url, timeout))
        if request.full_url == updates.LATEST_RELEASE_URL:
            return io.BytesIO(json.dumps({"tag_name": "v2.0.1"}).encode())
        return io.BytesIO(b"test installer")

    monkeypatch.setattr(updates, "verified_context", lambda: context)
    monkeypatch.setattr(updates.urllib.request, "urlopen", opened)
    monkeypatch.setattr(updates.platform, "system", lambda: "Darwin")
    assert updates.fetch_latest_release().version == "2.0.1"
    release = updates.ReleaseInfo("2.0.1", "Patch", "https://github.com/mxweir/streamfetch",
                                  assets=({"name": "StreamFetch-macos.dmg",
                                           "url": "https://example.invalid/app.dmg"},))
    target = updates._download_packaged_asset(release, tmp_path)
    assert target.read_bytes() == b"test installer"
    assert seen == [(updates.LATEST_RELEASE_URL, 5), ("https://example.invalid/app.dmg", 60)]

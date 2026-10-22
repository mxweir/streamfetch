import os
import ssl
import zipfile

import pytest
from cryptography import x509

from streamfetch.home_tls import HomeIdentity, validate_address


def test_persistent_private_identity_and_public_export(tmp_path):
    first = HomeIdentity(tmp_path)
    second = HomeIdentity(tmp_path)
    assert first.public_certificate == second.public_certificate
    assert first.fingerprint == second.fingerprint
    public = x509.load_der_x509_certificate(first.public_certificate)
    assert public.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert b"PRIVATE KEY" not in first.public_certificate
    assert first.context("192.168.1.2").minimum_version == ssl.TLSVersion.TLSv1_2
    if os.name != "nt":
        assert (tmp_path / "home-tls/identity.json").stat().st_mode & 0o777 == 0o600


def test_corrupt_identity_is_not_silently_rotated(tmp_path):
    HomeIdentity(tmp_path)
    path = tmp_path / "home-tls/identity.json"
    path.write_text("broken")
    with pytest.raises(ValueError, match="not automatically replaced"):
        HomeIdentity(tmp_path)
    assert path.read_text() == "broken"


@pytest.mark.parametrize("address", ["8.8.8.8", "0.0.0.0", "::1", "example.com"])
def test_only_private_ipv4_addresses(address):
    with pytest.raises(ValueError):
        validate_address(address)


def test_update_backup_preserves_identity_without_exporting_private_key(tmp_path):
    from streamfetch.updates import create_pre_update_backup

    identity = HomeIdentity(tmp_path)
    backup = create_pre_update_backup(tmp_path, None, "1.7.0")
    with zipfile.ZipFile(backup) as archive:
        assert not any("home-tls" in name for name in archive.namelist())
        assert b"PRIVATE KEY" not in b"".join(archive.read(n) for n in archive.namelist())
    assert HomeIdentity(tmp_path).public_certificate == identity.public_certificate

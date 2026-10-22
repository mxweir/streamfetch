"""Installation-local TLS identity; never modifies the operating system trust store."""

from __future__ import annotations

import contextlib
import datetime as dt
import ipaddress
import json
import os
import ssl
import tempfile
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

_LOCK = threading.Lock()
NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")
)


def validate_address(value):
    address = ipaddress.IPv4Address(value)
    if not any(address in network for network in NETWORKS):
        raise ValueError("Use a private home-network IPv4 address.")
    return str(address)


class HomeIdentity:
    def __init__(self, state_dir):
        folder = Path(state_dir) / "home-tls"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = folder / "identity.json"
        with _LOCK:
            if not path.exists():
                key = ec.generate_private_key(ec.SECP256R1())
                name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "StreamFetch Home CA")])
                now = dt.datetime.now(dt.UTC)
                cert = (
                    x509.CertificateBuilder()
                    .subject_name(name)
                    .issuer_name(name)
                    .public_key(key.public_key())
                    .serial_number(x509.random_serial_number())
                    .not_valid_before(now - dt.timedelta(minutes=5))
                    .not_valid_after(now + dt.timedelta(days=1825))
                    .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
                    .add_extension(
                        x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False
                    )
                    .add_extension(
                        x509.KeyUsage(False, False, False, False, False, True, True, False, False),
                        True,
                    )
                    .add_extension(
                        x509.NameConstraints(
                            [x509.IPAddress(n) for n in NETWORKS] + [x509.DNSName("localhost")],
                            None,
                        ),
                        True,
                    )
                    .sign(key, hashes.SHA256())
                )
                data = json.dumps(
                    {
                        "key": key.private_bytes(
                            serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption(),
                        ).decode(),
                        "certificate": cert.public_bytes(serialization.Encoding.PEM).decode(),
                    }
                ).encode()
                # Publish a complete file atomically without replacing another process's CA.
                fd, temporary = tempfile.mkstemp(dir=folder, prefix=".identity-")
                try:
                    with os.fdopen(fd, "wb") as output:
                        output.write(data)
                        output.flush()
                        os.fsync(output.fileno())
                    with contextlib.suppress(FileExistsError):
                        os.link(temporary, path)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            try:
                data = json.loads(path.read_text())
                self.key = serialization.load_pem_private_key(data["key"].encode(), None)
                self.cert = x509.load_pem_x509_certificate(data["certificate"].encode())
                self.cert.verify_directly_issued_by(self.cert)
                if not self.cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
                    raise ValueError("Not a CA certificate")
                if self.key.public_key().public_bytes(
                    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
                ) != self.cert.public_key().public_bytes(
                    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
                ) or self.cert.not_valid_after_utc <= dt.datetime.now(dt.UTC):
                    raise ValueError("Expired or mismatched identity")
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(
                    "Home TLS identity is invalid. Restore its backup; it was not "
                    "automatically replaced."
                ) from error

    @property
    def public_certificate(self):
        return self.cert.public_bytes(serialization.Encoding.DER)

    @property
    def fingerprint(self):
        return self.cert.fingerprint(hashes.SHA256()).hex(":").upper()

    def context(self, address):
        address = validate_address(address)
        key = ec.generate_private_key(ec.SECP256R1())
        now = dt.datetime.now(dt.UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "StreamFetch")]))
            .issuer_name(self.cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(min(now + dt.timedelta(days=90), self.cert.not_valid_after_utc))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()), False
            )
            .add_extension(
                x509.KeyUsage(True, False, False, False, False, False, False, False, False), True
            )
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.IPAddress(ipaddress.ip_address(address)),
                        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                        x509.DNSName("localhost"),
                    ]
                ),
                False,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
            .sign(self.key, hashes.SHA256())
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        with tempfile.TemporaryDirectory(prefix="streamfetch-tls-") as folder:
            certificate, private = Path(folder) / "cert.pem", Path(folder) / "key.pem"
            certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            private.touch(mode=0o600)
            private.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            context.load_cert_chain(certificate, private)
        return context

import socket

import pytest

from streamfetch.sharing import local_address


@pytest.mark.parametrize(
    "address,expected",
    [("192.168.1.25", "192.168.1.25"), ("10.2.3.4", "10.2.3.4"),
     ("8.8.8.8", "127.0.0.1")],
)
def test_address_detection_is_bounded_private_without_dns(monkeypatch, address, expected):
    calls = []

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            calls.append("closed")

        def settimeout(self, value):
            calls.append(value)

        def connect(self, target):
            calls.append(target)

        def getsockname(self):
            return address, 50000

    def no_dns(*_):
        pytest.fail("Address suggestion must not resolve the machine hostname")

    monkeypatch.setattr(socket, "gethostbyname_ex", no_dns)
    monkeypatch.setattr(socket, "socket", lambda *_: Probe())
    assert local_address() == expected
    assert calls == [0.25, ("192.0.2.1", 9), "closed"]


def test_disconnected_network_returns_loopback_without_raising(monkeypatch):
    def unavailable(*_):
        raise OSError("Network is down")

    monkeypatch.setattr(socket, "socket", unavailable)
    assert local_address() == "127.0.0.1"

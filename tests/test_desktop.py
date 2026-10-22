import os
import signal
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from streamfetch.desktop import find_free_port, find_streamlit_app, stop_server, streamlit_options


def test_posix_cleanup_targets_only_owned_server_group(monkeypatch):
    calls = []
    process = SimpleNamespace(pid=1234, wait=lambda timeout: 0)
    monkeypatch.setattr("streamfetch.desktop.os.killpg", lambda pid, sig: calls.append((pid, sig)))
    stop_server(process, system="darwin")
    assert calls == [(1234, signal.SIGTERM), (1234, signal.SIGKILL)]


def test_windows_cleanup_targets_owned_process_tree(monkeypatch):
    calls = []
    process = SimpleNamespace(pid=1234, wait=lambda timeout: 0)
    monkeypatch.setattr(
        "streamfetch.desktop.subprocess.run", lambda command, **kwargs: calls.append(command)
    )
    stop_server(process, system="win32")
    assert calls[0][1:] == ["/PID", "1234", "/T", "/F"]
    assert calls[0][0].endswith("taskkill.exe")


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group integration")
def test_cleanup_stops_helper_that_ignores_termination():
    child_code = (
        "import socket,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "sock=socket.socket(); sock.bind(('127.0.0.1',0)); sock.listen(); "
        "print(sock.getsockname()[1],flush=True); time.sleep(60)"
    )
    parent_code = (
        "import subprocess,sys,time; "
        f"child=subprocess.Popen([sys.executable,'-c',{child_code!r}],"
        "stdout=subprocess.PIPE,text=True); print(child.stdout.readline(),flush=True); "
        "time.sleep(60)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", parent_code],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        port = int(process.stdout.readline())
        stop_server(process)
        assert process.poll() is not None
        for _ in range(100):
            with socket.socket() as probe:
                probe.settimeout(0.1)
                if probe.connect_ex(("127.0.0.1", port)) != 0:
                    break
            time.sleep(0.01)
        else:
            pytest.fail("Owned helper process is still listening after shutdown.")
    finally:
        stop_server(process)


def test_entrypoint_dispatches_frozen_helpers_before_server(monkeypatch):
    import streamfetch.desktop as desktop

    calls = []
    monkeypatch.setattr(desktop.multiprocessing, "freeze_support", lambda: calls.append("helpers"))
    monkeypatch.setattr(desktop, "run_frozen_server", lambda port: calls.append(port) or 0)
    monkeypatch.setattr(desktop.sys, "argv", ["StreamFetch", "--streamfetch-server", "8517"])
    assert desktop.entrypoint() == 0
    assert calls == ["helpers", 8517]


def test_desktop_launcher_finds_checkout_app():
    assert find_streamlit_app().name == "app.py"


def test_desktop_launcher_allocates_local_port():
    assert 0 < find_free_port() < 65536


def test_frozen_server_options_pin_loopback_and_port():
    options = streamlit_options(8765)

    assert options["global_developmentMode"] is False
    assert options["server_address"] == "127.0.0.1"
    assert options["server_port"] == 8765

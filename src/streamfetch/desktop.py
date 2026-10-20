"""Native desktop launcher for the local Streamlit application."""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


def find_streamlit_app() -> Path:
    """Locate app.py in a checkout, installed wheel, or PyInstaller bundle."""

    bundle_root = getattr(sys, "_MEIPASS", None)
    candidates = [
        Path(bundle_root) / "app.py" if bundle_root else None,
        Path(__file__).resolve().parents[2] / "app.py",
        Path(__file__).with_name("_desktop_app.py"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise RuntimeError("The bundled StreamFetch app could not be found.")


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def wait_for_server(
    url: str,
    process: subprocess.Popen[bytes] | None = None,
    thread: threading.Thread | None = None,
    timeout: float = 30,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError("StreamFetch stopped before the desktop window opened.")
        if thread is not None and not thread.is_alive():
            raise RuntimeError("StreamFetch stopped before the desktop window opened.")
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:  # noqa: S310
                if response.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.15)
    raise RuntimeError("Timed out while starting the local StreamFetch server.")


def main() -> int:
    """Run StreamFetch in a native pywebview window."""

    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            'Desktop support is not installed. Run `pip install -e ".[desktop]"`.'
        ) from exc

    port = find_free_port()
    url = f"http://127.0.0.1:{port}"
    app_path = find_streamlit_app()
    process = None
    server_thread = None
    if getattr(sys, "frozen", False):
        from streamlit.web import bootstrap

        options = {
            "server.address": "127.0.0.1",
            "server.port": port,
            "server.headless": True,
            "browser.gatherUsageStats": False,
        }
        server_thread = threading.Thread(
            target=bootstrap.run,
            args=(str(app_path), False, [], options),
            daemon=True,
            name="streamfetch-desktop-server",
        )
        server_thread.start()
    else:
        command = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
    try:
        wait_for_server(url, process=process, thread=server_thread)
        webview.create_window(
            "StreamFetch",
            url,
            width=1380,
            height=900,
            min_size=(920, 640),
            background_color="#17151c",
        )
        webview.start()
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Native desktop launcher for the local Streamlit application."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
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
    timeout: float = 30,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError("StreamFetch stopped before the desktop window opened.")
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:  # noqa: S310
                if response.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.15)
    raise RuntimeError("Timed out while starting the local StreamFetch server.")


def streamlit_options(port: int) -> dict[str, object]:
    return {
        "global_developmentMode": False,
        "server_address": "127.0.0.1",
        "server_port": port,
        "server_headless": True,
        "browser_gatherUsageStats": False,
    }


def run_frozen_server(port: int) -> int:
    """Run Streamlit in the bundled executable's main thread."""

    os.environ.update(
        {
            "STREAMLIT_GLOBAL_DEVELOPMENT_MODE": "false",
            "STREAMLIT_SERVER_ADDRESS": "127.0.0.1",
            "STREAMLIT_SERVER_PORT": str(port),
            "STREAMLIT_SERVER_HEADLESS": "true",
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        }
    )
    from streamlit.web import bootstrap

    options = streamlit_options(port)
    bootstrap.load_config_options(options)
    bootstrap.run(str(find_streamlit_app()), False, [], options)
    return 0


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
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--streamfetch-server", str(port)]
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
        wait_for_server(url, process=process)
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
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--streamfetch-server":
        raise SystemExit(run_frozen_server(int(sys.argv[2])))
    raise SystemExit(main())

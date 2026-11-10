"""Start the frozen server and confirm its private readiness route."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

from streamfetch.desktop import find_free_port, stop_server, wait_for_server


def main() -> None:
    executable = Path(sys.argv[1]).resolve()
    port = find_free_port()
    route = f"streamfetch-smoke-{secrets.token_hex(12)}"
    with tempfile.TemporaryDirectory() as state:
        log_path = Path(state) / "server.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [str(executable), "--streamfetch-server", str(port)],
                env={
                    **os.environ,
                    "STREAMFETCH_STATE_DIR": state,
                    "STREAMLIT_SERVER_BASE_URL_PATH": route,
                },
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=os.name == "posix",
            )
            try:
                wait_for_server(f"http://127.0.0.1:{port}/{route}/", process, timeout=90)
            except RuntimeError:
                print(log_path.read_text(encoding="utf-8", errors="replace"))
                raise
            finally:
                stop_server(process)


if __name__ == "__main__":
    main()

import math
import shutil
import struct
import time
import wave

import pytest

from streamfetch.library import MediaLibrary
from streamfetch.loudness import LoudnessService, safe_gain


@pytest.mark.parametrize(
    "integrated,peak,expected",
    [(-12, -1, -6), (-24, -10, 6), (-30, -2, 1), ("-inf", "-inf", 0), (-60, -40, 12)],
)
def test_gain_matches_target_with_peak_headroom(integrated, peak, expected):
    assert safe_gain(integrated, peak) == expected


def test_real_ffmpeg_analysis_is_cached_and_non_destructive(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("Optional FFmpeg integration")
    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as media:
        media.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        media.writeframes(
            b"".join(
                struct.pack("<h", int(2000 * math.sin(i * math.tau * 440 / 16000)))
                for i in range(32000)
            )
        )
    original = path.read_bytes()
    library = MediaLibrary(tmp_path)
    library.scan()
    item = library.list_items()[0]
    service = LoudnessService(tmp_path)
    assert service.gain(item) is None
    service.start()
    deadline = time.monotonic() + 15
    while service.running and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not service.running and service.failed == 0
    assert service.gain(item) is not None
    assert path.read_bytes() == original
    assert LoudnessService(tmp_path).gain(item) == service.gain(item)
    path.write_bytes(original + b"changed")
    assert service.gain(item) is None

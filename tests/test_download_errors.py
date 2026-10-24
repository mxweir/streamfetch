from dataclasses import replace
from types import SimpleNamespace

import pytest

from streamfetch.download_errors import classify_download_error, safe_error_detail
from streamfetch.downloader import Downloader, DownloaderError
from streamfetch.jobs import DownloadJobManager, JobStatus
from streamfetch.models import DownloadRequest, MediaType


@pytest.mark.parametrize("message,code,retryable", [
    ("Private video. Sign in", "private", False),
    ("Sign in to confirm your age", "authentication", False),
    ("HTTP Error 403 Forbidden", "extractor", False),
    ("Requested format is not available", "format", False),
    ("ffmpeg not found", "ffmpeg", False),
    ("No space left on device", "storage", False),
    ("Permission denied", "permission", False),
    ("Video unavailable", "unavailable", False),
    ("This video is unavailable", "unavailable", False),
    ("HTTP Error 429: Too many requests", "rate_limit", False),
    ("not available in your country", "region", False),
    ("Connection timed out", "network", True),
    ("HTTP Error 503", "network", True),
    ("unexpected failure", "unknown", False),
])
def test_actionable_failures(message, code, retryable):
    failure = classify_download_error(message)
    assert failure.code == code and failure.retryable is retryable
    assert failure.title and failure.guidance


def test_details_redact_urls_home_and_sensitive_headers():
    from pathlib import Path

    detail = safe_error_detail(
        f"\x1b[31mFailure at {Path.home()}/media\x1b[0m\n"
        "https://example.invalid/?token=secret\nAuthorization: Bearer abcdef\n"
        "Cookie: session=private; next=secret\npassword=another"
    )
    for secret in (str(Path.home()), "example.invalid", "abcdef", "private", "another", "secret"):
        assert secret not in detail
    assert "<redacted>" in detail


def test_real_ydl_error_is_preserved_instead_of_generic_exit_code(monkeypatch, tmp_path):
    class FakeYDL:
        def __init__(self, options):
            self.logger = options["logger"]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def download(self, _urls):
            self.logger.error("ERROR: Private video. Sign in")
            return 1

    monkeypatch.setattr("streamfetch.downloader._import_yt_dlp",
                        lambda: SimpleNamespace(YoutubeDL=FakeYDL))
    request = DownloadRequest(urls=("https://youtu.be/example",), output_dir=tmp_path,
                              media_type=MediaType.AUDIO, container="mp3", quality="192K")
    with pytest.raises(DownloaderError, match="Private video") as error:
        Downloader().download(request)
    assert not error.value.retryable


def test_permanent_failure_does_not_schedule_automatic_retry(tmp_path):
    class PrivateDownloader:
        calls = 0

        def download(self, request, callback):
            type(self).calls += 1
            raise DownloaderError("Private video")

    request = DownloadRequest(urls=("https://youtu.be/example",), output_dir=tmp_path,
                              media_type=MediaType.AUDIO, container="mp3", quality="192K")
    manager = DownloadJobManager(downloader_factory=PrivateDownloader, retry_delays=(0, 0))
    job = manager.submit(replace(request, allow_playlists=False))[0]
    assert manager.wait(job).status == JobStatus.FAILED
    assert PrivateDownloader.calls == 1
    manager.shutdown()

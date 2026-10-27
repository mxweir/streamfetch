import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest

from streamfetch.activity import activity_page, completed_roots
from streamfetch.config import build_ydl_options, download_profile
from streamfetch.downloader import Downloader, DownloaderError
from streamfetch.models import DownloadRequest, MediaType


def request(root):
    return DownloadRequest(urls=("https://youtu.be/one",), output_dir=root,
                           media_type=MediaType.AUDIO, container="mp3", quality="192K")


def test_output_profiles_separate_formats_quality_and_clips_but_not_network_options(tmp_path):
    original = request(tmp_path)
    base = build_ydl_options(original)
    for candidate in (
        replace(original, media_type=MediaType.VIDEO, container="mp4", quality="360p"),
        replace(original, quality="320K"),
        replace(original, split_chapters=True),
        replace(original, embed_thumbnail=False),
    ):
        options = build_ydl_options(candidate)
        assert options["download_archive"] != base["download_archive"]
        assert options["outtmpl"]["default"] != base["outtmpl"]["default"]
    assert download_profile(replace(original, quality="192")) == download_profile(original)
    assert download_profile(replace(original, rate_limit=100000, concurrent_fragments=2,
                                    cookie_browser="firefox")) == download_profile(original)
    legacy = tmp_path / ".streamfetch-archive.txt"
    legacy.write_text("youtube one\n")
    assert base["download_archive"] != str(legacy)
    assert legacy.read_text() == "youtube one\n"
    clipped = replace(original, download_sections=("0-10",))
    assert download_profile(clipped) != download_profile(original)


def test_chapter_splitting_happens_after_audio_conversion(tmp_path):
    options = build_ydl_options(replace(request(tmp_path), split_chapters=True))
    processors = [row["key"] for row in options["postprocessors"]]
    assert processors.index("FFmpegSplitChapters") > processors.index("FFmpegExtractAudio")


def test_concurrent_jobs_only_return_their_own_final_files(monkeypatch, tmp_path):
    barrier = threading.Barrier(2)

    class YDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def download(self, urls):
            target = tmp_path / (urls[0].rsplit("/", 1)[1] + ".mp3")
            target.write_bytes(b"audio")
            (tmp_path / "unrelated-cover.jpg").write_bytes(b"cover")
            barrier.wait(timeout=5)
            for hook in self.options["postprocessor_hooks"]:
                hook({"status": "finished", "info_dict": {"filepath": str(target)}})
            return 0

    monkeypatch.setattr("streamfetch.downloader._import_yt_dlp",
                        lambda: SimpleNamespace(YoutubeDL=YDL))
    requests = [replace(request(tmp_path), urls=(f"https://youtu.be/{name}",))
                for name in ("one", "two")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda value: Downloader().download(value), requests))
    assert results[0].files == ((tmp_path / "one.mp3").resolve(),)
    assert results[1].files == ((tmp_path / "two.mp3").resolve(),)


def test_collector_rejects_file_outside_output_root(monkeypatch, tmp_path):
    class YDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def download(self, _urls):
            for hook in self.options["postprocessor_hooks"]:
                hook({"status": "finished",
                      "info_dict": {"filepath": str(tmp_path / "outside.mp3")}})

    monkeypatch.setattr("streamfetch.downloader._import_yt_dlp",
                        lambda: SimpleNamespace(YoutubeDL=YDL))
    with pytest.raises(DownloaderError, match="outside"):
        Downloader().download(request(tmp_path / "output"))


def test_completed_job_invalidates_library_only_once(tmp_path):
    job = SimpleNamespace(id="done", status="completed", files=(tmp_path / "track.mp3",),
                          output_dir=tmp_path)
    seen, roots = completed_roots([job], ())
    assert roots == {str(tmp_path.resolve())}
    seen_again, roots_again = completed_roots([job], seen)
    assert seen_again == seen and not roots_again


def test_activity_is_bounded_and_prioritises_running_jobs():
    jobs = [SimpleNamespace(id=str(i), status="completed", created_at=i) for i in range(200)]
    jobs.append(SimpleNamespace(id="active", status="running", created_at=-1))
    rows, total = activity_page(jobs, "All")
    assert total == 201 and len(rows) == 30 and rows[0].id == "active"
    rows, total = activity_page(jobs, "Active")
    assert total == 1 and rows[0].id == "active"

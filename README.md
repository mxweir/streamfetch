# StreamFetch

[![CI](https://github.com/mxweir/streamlit-media-downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/mxweir/streamlit-media-downloader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)

StreamFetch is a local Streamlit interface for downloading YouTube media with
[`yt-dlp`](https://github.com/yt-dlp/yt-dlp). It supports individual videos,
playlists, channel URLs, audio extraction, format and quality selection,
metadata, thumbnails, subtitles, browser cookies, and duplicate protection.

> [!IMPORTANT]
> Download only media you created, media in the public domain, or media you have
> permission to download. You are responsible for respecting copyright,
> YouTube's terms, and the laws that apply to you. This project does not bypass
> DRM and is not affiliated with YouTube or Google.

## Features

- Video output as MP4, MKV, or WebM
- Audio output as MP3, M4A, Opus, FLAC, or WAV
- Configurable video resolution and audio quality
- Single videos, playlists, multiple URLs, and complete channel/tab URLs
- Optional metadata, thumbnails, and embedded subtitles
- Configurable playlist/channel safety limit (50 items by default)
- Download archive that prevents accidental duplicate downloads
- Optional local Chrome, Firefox, Edge, Safari, or Brave cookies
- Source preview and live progress in the browser
- Cross-platform filename normalization

## Requirements

- Python 3.11 or newer
- [FFmpeg](https://ffmpeg.org/download.html) available on `PATH`
- A JavaScript runtime supported by yt-dlp may be needed for some YouTube
  formats. Keep yt-dlp current and follow its installation documentation.

Install FFmpeg:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# Windows (winget)
winget install Gyan.FFmpeg
```

## Local installation

```bash
git clone https://github.com/mxweir/streamlit-media-downloader.git
cd streamlit-media-downloader
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e .
streamlit run app.py
```

Streamlit opens `http://localhost:8501`. Paste one YouTube URL per line, choose
the output settings, confirm that you have permission, and start the download.
Files are stored in `downloads/` by default and organized by uploader and
playlist.

## Docker

```bash
docker build -t streamfetch .
docker run --rm -p 8501:8501 -v "$PWD/downloads:/app/downloads" streamfetch
```

Browser-cookie extraction is intended for the native local installation and is
not available inside the default container unless a browser profile is mounted
explicitly.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

The code is split into a Streamlit UI and a small `streamfetch` core package.
Format selection and yt-dlp options are unit-tested without contacting YouTube.

## Deployment warning

StreamFetch is designed as a trusted, single-user local application. A remote
deployment downloads files onto the server, may expose browser cookies or local
paths, and can consume significant bandwidth and disk space. Do not expose it
to the public internet without authentication, quotas, isolation, and storage
controls.

## Roadmap

- Resumable background queue
- Per-item selection before downloading a playlist
- Persistent download history and disk-usage dashboard
- Optional desktop packaging
- Internationalized interface

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md).

# StreamFetch

[![CI](https://github.com/mxweir/streamlit-media-downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/mxweir/streamlit-media-downloader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)

StreamFetch is a local Streamlit interface for downloading YouTube and
SoundCloud media with [`yt-dlp`](https://github.com/yt-dlp/yt-dlp). It supports
YouTube videos, playlists, and channels as well as SoundCloud tracks, sets, and
profiles. Format and quality selection, metadata, thumbnails, subtitles,
browser cookies, and duplicate protection are built in.

The visual direction is inspired by Refero's
[Slush style reference](https://styles.refero.design/style/8b6b547f-a357-4f1b-9842-4579c62dd42b):
pastel paper surfaces, bold display type, sticker colors, and black outlined controls.

> [!IMPORTANT]
> Download only media you created, media in the public domain, or media you have
> permission to download. You are responsible for respecting copyright,
> each platform's terms, and the laws that apply to you. This project does not
> bypass DRM and is not affiliated with YouTube, Google, or SoundCloud.

## Features

- Bold pastel interface with outlined cards, pill controls, and responsive layout
- Persistent local media library backed by a rebuildable SQLite index
- Folder scanning with metadata, embedded cover art, search, filters, and sorting
- Library statistics for audio, video, artists, and storage use
- Custom continuous audio/video player with persistent current-item state
- Automatic queue advancement with next-item preloading
- Seek, volume, previous/next, favorite, and keyboard controls
- Smart queue with play-next, shuffle, repeat, drag-to-reorder, and collection playback
- Configurable soft audio transitions and saved playback positions
- Favorites, custom playlists, and local play history
- Video output as MP4, MKV, or WebM
- Audio output as MP3, M4A, Opus, FLAC, or WAV
- Configurable video resolution and audio quality
- Parallel background download jobs with live speed and ETA
- Pause, resume, and retry controls using partial-download continuation
- Fragment concurrency, bandwidth limits, clip ranges, chapter splitting, and SponsorBlock
- YouTube videos, playlists, multiple URLs, and complete channel/tab URLs
- SoundCloud tracks, sets/playlists, profiles, and share links
- Mixed YouTube and SoundCloud lists in audio mode
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

Streamlit opens `http://localhost:8501`. Paste one YouTube or SoundCloud URL per
line, choose the output settings, confirm that you have permission, and start
the download. SoundCloud sources support audio output; YouTube supports both
video and audio. Files are stored in `downloads/` by default and organized by
uploader and collection.

## Local media library

Select **Library** at the top of the app to scan and browse a local media
folder. StreamFetch indexes MP3, M4A, Opus, Ogg, FLAC, WAV, MP4, MKV, and WebM
files. The index lives in `.streamfetch/library.db` inside the selected folder;
it contains only rebuildable metadata and can be recreated from the media files
at any time.

Use **Refresh library** after adding, moving, or deleting files. The library
extracts embedded titles, artists, albums, durations, and artwork where the file
format provides them. Search and filtering happen locally and no library data is
uploaded.

Select any library item to open it in the continuous player. The next queued
item is preloaded and starts automatically when the current item ends, including
audio-to-video transitions. The player includes seeking, volume, favorites,
previous/next navigation, and keyboard controls: **Space** toggles playback,
**N** advances, **P** goes back, and the arrow keys seek by five seconds.
Queue entries can be reordered directly in the player. Repeat and transition
settings, queue order, and paused playback positions persist in the library.

The current item, queue, favorites, playlists, and the latest 5,000 play actions
are stored locally in the same SQLite database. Removing a missing media file
during a refresh also removes its associated library state; StreamFetch never
deletes the media file itself. Browser autoplay rules can still require one
manual press before the first playback in a new browser session.

## Background downloads

Each submitted URL becomes an independent background job. Two sources can run
in parallel while the interface remains usable. Active jobs report progress,
speed, ETA, and the current filename. Pausing stops after the current fragment;
resuming uses yt-dlp's partial-download continuation. Advanced settings also
support bandwidth limits, concurrent fragments, time ranges, chapter splitting,
and optional SponsorBlock removal for supported YouTube sources.

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
Format selection and yt-dlp options are unit-tested without contacting either
platform.

## Deployment warning

StreamFetch is designed as a trusted, single-user local application. A remote
deployment downloads files onto the server, may expose browser cookies or local
paths, and can consume significant bandwidth and disk space. Do not expose it
to the public internet without authentication, quotas, isolation, and storage
controls.

## Roadmap

- Optional waveform and audio spectrum visualizations
- Persist background jobs across full app restarts
- Per-item selection before downloading a playlist
- Optional desktop packaging
- Internationalized interface

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md).

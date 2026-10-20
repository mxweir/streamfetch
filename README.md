<p align="center">
  <img src="docs/assets/streamfetch-mark.svg" width="112" alt="StreamFetch logo">
</p>

<h1 align="center">StreamFetch</h1>

<p align="center">
  <strong>Download. Organize. Play.</strong><br>
  A private, local-first media workspace for permitted YouTube and SoundCloud downloads.
</p>

<p align="center">
  <a href="https://github.com/mxweir/streamlit-media-downloader/actions/workflows/ci.yml"><img src="https://github.com/mxweir/streamlit-media-downloader/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mxweir/streamlit-media-downloader/releases/latest"><img src="https://img.shields.io/github/v/release/mxweir/streamlit-media-downloader?display_name=tag&sort=semver&color=8b7cff" alt="Latest release"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-ffcf4a.svg" alt="MIT license"></a>
</p>

<p align="center">
  <a href="#quick-start"><strong>Quick start</strong></a> ·
  <a href="#what-you-get"><strong>Features</strong></a> ·
  <a href="CHANGELOG.md"><strong>Changelog</strong></a> ·
  <a href="CONTRIBUTING.md"><strong>Contribute</strong></a>
</p>

<p align="center">
  <img src="docs/assets/releases/v1.1.0/product-tour.gif" width="760" alt="StreamFetch 1.1 product tour showing the branded app shell, collection selection, and visualizer player">
</p>

StreamFetch wraps [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) in a focused
Streamlit interface. Download permitted video or audio, keep it in a searchable
local library, and play it without sending your collection to a cloud service.

> [!IMPORTANT]
> Download only media you created, media in the public domain, or media you have
> permission to download. You are responsible for copyright, platform terms,
> and applicable law. StreamFetch does not bypass DRM and is not affiliated with
> YouTube, Google, or SoundCloud.

## Why StreamFetch?

| Local by design | More than a downloader | Built for real collections |
| --- | --- | --- |
| Media, metadata, favorites, playlists, and history stay on your device. | A persistent library and player turn downloads into a usable media workspace. | Search, filters, cover art, editable metadata, duplicate detection, and imports are included. |

## See it in action

<table>
  <tr>
    <td width="50%"><img src="docs/assets/releases/v1.1.0/app-shell.png" alt="StreamFetch 1.1 branded app shell"></td>
    <td width="50%"><img src="docs/assets/releases/v1.1.0/collection-selection.png" alt="Per-item selection for a YouTube collection"></td>
  </tr>
  <tr>
    <td align="center"><strong>One coherent app</strong><br><sub>New StreamFetch identity · local-first workspace · English and German</sub></td>
    <td align="center"><strong>Choose before downloading</strong><br><sub>Inspect playlists, channels, sets, and profiles · select only the items you want</sub></td>
  </tr>
</table>

<p align="center">
  <img src="docs/assets/releases/v1.1.0/player-visualizer.png" width="820" alt="Expanded StreamFetch player with live waveform and playback queue">
  <br>
  <strong>Floating player, smart queue, and live visuals</strong><br>
  <sub>Waveform or spectrum · continuous playback · drag to reorder · shuffle · repeat · crossfade · saved position</sub>
</p>

## What you get

### Download studio

- YouTube videos, playlists, channel tabs, and multiple URLs
- SoundCloud tracks, sets, playlists, profiles, and share links
- Video output as MP4, MKV, or WebM; audio as MP3, M4A, Opus, FLAC, or WAV
- Resolution and audio-quality controls, metadata, thumbnails, and subtitles
- Parallel background jobs with live progress, speed, ETA, pause, resume, and retry
- Durable job state that survives closing and fully restarting the app
- Per-item preview and selection before downloading playlists, channels, sets, or profiles
- Collection safety limits, bandwidth limits, fragment concurrency, clip ranges,
  chapter splitting, SponsorBlock, and optional browser cookies
- Download archive and cross-platform filename normalization

### Media library

- Rebuildable SQLite index for MP3, M4A, Opus, Ogg, FLAC, WAV, MP4, MKV, and WebM
- Embedded metadata and cover-art extraction with local search, filters, and sorting
- Favorites, custom playlists, history, ratings, tags, and editable display metadata
- Artist and album pages plus recently added, most played, highly rated, and unplayed views
- Recursive folder import and exact duplicate detection with SHA-256 confirmation

### Player

- Floating mini-player that becomes a full-width bottom bar on narrow screens
- Persistent current item, queue, playback position, volume, repeat, and transition settings
- Automatic queue advancement and next-item preloading across audio and video
- Previous/next, seek, shuffle, play-next, clear, remove, and drag-to-reorder controls
- Keyboard shortcuts: <kbd>Space</kbd> play/pause, <kbd>N</kbd> next,
  <kbd>P</kbd> previous, and arrow keys to seek five seconds
- Optional live waveform and audio-spectrum visualizations powered by the Web Audio API

### App experience

- English and German interface with an automatic system-language default
- StreamFetch logo and identity throughout the browser and native desktop shell
- Native desktop launcher powered by pywebview, plus a PyInstaller packaging profile

## Quick start

### 1. Install FFmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt update && sudo apt install ffmpeg

# Windows
winget install Gyan.FFmpeg
```

### 2. Install StreamFetch

```bash
git clone https://github.com/mxweir/streamlit-media-downloader.git
cd streamlit-media-downloader
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e .
```

### 3. Run it

```bash
streamlit run app.py
```

Open `http://localhost:8501`, paste one permitted URL per line, choose the
format, confirm permission, and start the download. Files are saved to
`downloads/` by default and organized by uploader and collection.

> [!TIP]
> Keep `yt-dlp` current. Some YouTube formats can also require a JavaScript
> runtime supported by yt-dlp.

## Native desktop app

Run StreamFetch in its own native window instead of a browser tab:

```bash
pip install -e ".[desktop]"
streamfetch-desktop
```

To create a standalone desktop build for the current operating system:

```bash
pip install -e ".[package]"
pyinstaller --clean packaging/streamfetch.spec
```

The build is written to `dist/StreamFetch`. Desktop bundles are platform-specific,
so build separately on macOS, Windows, or Linux for each target.

## Docker

```bash
docker build -t streamfetch .
docker run --rm -p 8501:8501 -v "$PWD/downloads:/app/downloads" streamfetch
```

Browser-cookie extraction is intended for a native local installation. It is
not available in the default container unless a browser profile is explicitly
mounted.

## How local storage works

Selecting **Library** indexes the chosen media directory in
`.streamfetch/library.db`. The database contains only rebuildable metadata and
player state; the original media remains authoritative. A refresh notices
added, changed, moved, or missing files. StreamFetch never deletes your media
when cleaning the index or reviewing duplicates.

Metadata edits in the app affect the local index, not the underlying media
file. Favorites, playlists, the queue, paused positions, and up to 5,000 recent
play actions live in the same local database.

Download jobs are stored separately in `~/.streamfetch/download-jobs.json`.
Completed and failed jobs return after a restart; interrupted jobs return paused
and can be resumed deliberately.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

The project supports Python 3.11, 3.12, and 3.13. Downloader option generation
is unit-tested without contacting YouTube or SoundCloud.

Release notes follow a visual, repeatable format. See [CHANGELOG.md](CHANGELOG.md)
for the history and [docs/RELEASING.md](docs/RELEASING.md) for the screenshot and
release checklist.

## Deployment and security

StreamFetch is designed as a trusted, single-user local application. A public
deployment can expose local paths or browser cookies and consume substantial
bandwidth and storage. Do not expose it to the internet without authentication,
quotas, isolation, and storage controls. Please report vulnerabilities through
[SECURITY.md](SECURITY.md).

## Version 1.1 roadmap: complete

The complete 1.1 roadmap is now shipped: restart-safe background jobs,
collection item selection, live audio visualizations, desktop packaging, and
English/German localization. See the [visual 1.1 release notes](docs/releases/v1.1.0.md)
for the implementation tour and verification details.

## Contributing

Issues and focused pull requests are welcome. Start with
[CONTRIBUTING.md](CONTRIBUTING.md), check the
[open issues](https://github.com/mxweir/streamlit-media-downloader/issues), and
keep examples free of private media, browser data, credentials, and personal
paths.

<p align="center">
  <sub>Built with Streamlit, yt-dlp, Mutagen, SQLite, and a local-first mindset.</sub>
</p>

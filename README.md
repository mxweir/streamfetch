<p align="center">
  <img src="docs/assets/streamfetch-mark.svg" width="112" alt="StreamFetch logo">
</p>

<h1 align="center">StreamFetch</h1>

<p align="center">
  <strong>Download. Organize. Play.</strong><br>
  A private, local-first media workspace for permitted YouTube and SoundCloud downloads.
</p>

<p align="center">
  <a href="https://github.com/mxweir/streamfetch/actions/workflows/ci.yml"><img src="https://github.com/mxweir/streamfetch/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mxweir/streamfetch/releases/latest"><img src="https://img.shields.io/github/v/release/mxweir/streamfetch?display_name=tag&sort=semver&color=8b7cff" alt="Latest release"></a>
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
  <img src="docs/assets/releases/v1.3.0/product-tour.gif" width="760" alt="StreamFetch 1.3 product tour showing subscriptions, new arrivals, source settings, and sync history">
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
    <td width="50%"><img src="docs/assets/releases/v1.3.0/new-arrivals.png" alt="StreamFetch new arrivals with selective synchronization"></td>
    <td width="50%"><img src="docs/assets/releases/v1.3.0/source-settings.png" alt="Per-source download presets, limits, and check intervals"></td>
  </tr>
  <tr>
    <td align="center"><strong>Follow your favorite sources</strong><br><sub>Discover new arrivals · choose what to sync · keep a local playlist</sub></td>
    <td align="center"><strong>Each source, your settings</strong><br><sub>Format presets · batch limits · startup checks · optional schedules</sub></td>
  </tr>
</table>

<p align="center">
  <img src="docs/assets/releases/v1.3.0/sync-history.png" width="820" alt="Persistent source check history showing five initial discoveries and no duplicates on the next check">
  <br>
  <strong>Know what changed since your last visit</strong><br>
  <sub>Persistent checks · new-item counts · download results · retryable failures</sub>
</p>

## What you get

### Subscriptions & Smart Sync

- Save YouTube channels and playlists or SoundCloud profiles, sets, and playlists
- Set a format preset, media folder, download batch limit, and inspection limit per source
- Preview new items and select what to download; completed items stay out of the next batch
- Recognize existing library items by their source URL and reuse completed subscription media
- Maintain a dedicated local playlist that follows the latest inspected source order
- Check manually, at startup, or at an optional interval while StreamFetch is running
- Keep per-source check history and retryable download results across restarts

Checks only discover new items. Downloads start after you select and confirm
them. Each check inspects up to 500 source entries in the platform's returned
order; older local items outside that window are retained.

### Download studio

- YouTube videos, playlists, channel tabs, and multiple URLs
- SoundCloud tracks, sets, playlists, profiles, and share links
- Video output as MP4, MKV, or WebM; audio as MP3, M4A, Opus, FLAC, or WAV
- Resolution and audio-quality controls, metadata, thumbnails, and subtitles
- Parallel background jobs with live progress, speed, ETA, pause, resume, cancel, and retry
- Automatic retry with backoff, scoped partial-file cleanup, and free-space estimates
- Presets for MP3, lossless audio, 1080p video, and archive quality
- Explicit resume, skip, or overwrite handling when a destination already exists
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
- Guided first-run setup and startup checks for FFmpeg, yt-dlp, JavaScript, and storage
- GitHub release notifications and optional backed-up, data-preserving updates
- Privacy-safe diagnostics that omit URLs, cookies, filenames, and absolute media paths
- Native desktop launcher plus automated macOS, Windows, and Linux release builds

## Quick start

### 1. Install system tools

```bash
# macOS
brew install ffmpeg node

# Ubuntu / Debian
sudo apt update && sudo apt install ffmpeg nodejs

# Windows
winget install Gyan.FFmpeg
winget install OpenJS.NodeJS.LTS
```

StreamFetch verifies FFmpeg, yt-dlp, a supported JavaScript runtime, and the
selected media folder during setup. If something is missing, it shows the exact
installation command for the current operating system.

### 2. Install StreamFetch

```bash
git clone https://github.com/mxweir/streamfetch.git
cd streamfetch
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
`~/Downloads/StreamFetch` by default and organized by uploader and collection.

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

The build is written to `dist/StreamFetch.app` on macOS and to the matching
platform executable on Windows or Linux. Tagged GitHub releases automatically
build a DMG, Windows EXE, and Linux archive. Signing and notarization run when
the repository's optional signing secrets are configured.

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

App preferences, update metadata, and pre-update backups live in
`~/.streamfetch/`. Before any update is installed or staged, StreamFetch creates
a ZIP containing settings, job state, and a consistent SQLite snapshot. Media
files are never copied, replaced, or deleted by the updater. Source checkouts
are only updated automatically when they are clean and currently on `main`.

Subscriptions and sync history live in `~/.streamfetch/subscriptions.db`.
Subscription downloads are stored inside each source's selected media folder
under `Subscriptions/`. Open that folder in Library to play or organize them.
Removing a source keeps its files and local playlist. Update backups include
the subscriptions database and the library index for every source folder.

## Updates and diagnostics

The optional startup check reads the latest public GitHub release and caches the
result for six hours. Updates are handled according to the installation type:

- Source checkout: fast-forward `main`, then refresh the desktop dependencies.
- Python package: upgrade from the matching GitHub release tag.
- Standalone desktop build: download the platform artifact and let the operating
  system open it after StreamFetch has staged the backup.

Automatic installation is off by default. Update checks can also be disabled.
The diagnostics ZIP is designed for issue reports and intentionally excludes
download URLs, browser cookies, media filenames, and absolute media paths.

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

## Version 1.3: subscriptions and smart sync

Version 1.3 gives your sources a permanent home: saved subscriptions,
new-arrival previews, configurable checks, selective synchronization, persistent
history, and source-ordered local playlists. See the
[visual 1.3 release notes](docs/releases/v1.3.0.md) for the implementation tour
and verification details.

## Contributing

Issues and focused pull requests are welcome. Start with
[CONTRIBUTING.md](CONTRIBUTING.md), check the
[open issues](https://github.com/mxweir/streamfetch/issues), and
keep examples free of private media, browser data, credentials, and personal
paths.

<p align="center">
  <sub>Built with Streamlit, yt-dlp, Mutagen, SQLite, and a local-first mindset.</sub>
</p>

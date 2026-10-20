# Changelog

Every StreamFetch release is documented with the same visual format: a short
summary, an authentic product image, user-visible changes, upgrade notes, and
verification details. Full visual notes live in [`docs/releases`](docs/releases).

## [1.1.0] — Roadmap complete

_Released 2026-10-20 · [Full visual release notes](docs/releases/v1.1.0.md)_

<p align="center">
  <img src="docs/assets/releases/v1.1.0/product-tour.gif" width="680" alt="StreamFetch 1.1 product tour">
</p>

### Highlights

- Persisted background jobs across complete app restarts, including safe recovery of interrupted work.
- Added per-item selection for playlists, channels, SoundCloud sets, and profiles.
- Added optional live waveform and spectrum modes to the floating player.
- Added English/German localization, the new StreamFetch logo throughout the app, and a native desktop launcher.
- Added a repeatable PyInstaller profile for platform-specific desktop bundles.

### Quality

- 51 automated tests with 82% measured coverage at release time.
- CI verified on Python 3.11, 3.12, and 3.13.
- Browser QA covered the real collection inspector, both visualizer modes, and live language switching.
- No library migration required; existing local databases remain compatible.

## [1.0.0] — The local media workspace

_Released 2026-10-20 · [Full visual release notes](docs/releases/v1.0.0.md)_

<p align="center">
  <img src="docs/assets/product-tour.gif" width="680" alt="StreamFetch 1.0 product tour">
</p>

### Highlights

- Rebuilt the interface as a premium, responsive desktop-style media app.
- Added a floating player with an expandable, reorderable smart queue.
- Introduced a library home with fresh additions and most-played shelves.
- Consolidated secondary media actions into focused card menus.
- Completed desktop and narrow-screen browser QA.

### Quality

- 40 automated tests with 84% measured coverage at release time.
- CI verified on Python 3.11, 3.12, and 3.13.
- No migration required; existing local library databases remain compatible.

## Earlier releases

| Version | Focus | Release |
| --- | --- | --- |
| 0.9.0 | Local library hub and discovery | [Notes](https://github.com/mxweir/streamlit-media-downloader/releases/tag/v0.9.0) |
| 0.8.0 | Background download manager | [Notes](https://github.com/mxweir/streamlit-media-downloader/releases/tag/v0.8.0) |
| 0.7.0 | Smart queue controls | [Notes](https://github.com/mxweir/streamlit-media-downloader/releases/tag/v0.7.0) |
| 0.6.0 | Continuous queue player | [Notes](https://github.com/mxweir/streamlit-media-downloader/releases/tag/v0.6.0) |
| 0.5.0 | Persistent player and collections | [Notes](https://github.com/mxweir/streamlit-media-downloader/releases/tag/v0.5.0) |
| 0.4.0 | Persistent local media library | [Notes](https://github.com/mxweir/streamlit-media-downloader/releases/tag/v0.4.0) |
| 0.3.0 | Pastel interface redesign | [Notes](https://github.com/mxweir/streamlit-media-downloader/releases/tag/v0.3.0) |
| 0.2.0 | SoundCloud support | [Notes](https://github.com/mxweir/streamlit-media-downloader/releases/tag/v0.2.0) |
| 0.1.0 | Initial YouTube downloader | [Notes](https://github.com/mxweir/streamlit-media-downloader/releases/tag/v0.1.0) |

[1.0.0]: https://github.com/mxweir/streamlit-media-downloader/releases/tag/v1.0.0
[1.1.0]: https://github.com/mxweir/streamlit-media-downloader/releases/tag/v1.1.0

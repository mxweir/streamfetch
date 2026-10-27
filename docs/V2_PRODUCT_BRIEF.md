# StreamFetch 2.0 product brief

_Decision record · 2026-10-27_

## Product promise

**Collect. Curate. Take anywhere.** StreamFetch is a personal, local-first media
workspace, not a cloud streaming service. The 2.0 milestone improves a complete
workflow: capture a permitted source, download deliberately, find useful moments,
organize tracks and export originals for another device or player.

Success is less repeated work and more confidence in the results, not a larger
settings menu. Existing libraries and user choices must remain valuable.

## Ten-role review

This is a ten-role agent review, not a claim that ten human employees worked on
the product. Roles are review lenses and ownership boundaries; implementation
and verification evidence belong in the release notes.

| Role | Decision contributed | Acceptance focus |
| --- | --- | --- |
| Project manager | Ship a coherent end-to-end 2.0 rather than unrelated feature count. | Integrate, verify, document and publish one releasable milestone. |
| Product manager | Connect capture, discovery, curation and portability. | Every new feature has a clear user task and boundary. |
| UX designer | One primary navigation and a useful Overview. | Users can identify where to save links, download, search and manage media. |
| Senior application developer | Keep existing services and state rather than rewrite the stack. | Existing workflows remain available; state survives restarts. |
| Download reliability engineer | Separate output profiles and track real job artifacts. | MP4 does not suppress MP3; clips and quality variants do not collide. |
| Search engineer | Search local metadata and meaningful moments together. | Timestamp results open the correct media and current position. |
| Library/data engineer | Make collection actions batch-oriented and exports portable. | Selected originals, playlist and hashes agree; export limits are enforced. |
| Security reviewer | Preserve local trust boundaries and disclose export/inbox privacy. | No new public download endpoint, automatic authentication or hidden tag rewriting. |
| QA/release engineer | Distinguish unit tests, browser checks and platform builds. | Report actual results, keep failure cases covered, do not invent device evidence. |
| Marketing/documentation lead | Explain productive value with authentic screenshots. | README and visual release notes match shipped behavior and limitations. |

## Scope and acceptance criteria

### 1. Capture without committing to a download

- Save supported links in a persistent offline-capable inbox.
- Deduplicate URLs and expose ready, handed-off and archived states.
- Do not silently fetch previews, download media or infer permission from a URL.
- Hand off explicitly into the download workspace; keep secrets in local state.

### 2. Find files and useful moments

- Search indexed metadata, bookmarks and non-outdated transcript segments.
- Return exact timestamp actions for moments and normal media actions for files.
- Remain useful without Whisper: metadata, bookmarks and imported subtitles work.
- Avoid promising semantic AI search, automatically generated transcripts or a
  global player when those are not implemented.

### 3. Curate once, take a collection elsewhere

- Apply favorites, queue and playlist actions to multiple selected tracks.
- Export originals, a relative-path M3U8 playlist and a SHA-256 manifest together.
- Enforce 200-track and 200-MiB total archive limits before offering a download.
- Keep generated metadata free of absolute database paths or app secrets.
- Preserve original bytes and disclose that embedded URLs/comments remain present.
- Do not implement or advertise ZIP import, account sync or a new home-player API.

### 4. Make downloading dependable

- Scope completed-download archives to output profiles.
- Use distinct filenames for media type, quality and clip variants.
- Associate final files with their own job rather than folder-scan timing.
- Invalidate the library index once after a completed batch, not per fragment.
- Retain 1.9 independent engine updates and deliberate authentication choices.

### 5. Make the product legible

- Compact app bar; Overview, Inbox, Download, Search, Library, Subscriptions and
  System in the primary sidebar.
- Overview shows useful current state: continue listening, recent media and jobs.
- Library owns actual playback; other workspaces use explicit navigation actions.
- Capture real screenshots of Overview, Inbox, Search and Collections.

## Preservation and non-goals

Preserve downloaded originals, editable metadata, favorites, playlists, watched
folders, transcripts, bookmarks, player positions, subscriptions, presets, engine
updates, certificate identity and existing explicit home-player permissions.

Not included: cloud hosting/accounts, commercial music catalog access, DRM
bypass, automatic source downloading from the inbox, synchronized multi-room
playback, uninterrupted cross-workspace audio, native mobile apps, automatic
certificate trust, ZIP restore or comprehensive interactive Windows/phone proof
merely because builds pass.

## Release gate

Release only after the integrated application passes the final measured tests
and lint checks, critical browser flows are exercised, actual product screenshots
are captured, README/changelog are consistent, and GitHub release artifacts are
verified. Record measured evidence in the release notes and disclose any untested
physical-device/platform behavior honestly.

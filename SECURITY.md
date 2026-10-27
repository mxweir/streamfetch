# Security policy

## Supported versions

Only the latest release and current `main` are supported.

## Local and home-network boundaries

The administrative Streamlit interface binds to loopback by default. Do not
publicly expose it. The optional home player runs on a separate port and shares
media from one explicitly selected library. It never exposes administrative
downloads from online sources, settings, filesystem browsing, cookie extraction
or operating-system command execution.

Since 1.8, paired devices can persist progress for indexed tracks. Computer
playback control and saving original-file copies are separate explicit permissions,
both disabled by default and scoped to all paired devices in that sharing session.
These are not per-device ACLs. Do not pair untrusted devices. Revoking permission
blocks new requests and pending commands; copies already received cannot be erased.
Original downloads revalidate containment and use attachment filenames. Stopping
sharing also interrupts ongoing transfers as the next streaming chunk is sent.

Remote commands affect only an open StreamFetch library player. A ten-second
controller lease prevents multiple desktop tabs from claiming the same speaker.
Commands expire after ten seconds, use a bounded queue and require acknowledgements;
browser-autoplay rejection is reported rather than claimed as a successful handoff.
The control/progress endpoints require an authenticated session, enforce Host/Origin,
bound request sizes and finite numeric values, and limit clients to 120 updates/minute.
Playback position is private library metadata, backed up with its database.

Loudness analysis decodes locally through FFmpeg and stores measurements keyed by
file size and modification time. Web Audio gain changes playback only; source
files are never rewritten. No audio is sent to a cloud service for this feature.

Home-player pairing codes are generated for each sharing session. Browser
sessions use Secure, HttpOnly, SameSite=Strict cookies and expire after 12 hours.
Stopping sharing revokes sessions; sharing is disabled after process restart.
Login throttling and Host/Origin checks reduce common browser-based attacks.

Since 1.7 the home player requires TLS 1.2 or newer, without an HTTP fallback.
Each installation creates its own private CA, restricted to RFC1918/loopback IPs
and localhost names. Leaf certificates last at most 90 days. The public CA
certificate must be transferred privately, fingerprint-checked and explicitly
trusted on the phone. StreamFetch never changes OS/browser trust stores or asks
users to bypass certificate warnings. Device/browser policies may forbid local CAs.

QR credentials contain 256 bits of randomness, live for two minutes, and are
redeemed atomically once. Generating a new code revokes the previous code. The
credential is in a URL fragment (not sent in GET requests), removed from browser
history before being POSTed over TLS. Never share screenshots of a live QR code.
Tokens and sessions stay in memory and are revoked on stop/restart. Host/Origin
checks, login throttling and a 32-session cap apply to both pairing methods.

The private CA key lives in `home-tls/identity.json` in the application state
directory, outside the installed application. POSIX files/directories are created
with 0600/0700 permissions; Windows protection depends on the user's profile ACLs.
Updates preserve this identity, but it is deliberately excluded from portable
update/diagnostic ZIPs. Back it up only to protected private storage. A missing
identity creates a new CA requiring phone re-enrollment; corrupt/expired identities
fail closed and are never silently replaced. The CA lasts five years. Remove its
trust from phones before intentionally replacing or retiring an installation.

TLS does not make this an internet-facing server. Use trusted home Wi-Fi only.
Do not port-forward it, publish it through a tunnel, or expose the administrative UI.

Transcription runs locally. Downloading an uncached model contacts Hugging Face
only after consent. Media tagging requires explicit confirmation and creates a
full original-file backup before replacing a file. Backups contain private media;
protect them like your library and do not attach them to issue reports.

## Workspace, inbox and collection exports

Since 2.0, the link inbox stores URLs and notes locally without fetching them.
Private SoundCloud share tokens are retained when required for access. Protect
`inbox.db` and pre-update backups; never attach them to public issue reports.
Hand-off only prepares the download editor and never starts a job by itself.
Local search reads indexed metadata, bookmarks and current transcript segments;
it does not send queries or media to an online search service.

Collection ZIPs contain explicitly selected original files, relative M3U8 paths
and a versioned, allowlisted size/SHA-256 metadata manifest. Limits are 200 tracks
and a 200 MiB archive. The exporter refuses symlinks and special files. POSIX
opens each directory relative to a verified directory descriptor; Windows
validates the actual opened file handle's resolved path before reading. Path
containment is checked again at export time, not merely when indexing media.
There is no ZIP-import endpoint or additional home-player download API.

Original media bytes are preserved, including embedded URLs, comments and tags.
The manifest does not add absolute database paths or application credentials,
but an export is not a privacy scrubber. Review files before sharing them.
Prepared exports remain private local artifacts until explicitly downloaded or
distributed. They are not a complete app-state backup or restore format.

## Download-engine updates

Since 1.9, engine checks contact PyPI automatically at startup and before use
(six-hour cache), separately from optional GitHub app-release checks. Only stable
pure-Python yt-dlp, its pinned EJS solver and certifi wheels from the official
PyPI HTTPS endpoints are accepted. SHA-256 digests are checked before extraction;
archive traversal, symlinks, unexpected top-level files and oversized archives are
rejected. This trusts the publishers and PyPI, not an independent code audit.
Bundles are immutable and live in the current user's app-state directory, not
system Python. Loaded engines are never hot-replaced; prepared updates require a
full app restart. Failed/offline checks retain the installed engine. Unsupported
Python/mandatory dependencies require a StreamFetch update. No media is migrated.

Saved presets contain only allowlisted format/options fields. URLs, output paths
and cookie-browser selections are excluded. Presets join normal pre-update state
backups. Technical error details redact home directories, URLs and common secret
headers; still review details before sharing. Error classification is heuristic
guidance, not proof of the upstream cause. Cookie access always remains explicit.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not open a
public issue for vulnerabilities involving cookie extraction, path handling,
server-side requests, command execution, or sensitive data exposure.

Never attach browser profiles, cookie databases, tokens, downloaded private
media, or personally identifiable information to an issue or pull request.

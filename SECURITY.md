# Security policy

## Supported versions

Only the latest release and current `main` are supported.

## Local and home-network boundaries

The administrative Streamlit interface binds to loopback by default. Do not
publicly expose it. The optional home player runs on a separate port and shares
read-only media from one explicitly selected library. It never exposes download,
settings, filesystem browsing or cookie-extraction endpoints.

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

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not open a
public issue for vulnerabilities involving cookie extraction, path handling,
server-side requests, command execution, or sensitive data exposure.

Never attach browser profiles, cookie databases, tokens, downloaded private
media, or personally identifiable information to an issue or pull request.

# Security policy

## Supported versions

Only the latest release and current `main` are supported.

## Local and home-network boundaries

The administrative Streamlit interface binds to loopback by default. Do not
publicly expose it. The optional home player runs on a separate port and shares
read-only media from one explicitly selected library. It never exposes download,
settings, filesystem browsing or cookie-extraction endpoints.

Home-player pairing codes are generated for each sharing session. Browser
sessions use HttpOnly, SameSite=Strict cookies and expire after 12 hours.
Stopping sharing revokes sessions; sharing is disabled after process restart.
Login throttling and Host/Origin checks reduce common browser-based attacks.

The home player intentionally uses HTTP, not TLS. Pairing codes, session cookies
and media may be observed by other parties on an untrusted network. Use trusted
home Wi-Fi only. Do not port-forward it, publish it through a tunnel, or treat it
as an internet-facing authenticated media server.

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

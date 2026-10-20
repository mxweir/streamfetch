"""Premium StreamFetch visual system for the Streamlit interface."""

APP_CSS = """
<style>
:root {
    --sf-ink: #17151c;
    --sf-ink-soft: #3f3b48;
    --sf-paper: #fffdf7;
    --sf-canvas: #efedf5;
    --sf-line: #d7d2df;
    --sf-blue: #75b8ff;
    --sf-mint: #8ce0b7;
    --sf-lilac: #d9b8ff;
    --sf-violet: #7255d9;
    --sf-yellow: #ffd95a;
    --sf-coral: #ff765f;
}

html, body, [class*="css"] {
    font-family: Inter, Satoshi, "Helvetica Neue", Arial, sans-serif;
}

.stApp,
[data-testid="stAppViewContainer"] > .main {
    background:
        radial-gradient(circle at 78% 0%, rgba(217, 184, 255, .55), transparent 28rem),
        var(--sf-canvas);
    color: var(--sf-ink);
}

[data-testid="stHeader"] { background: transparent; }

.block-container {
    max-width: 1460px;
    padding: 1.25rem 2.25rem 10rem;
}

p, label, [data-testid="stMarkdownContainer"] { color: inherit; }

.sf-appbar {
    align-items: center;
    display: flex;
    justify-content: space-between;
    margin-bottom: .85rem;
    min-height: 52px;
    padding: .45rem .65rem .45rem .5rem;
    background: rgba(255, 253, 247, .8);
    border: 1px solid rgba(23, 21, 28, .14);
    border-radius: 18px;
    backdrop-filter: blur(18px);
    box-shadow: 0 12px 36px rgba(36, 29, 53, .08);
}

.sf-appbar__brand,
.sf-appbar__status {
    align-items: center;
    display: flex;
    gap: .7rem;
}

.sf-logo {
    display: grid;
    height: 36px;
    width: 36px;
    place-items: center;
    border-radius: 11px;
    background: var(--sf-ink);
    color: #fff;
    font-size: .74rem;
    font-weight: 900;
    letter-spacing: -.04em;
}

.sf-appbar strong { font-size: .93rem; letter-spacing: -.02em; }
.sf-appbar small { color: #716b79; font-size: .72rem; }

.sf-status-dot {
    height: 8px;
    width: 8px;
    border-radius: 50%;
    background: #25b16b;
    box-shadow: 0 0 0 4px rgba(37, 177, 107, .13);
}

.sf-hero {
    align-items: end;
    display: grid;
    grid-template-columns: minmax(0, 1.45fr) minmax(250px, .55fr);
    gap: 2rem;
    min-height: 230px;
    overflow: hidden;
    position: relative;
    margin-bottom: 1rem;
    padding: 2rem 2.2rem;
    border: 1px solid rgba(23, 21, 28, .18);
    border-radius: 30px;
    background: var(--sf-ink);
    box-shadow: 0 20px 60px rgba(32, 25, 47, .15);
    color: #fff;
}

.sf-hero::after {
    content: "";
    position: absolute;
    inset: -80px -100px auto auto;
    width: 430px;
    height: 240px;
    border: 58px solid var(--sf-lilac);
    border-radius: 50%;
    opacity: .92;
    transform: rotate(-14deg);
}

.sf-hero__copy,
.sf-hero__aside { position: relative; z-index: 1; }

.sf-eyebrow {
    color: var(--sf-mint);
    font-size: .69rem;
    font-weight: 850;
    letter-spacing: .13em;
    text-transform: uppercase;
}

.sf-hero h1 {
    max-width: 820px;
    margin: .65rem 0 .8rem;
    color: #fff;
    font-family: "Arial Black", Impact, sans-serif;
    font-size: clamp(2.7rem, 6vw, 5.4rem);
    letter-spacing: -.07em;
    line-height: .88;
    text-transform: uppercase;
}

.sf-hero h1 span { color: var(--sf-lilac); }

.sf-hero p {
    max-width: 650px;
    margin: 0;
    color: #cbc6d1;
    font-size: clamp(.95rem, 1.7vw, 1.12rem);
    line-height: 1.5;
}

.sf-hero__aside {
    display: grid;
    gap: .55rem;
    justify-items: end;
}

.sf-pill {
    display: inline-flex;
    align-items: center;
    gap: .45rem;
    padding: .56rem .8rem;
    border: 1px solid rgba(255,255,255,.23);
    border-radius: 999px;
    background: rgba(255,255,255,.1);
    color: #fff;
    font-size: .7rem;
    font-weight: 800;
    letter-spacing: .06em;
    text-transform: uppercase;
    backdrop-filter: blur(10px);
}

.sf-pill--accent {
    background: var(--sf-yellow);
    border-color: var(--sf-yellow);
    color: var(--sf-ink);
}

.sf-legal {
    align-items: center;
    display: flex;
    gap: .75rem;
    margin-bottom: 1rem;
    padding: .75rem .9rem;
    border: 1px solid rgba(23, 21, 28, .12);
    border-radius: 14px;
    background: rgba(255, 253, 247, .64);
    color: #625d69;
    font-size: .77rem;
}

.sf-legal__icon {
    display: grid;
    flex: 0 0 28px;
    height: 28px;
    place-items: center;
    border-radius: 9px;
    background: var(--sf-yellow);
}

.sf-section-label {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    margin: .25rem 0 .7rem;
    color: #67616e;
    font-size: .69rem;
    font-weight: 850;
    letter-spacing: .1em;
    text-transform: uppercase;
}

.sf-section-label::before {
    content: "";
    width: 19px;
    height: 2px;
    background: var(--sf-violet);
}

.sf-view-heading { margin: .3rem 0 1rem; }
.sf-view-heading h2 {
    margin: 0;
    color: var(--sf-ink);
    font-family: "Arial Black", Impact, sans-serif;
    font-size: clamp(2rem, 4vw, 3.5rem);
    letter-spacing: -.055em;
    line-height: 1;
}
.sf-view-heading p { margin: .45rem 0 0; color: #696270; }

[data-testid="stSidebar"] {
    border-right: 0;
    background: var(--sf-ink);
    color: #f9f7ff;
}

[data-testid="stSidebar"] > div:first-child { padding-top: 1.25rem; }
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { color: #f9f7ff; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.16) !important; }

.sf-sidebar-brand {
    margin-bottom: 1.25rem;
    padding: .2rem .1rem .8rem;
}
.sf-sidebar-brand__top { align-items: center; display: flex; gap: .75rem; }
.sf-sidebar-brand .sf-logo { background: var(--sf-lilac); color: var(--sf-ink); }
.sf-sidebar-brand strong {
    display: block;
    color: #fff;
    font-family: "Arial Black", Impact, sans-serif;
    font-size: 1.35rem;
    letter-spacing: -.045em;
    line-height: 1;
}
.sf-sidebar-brand span {
    display: block;
    margin-top: .8rem;
    color: #938d9c;
    font-size: .66rem;
    font-weight: 800;
    letter-spacing: .1em;
    text-transform: uppercase;
}

[data-testid="stVerticalBlock"]:has(
    > [data-testid="stElementContainer"] .sf-card-marker
),
[data-testid="stVerticalBlock"]:has(
    > [data-testid="stElementContainer"] .sf-library-card-marker
),
[data-testid="stVerticalBlock"]:has(
    > [data-testid="stElementContainer"] .sf-history-marker
) {
    border: 1px solid rgba(23, 21, 28, .12) !important;
    border-radius: 22px !important;
    background: rgba(255, 253, 247, .94);
    box-shadow: 0 14px 34px rgba(38, 31, 53, .07) !important;
    padding: 1rem !important;
}

.sf-card-marker,
.sf-library-card-marker,
.sf-player-marker,
.sf-history-marker { display: none; }

.sf-cover-placeholder {
    display: grid;
    width: 100%;
    aspect-ratio: 1;
    place-items: center;
    overflow: hidden;
    border-radius: 17px;
    background:
        radial-gradient(circle at 70% 20%, rgba(255,255,255,.7), transparent 25%),
        linear-gradient(140deg, var(--sf-blue), var(--sf-lilac));
}
.sf-cover-placeholder span {
    display: grid;
    width: 72px;
    height: 72px;
    place-items: center;
    border-radius: 23px;
    background: var(--sf-ink);
    color: #fff;
    font-size: 2.1rem;
    box-shadow: 0 14px 26px rgba(23,21,28,.2);
    transform: rotate(-5deg);
}

[data-testid="stImage"] img {
    border: 0;
    border-radius: 17px;
    aspect-ratio: 1;
    object-fit: cover;
}

.sf-media-title {
    margin-top: .8rem;
    overflow: hidden;
    color: var(--sf-ink);
    font-size: 1.07rem;
    font-weight: 850;
    letter-spacing: -.025em;
    line-height: 1.08;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.sf-media-artist { margin-top: .35rem; color: #4e4854; font-size: .82rem; font-weight: 750; }
.sf-media-album { color: #86808c; font-size: .74rem; }

.sf-stats {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: .7rem;
    margin: .8rem 0 1rem;
}
.sf-stat,
[data-testid="stMetric"] {
    min-height: 92px;
    padding: .9rem 1rem;
    border: 1px solid rgba(23, 21, 28, .1);
    border-radius: 17px;
    background: rgba(255, 253, 247, .8);
    box-shadow: 0 10px 25px rgba(35,29,49,.05);
}
.sf-stat { display: flex; flex-direction: column; justify-content: center; }
.sf-stat span { color: #746e7a; font-size: .76rem; }
.sf-stat strong {
    margin-top: .2rem;
    color: var(--sf-ink);
    font-size: clamp(1.3rem, 2vw, 1.9rem);
    letter-spacing: -.04em;
}
[data-testid="stMetric"] [data-testid="stMetricLabel"] { color: #746e7a; }
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: var(--sf-ink);
    font-size: clamp(1.3rem, 2vw, 1.9rem);
    font-weight: 850;
    letter-spacing: -.04em;
}

.stTextInput [data-baseweb="input"],
.stTextArea [data-baseweb="textarea"],
.stSelectbox [data-baseweb="select"] > div,
.stNumberInput [data-baseweb="input"],
.stMultiSelect [data-baseweb="select"] > div {
    border: 1px solid rgba(23, 21, 28, .2) !important;
    border-radius: 13px !important;
    background: var(--sf-paper) !important;
    box-shadow: none !important;
}

[data-testid="stSidebar"] .stTextInput [data-baseweb="input"],
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div,
[data-testid="stSidebar"] .stNumberInput [data-baseweb="input"],
[data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] > div {
    border-color: rgba(255,255,255,.18) !important;
    background: #29262f !important;
    color: #fff !important;
}

.stButton > button,
.stDownloadButton > button,
[data-testid="stPopover"] > button {
    min-height: 2.55rem;
    border: 1px solid rgba(23, 21, 28, .18) !important;
    border-radius: 12px !important;
    background: var(--sf-paper) !important;
    color: var(--sf-ink) !important;
    box-shadow: none !important;
    font-size: .71rem !important;
    font-weight: 800 !important;
    letter-spacing: .025em;
    transition: transform 120ms ease, box-shadow 120ms ease, background 120ms ease;
}
.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="stPopover"] > button:hover {
    background: #fff !important;
    box-shadow: 0 8px 18px rgba(28,23,39,.1) !important;
    transform: translateY(-1px);
}
.stButton > button[kind="primary"] { background: var(--sf-ink) !important; color: #fff !important; }
.stButton > button[kind="primary"] p { color: #fff !important; }
.stButton > button[kind="primary"]:hover { background: var(--sf-violet) !important; }
.stButton > button:disabled {
    background: #dedbe3 !important;
    color: #77727c !important;
    transform: none;
}

.stRadio [role="radiogroup"],
[data-testid="stSegmentedControl"] [role="radiogroup"] {
    gap: .25rem;
    padding: .28rem;
    border: 1px solid rgba(23,21,28,.12);
    border-radius: 14px;
    background: rgba(255,253,247,.62);
}
.stRadio [role="radiogroup"] label,
[data-testid="stSegmentedControl"] label {
    border: 0;
    border-radius: 10px;
}

[data-testid="stExpander"],
[data-testid="stAlert"] {
    border: 1px solid rgba(23, 21, 28, .13) !important;
    border-radius: 16px !important;
    background: rgba(255,253,247,.78);
    box-shadow: none !important;
}
[data-testid="stAlert"] { color: var(--sf-ink); }
[data-testid="stProgressBar"] > div > div { background: var(--sf-violet) !important; }
[data-testid="stDataFrame"] { overflow: hidden; border-radius: 16px; }
hr { border-color: rgba(23,21,28,.13) !important; }

/* Components v2 inherit layout containment from Streamlit. Pin the outer
   element so the player is truly viewport-relative instead of block-relative. */
[data-streamfetch-player-dock],
[data-testid="stElementContainer"]:has([data-testid="stBidiComponentIsolated"]),
[data-testid="stElementContainer"]:has(.sf-continuous-player) {
    bottom: 22px;
    position: fixed !important;
    right: 24px;
    width: min(700px, calc(100vw - 48px)) !important;
    z-index: 2147483000;
}

@media (max-width: 780px) {
    .block-container { padding: .8rem .8rem 9rem; }
    .sf-appbar__status small { display: none; }
    .sf-hero {
        grid-template-columns: 1fr;
        min-height: 245px;
        padding: 1.5rem;
        border-radius: 23px;
    }
    .sf-hero__aside { display: none; }
    .sf-hero h1 { font-size: clamp(2.55rem, 13vw, 4.4rem); }
    .sf-legal { align-items: flex-start; }
    [data-testid="stMetric"] { min-height: 82px; }
    .sf-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .sf-stat { min-height: 72px; }
    .sf-stat:last-child { grid-column: 1 / -1; }
    [data-streamfetch-player-dock],
    [data-testid="stElementContainer"]:has([data-testid="stBidiComponentIsolated"]),
    [data-testid="stElementContainer"]:has(.sf-continuous-player) {
        bottom: 10px;
        right: 10px;
        width: calc(100vw - 20px) !important;
    }
}
</style>
"""

HERO_HTML = """
<header class="sf-appbar">
    <div class="sf-appbar__brand">
        <span class="sf-logo">SF</span>
        <div><strong>StreamFetch</strong><br><small>Local media studio · 1.0</small></div>
    </div>
    <div class="sf-appbar__status">
        <span class="sf-status-dot"></span><small>Private on this device</small>
    </div>
</header>
<section class="sf-hero">
    <div class="sf-hero__copy">
        <span class="sf-eyebrow">Download · Organize · Play</span>
        <h1>Your media.<br><span>Your rules.</span></h1>
        <p>A focused local home for permitted YouTube and SoundCloud downloads,
        playlists, and the music you already own.</p>
    </div>
    <div class="sf-hero__aside">
        <span class="sf-pill sf-pill--accent">Local first</span>
        <span class="sf-pill">YouTube + SoundCloud</span>
        <span class="sf-pill">Powered by yt-dlp</span>
    </div>
</section>
"""

LEGAL_HTML = """
<div class="sf-legal">
    <span class="sf-legal__icon">⚖</span>
    <span>Only download media you created, that is in the public domain, or that
    you have permission to download. Respect copyright, platform terms, and local law.</span>
</div>
"""

SIDEBAR_HEADER_HTML = """
<div class="sf-sidebar-brand">
    <div class="sf-sidebar-brand__top"><span class="sf-logo">SF</span>
    <strong>Download<br>studio.</strong></div>
    <span>Format · quality · automation</span>
</div>
"""

LIBRARY_SIDEBAR_HTML = """
<div class="sf-sidebar-brand">
    <div class="sf-sidebar-brand__top"><span class="sf-logo">SF</span>
    <strong>Your<br>library.</strong></div>
    <span>Search · filter · rediscover</span>
</div>
"""

SOURCE_LABEL_HTML = '<div class="sf-section-label">New download</div>'
PREVIEW_LABEL_HTML = '<div class="sf-section-label">Source preview</div>'
RESULT_LABEL_HTML = '<div class="sf-section-label">Download activity</div>'
LIBRARY_LABEL_HTML = '<div class="sf-section-label">Local library</div>'

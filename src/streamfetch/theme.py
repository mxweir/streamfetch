"""Slush-inspired visual theme for the Streamlit interface."""

APP_CSS = """
<style>
:root {
    --sf-black: #000000;
    --sf-white: #ffffff;
    --sf-sky: #dceeff;
    --sf-gray: #cccccc;
    --sf-mist: #e9e9e9;
    --sf-blue: #4da2ff;
    --sf-mint: #55db9c;
    --sf-lavender: #e9ccff;
    --sf-orange: #fb4903;
    --sf-yellow: #ffd731;
    --sf-violet: #5c4ade;
}

html, body, [class*="css"] {
    font-family: Inter, Satoshi, "Helvetica Neue", Arial, sans-serif;
}

.stApp {
    background: var(--sf-sky);
    color: var(--sf-black);
}

[data-testid="stHeader"] {
    background: transparent;
}

[data-testid="stAppViewContainer"] > .main {
    background: var(--sf-sky);
}

.block-container {
    max-width: 1280px;
    padding: 2.5rem 3rem 5rem;
}

p, label, [data-testid="stMarkdownContainer"] {
    color: var(--sf-black);
}

.sf-marquee {
    margin: -1rem 0 1.25rem;
    overflow: hidden;
    border: 1.5px solid var(--sf-black);
    border-radius: 9999px;
    background: var(--sf-black);
    color: var(--sf-white);
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.1em;
    line-height: 1;
    padding: 0.8rem 1.2rem;
    text-align: center;
    text-transform: uppercase;
    white-space: nowrap;
}

.sf-hero {
    min-height: 380px;
    position: relative;
    overflow: hidden;
    margin-bottom: 1.5rem;
    padding: 2.2rem 2.5rem 2.4rem;
    border: 1.5px solid var(--sf-black);
    border-radius: 40px;
    background: var(--sf-white);
}

.sf-hero::after {
    content: "";
    position: absolute;
    z-index: 0;
    width: 520px;
    height: 210px;
    top: 14px;
    right: -120px;
    border: 44px solid var(--sf-blue);
    border-radius: 50%;
    transform: rotate(-16deg);
}

.sf-hero__top,
.sf-hero__copy,
.sf-platforms {
    position: relative;
    z-index: 2;
}

.sf-hero__top {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    font-size: 0.74rem;
    font-weight: 800;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}

.sf-logo {
    display: inline-grid;
    width: 42px;
    height: 42px;
    place-items: center;
    border: 1.5px solid var(--sf-black);
    border-radius: 50%;
    background: var(--sf-yellow);
    font-size: 0.9rem;
    font-weight: 900;
    letter-spacing: -0.05em;
}

.sf-hero h1 {
    max-width: 850px;
    margin: 2.25rem 0 1.25rem;
    color: var(--sf-black);
    font-family: "Arial Black", Impact, Antonio, sans-serif;
    font-size: clamp(4rem, 9vw, 7.8rem);
    font-weight: 900;
    letter-spacing: -0.07em;
    line-height: 0.78;
    text-transform: uppercase;
}

.sf-hero h1 span {
    color: var(--sf-violet);
}

.sf-hero__copy {
    max-width: 610px;
    margin: 0;
    font-size: clamp(1rem, 2vw, 1.35rem);
    font-weight: 600;
    line-height: 1.35;
}

.sf-platforms {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 1.5rem;
}

.sf-pill,
.sf-sticker {
    border: 1.5px solid var(--sf-black);
    color: var(--sf-black);
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.sf-pill {
    border-radius: 9999px;
    background: var(--sf-white);
    padding: 0.55rem 0.85rem;
}

.sf-pill--blue { background: var(--sf-blue); }
.sf-pill--mint { background: var(--sf-mint); }
.sf-pill--lavender { background: var(--sf-lavender); }

.sf-sticker {
    position: absolute;
    z-index: 3;
    right: 2.2rem;
    bottom: 2rem;
    padding: 0.9rem 1.1rem;
    border-radius: 18px;
    background: var(--sf-orange);
    transform: rotate(7deg);
}

.sf-legal {
    display: flex;
    gap: 0.8rem;
    align-items: flex-start;
    margin-bottom: 1.5rem;
    padding: 1rem 1.15rem;
    border: 1.5px solid var(--sf-black);
    border-radius: 20px;
    background: var(--sf-yellow);
    color: var(--sf-black);
    font-size: 0.88rem;
    font-weight: 600;
}

.sf-legal__icon {
    font-size: 1.15rem;
    line-height: 1;
}

.sf-section-label {
    display: inline-block;
    margin: 0 0 0.55rem;
    padding: 0.45rem 0.75rem;
    border: 1.5px solid var(--sf-black);
    border-radius: 9999px;
    background: var(--sf-lavender);
    color: var(--sf-black);
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: 0.09em;
    text-transform: uppercase;
}

.sf-sidebar-brand {
    margin-bottom: 1.25rem;
    padding: 1rem;
    border: 1.5px solid var(--sf-black);
    border-radius: 24px;
    background: var(--sf-mint);
}

.sf-sidebar-brand strong {
    display: block;
    font-family: "Arial Black", Impact, sans-serif;
    font-size: 1.55rem;
    letter-spacing: -0.04em;
    line-height: 0.95;
    text-transform: uppercase;
}

.sf-sidebar-brand span {
    display: block;
    margin-top: 0.6rem;
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

[data-testid="stSidebar"] {
    border-right: 1.5px solid var(--sf-black);
    background: var(--sf-lavender);
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 2rem;
}

[data-testid="stVerticalBlock"]:has(
    > [data-testid="stElementContainer"] .sf-section-label
),
[data-testid="stVerticalBlock"]:has(
    > [data-testid="stElementContainer"] .sf-card-marker
) {
    border: 1.5px solid var(--sf-black) !important;
    border-radius: 30px !important;
    background: var(--sf-white);
    box-shadow: none !important;
    padding: 1.25rem !important;
}

.sf-card-marker { display: none; }

.stTextInput [data-baseweb="input"],
.stTextArea [data-baseweb="textarea"],
.stSelectbox [data-baseweb="select"] > div,
.stNumberInput [data-baseweb="input"] {
    border: 1.5px solid var(--sf-black) !important;
    border-radius: 18px !important;
    background: var(--sf-white) !important;
    box-shadow: none !important;
}

.stTextArea textarea {
    min-height: 160px;
}

.stButton > button,
.stDownloadButton > button {
    min-height: 2.8rem;
    border: 1.5px solid var(--sf-black) !important;
    border-radius: 9999px !important;
    background: var(--sf-white) !important;
    color: var(--sf-black) !important;
    box-shadow: none !important;
    font-size: 0.75rem !important;
    font-weight: 800 !important;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    transition: transform 120ms ease, background 120ms ease;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    background: var(--sf-yellow) !important;
    transform: translateY(-2px);
}

.stButton > button[kind="primary"] {
    background: var(--sf-black) !important;
    color: var(--sf-white) !important;
}

.stButton > button[kind="primary"]:hover {
    background: var(--sf-violet) !important;
}

.stButton > button:disabled {
    background: var(--sf-mist) !important;
    color: #6b6b6b !important;
    transform: none;
}

.stRadio [role="radiogroup"] {
    gap: 0.45rem;
}

.stRadio [role="radiogroup"] label {
    padding: 0.35rem 0.7rem;
    border: 1px solid var(--sf-black);
    border-radius: 9999px;
    background: var(--sf-white);
}

[data-testid="stExpander"],
[data-testid="stAlert"] {
    border: 1.5px solid var(--sf-black) !important;
    border-radius: 20px !important;
    box-shadow: none !important;
}

[data-testid="stAlert"] {
    background: var(--sf-mint);
    color: var(--sf-black);
}

[data-testid="stProgressBar"] > div > div {
    background: var(--sf-violet) !important;
}

[data-testid="stDataFrame"] {
    overflow: hidden;
    border: 1.5px solid var(--sf-black);
    border-radius: 20px;
}

hr {
    border-color: var(--sf-black) !important;
    opacity: 1 !important;
}

@media (max-width: 760px) {
    .block-container {
        padding: 1.25rem 1rem 3rem;
    }

    .sf-hero {
        min-height: 430px;
        padding: 1.4rem;
        border-radius: 28px;
    }

    .sf-hero::after {
        width: 330px;
        height: 140px;
        top: 35px;
        right: -170px;
        border-width: 30px;
    }

    .sf-hero h1 {
        margin-top: 4rem;
        font-size: clamp(3.4rem, 17vw, 5.5rem);
    }

    .sf-sticker {
        right: 1rem;
        bottom: 1rem;
    }

    .sf-marquee {
        font-size: 0.62rem;
    }
}
</style>
"""

HERO_HTML = """
<div class="sf-marquee">
    Local first &nbsp;•&nbsp; YouTube &nbsp;•&nbsp; SoundCloud &nbsp;•&nbsp;
    Your media, your format &nbsp;•&nbsp; Open source
</div>
<section class="sf-hero">
    <div class="sf-hero__top">
        <span class="sf-logo">SF</span>
        <span>StreamFetch · Local media toolkit</span>
    </div>
    <h1>Fetch<br><span>your sound.</span></h1>
    <p class="sf-hero__copy">
        Download permitted videos, playlists, tracks, sets, and channels in the
        format that fits your library.
    </p>
    <div class="sf-platforms">
        <span class="sf-pill sf-pill--blue">YouTube</span>
        <span class="sf-pill sf-pill--mint">SoundCloud</span>
        <span class="sf-pill sf-pill--lavender">Powered by yt-dlp</span>
    </div>
    <span class="sf-sticker">MP3 / MP4</span>
</section>
"""

LEGAL_HTML = """
<div class="sf-legal">
    <span class="sf-legal__icon">⚖</span>
    <span>
        Download only media you created, that is in the public domain, or that
        you have permission to download. Respect copyright, platform terms, and
        local law.
    </span>
</div>
"""

SIDEBAR_HEADER_HTML = """
<div class="sf-sidebar-brand">
    <strong>Tune the<br>output.</strong>
    <span>Format · quality · extras</span>
</div>
"""

SOURCE_LABEL_HTML = '<div class="sf-section-label">01 · Add sources</div>'
PREVIEW_LABEL_HTML = '<div class="sf-section-label">02 · Preview</div>'
RESULT_LABEL_HTML = '<div class="sf-section-label">03 · Your files</div>'

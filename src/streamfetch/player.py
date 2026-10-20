"""Continuous browser player powered by Streamlit Components v2."""

from __future__ import annotations

from typing import Any

import streamlit as st

from streamfetch.library import MediaItem, QueueEntry

AUDIO_MIME_TYPES = {
    "FLAC": "audio/flac",
    "M4A": "audio/mp4",
    "MP3": "audio/mpeg",
    "OGG": "audio/ogg",
    "OPUS": "audio/ogg",
    "WAV": "audio/wav",
}
VIDEO_MIME_TYPES = {
    "MKV": "video/x-matroska",
    "MP4": "video/mp4",
    "WEBM": "video/webm",
}

PLAYER_HTML = """
<section class="sf-continuous-player" tabindex="0" aria-label="StreamFetch media player">
  <div class="sf-player-topline">
    <span>CONTINUOUS PLAYER</span>
    <span class="sf-player-status" data-status>READY</span>
  </div>
  <div class="sf-player-video" data-video-slot></div>
  <audio data-audio preload="auto"></audio>
  <video data-video preload="metadata" playsinline></video>
  <div class="sf-player-meta">
    <strong data-title>Nothing playing</strong>
    <span data-byline>Choose something from your library</span>
  </div>
  <div class="sf-player-timeline">
    <input data-seek type="range" min="0" max="1000" value="0" aria-label="Playback position">
    <div class="sf-player-times">
      <span data-current-time>0:00</span><span data-duration>0:00</span>
    </div>
  </div>
  <div class="sf-player-controls">
    <button type="button" data-previous aria-label="Previous item">&#8592;</button>
    <button type="button" class="sf-player-play" data-play aria-label="Play">PLAY</button>
    <button type="button" data-next aria-label="Next queued item">&#8594;</button>
    <button type="button" data-favorite aria-label="Toggle favorite">&#9825;</button>
  </div>
  <div class="sf-player-footer">
    <label>
      VOL
      <input data-volume type="range" min="0" max="1" step="0.05" value="1" aria-label="Volume">
    </label>
    <span data-queue>QUEUE EMPTY</span>
    <span>SPACE PLAY · N NEXT</span>
  </div>
</section>
"""

PLAYER_CSS = """
:host {
  display: block;
  color: #111111;
  font-family: "Space Grotesk", "Arial", sans-serif;
}

.sf-continuous-player {
  background: #f3ddff;
  border: 2px solid #111111;
  border-radius: 22px;
  box-shadow: 5px 5px 0 #111111;
  padding: 1rem;
  outline: none;
}

.sf-continuous-player:focus-visible {
  box-shadow: 5px 5px 0 #111111, 0 0 0 4px #ffcf40;
}

.sf-player-topline,
.sf-player-footer,
.sf-player-times {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
  font-size: .68rem;
  font-weight: 800;
  letter-spacing: .08em;
}

.sf-player-status {
  background: #7bdba7;
  border: 1.5px solid #111111;
  border-radius: 999px;
  padding: .2rem .55rem;
}

.sf-player-meta {
  display: grid;
  gap: .2rem;
  margin: .95rem 0 .7rem;
}

.sf-player-meta strong {
  font-size: clamp(1.25rem, 3vw, 2rem);
  line-height: 1;
}

.sf-player-meta span {
  color: #4b3c55;
  font-size: .85rem;
}

.sf-player-video {
  display: none;
  margin-top: .8rem;
}

.sf-player-video.is-visible {
  display: block;
}

.sf-player-video video {
  background: #111111;
  border: 2px solid #111111;
  border-radius: 14px;
  display: block;
  max-height: 360px;
  width: 100%;
}

audio,
video[data-video] {
  display: none;
}

.sf-player-timeline input,
.sf-player-footer input {
  accent-color: #7248ff;
  cursor: pointer;
}

.sf-player-timeline > input {
  width: 100%;
}

.sf-player-times {
  color: #5b4765;
  margin-top: -.1rem;
}

.sf-player-controls {
  display: grid;
  grid-template-columns: .8fr 2fr .8fr .8fr;
  gap: .55rem;
  margin: .65rem 0;
}

.sf-player-controls button {
  background: #ffffff;
  border: 2px solid #111111;
  border-radius: 999px;
  color: #111111;
  cursor: pointer;
  font: inherit;
  font-size: .8rem;
  font-weight: 900;
  min-height: 42px;
}

.sf-player-controls button:hover:not(:disabled) {
  background: #ffcf40;
  transform: translateY(-1px);
}

.sf-player-controls button:disabled {
  cursor: not-allowed;
  opacity: .35;
}

.sf-player-controls .sf-player-play {
  background: #111111;
  color: #ffffff;
}

.sf-player-footer {
  border-top: 1.5px solid #111111;
  margin-top: .8rem;
  padding-top: .65rem;
}

.sf-player-footer label {
  align-items: center;
  display: flex;
  gap: .35rem;
}

.sf-player-footer input {
  max-width: 90px;
}

@media (max-width: 620px) {
  .sf-player-controls {
    grid-template-columns: .7fr 1.5fr .7fr .7fr;
  }

  .sf-player-footer > :last-child {
    display: none;
  }
}
"""

PLAYER_JS = """
const formatTime = (seconds) => {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const whole = Math.floor(seconds);
  const minutes = Math.floor(whole / 60);
  const remainder = String(whole % 60).padStart(2, "0");
  return `${minutes}:${remainder}`;
};

export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector(".sf-continuous-player");
  const audio = root.querySelector("[data-audio]");
  const video = root.querySelector("[data-video]");
  const videoSlot = root.querySelector("[data-video-slot]");
  const title = root.querySelector("[data-title]");
  const byline = root.querySelector("[data-byline]");
  const status = root.querySelector("[data-status]");
  const seek = root.querySelector("[data-seek]");
  const currentTime = root.querySelector("[data-current-time]");
  const duration = root.querySelector("[data-duration]");
  const play = root.querySelector("[data-play]");
  const previous = root.querySelector("[data-previous]");
  const next = root.querySelector("[data-next]");
  const favorite = root.querySelector("[data-favorite]");
  const volume = root.querySelector("[data-volume]");
  const queue = root.querySelector("[data-queue]");

  const state = root.__streamfetchState ?? { track: null, nextTrack: null };
  state.nextTrack = data.next ?? null;
  root.__streamfetchState = state;

  const activeMedia = () => state.track?.media_type === "video" ? video : audio;

  const syncMeta = (track) => {
    title.textContent = track.title;
    byline.textContent = `${track.artist} · ${track.album}`;
    favorite.textContent = data.favorite ? "♥" : "♡";
    favorite.setAttribute("aria-label", data.favorite ? "Remove favorite" : "Add favorite");
    previous.disabled = !data.can_previous;
    next.disabled = !state.nextTrack;
    queue.textContent = data.queue_count
      ? `QUEUE · ${data.queue_count}`
      : "QUEUE EMPTY";
  };

  const syncProgress = () => {
    const media = activeMedia();
    const total = Number.isFinite(media.duration) ? media.duration : 0;
    seek.value = total ? String(Math.round((media.currentTime / total) * 1000)) : "0";
    currentTime.textContent = formatTime(media.currentTime);
    duration.textContent = formatTime(total);
  };

  const syncPlayback = () => {
    const media = activeMedia();
    play.textContent = media.paused ? "PLAY" : "PAUSE";
    play.setAttribute("aria-label", media.paused ? "Play" : "Pause");
    status.textContent = media.paused ? "PAUSED" : "PLAYING";
  };

  const setTrack = (track, shouldPlay = false) => {
    const oldMedia = activeMedia();
    const media = track.media_type === "video" ? video : audio;
    if (oldMedia !== media) oldMedia.pause();
    state.track = track;

    if (track.media_type === "video") {
      if (!videoSlot.contains(video)) videoSlot.appendChild(video);
      video.style.display = "block";
      videoSlot.classList.add("is-visible");
    } else {
      videoSlot.classList.remove("is-visible");
      audio.style.display = "none";
    }

    if (media.dataset.path !== track.path) {
      media.dataset.path = track.path;
      media.src = track.url;
      media.load();
    }
    media.volume = Number(volume.value);
    syncMeta(track);
    syncProgress();
    syncPlayback();

    if (shouldPlay) {
      media.play().catch(() => {
        status.textContent = "PRESS PLAY";
      });
    }
  };

  const emit = (type, details = {}) => {
    setTriggerValue("action", {
      type,
      nonce: `${Date.now()}-${Math.random()}`,
      ...details,
    });
  };

  const advance = () => {
    if (!state.nextTrack) return;
    const queued = state.nextTrack;
    setTrack(queued, true);
    emit("advance", { entry_id: queued.entry_id });
  };

  const onEnded = () => {
    if (state.nextTrack) {
      advance();
    } else {
      status.textContent = "QUEUE ENDED";
      play.textContent = "PLAY";
    }
  };
  const onPlay = () => syncPlayback();
  const onPause = () => syncPlayback();
  const onTime = () => syncProgress();
  const onLoaded = () => syncProgress();

  for (const media of [audio, video]) {
    media.addEventListener("ended", onEnded);
    media.addEventListener("play", onPlay);
    media.addEventListener("pause", onPause);
    media.addEventListener("timeupdate", onTime);
    media.addEventListener("loadedmetadata", onLoaded);
  }

  play.onclick = () => {
    const media = activeMedia();
    if (media.paused) {
      media.play().catch(() => { status.textContent = "PLAY BLOCKED"; });
    } else {
      media.pause();
    }
  };
  previous.onclick = () => emit("previous");
  next.onclick = () => advance();
  favorite.onclick = () => emit("favorite");
  seek.oninput = () => {
    const media = activeMedia();
    if (Number.isFinite(media.duration)) {
      media.currentTime = (Number(seek.value) / 1000) * media.duration;
    }
  };
  volume.oninput = () => {
    audio.volume = Number(volume.value);
    video.volume = Number(volume.value);
  };
  root.onkeydown = (event) => {
    if (event.target instanceof HTMLInputElement) return;
    const media = activeMedia();
    if (event.code === "Space") {
      event.preventDefault();
      play.click();
    } else if (event.key.toLowerCase() === "n" && !next.disabled) {
      advance();
    } else if (event.key.toLowerCase() === "p" && !previous.disabled) {
      emit("previous");
    } else if (event.key === "ArrowLeft") {
      media.currentTime = Math.max(0, media.currentTime - 5);
    } else if (event.key === "ArrowRight") {
      media.currentTime = Math.min(media.duration || Infinity, media.currentTime + 5);
    }
  };

  const sameTrack = state.track?.path === data.current.path;
  if (!sameTrack) {
    setTrack(data.current, data.autoplay);
  } else {
    state.track = data.current;
    syncMeta(data.current);
    syncProgress();
    syncPlayback();
  }

  if (state.nextTrack?.media_type === "audio") {
    const preloader = new Audio();
    preloader.preload = "auto";
    preloader.src = state.nextTrack.url;
    state.preloader = preloader;
  }

  return () => {
    for (const media of [audio, video]) {
      media.removeEventListener("ended", onEnded);
      media.removeEventListener("play", onPlay);
      media.removeEventListener("pause", onPause);
      media.removeEventListener("timeupdate", onTime);
      media.removeEventListener("loadedmetadata", onLoaded);
    }
  };
}
"""

_PLAYER_COMPONENT = st.components.v2.component(
    "streamfetch_continuous_player",
    html=PLAYER_HTML,
    css=PLAYER_CSS,
    js=PLAYER_JS,
)


def media_mime_type(item: MediaItem) -> str:
    """Return the browser MIME type for a local media item."""

    if item.media_type == "audio":
        return AUDIO_MIME_TYPES.get(item.format, "audio/mpeg")
    return VIDEO_MIME_TYPES.get(item.format, "video/mp4")


def media_url(item: MediaItem, coordinate: str, media_manager: Any | None = None) -> str:
    """Register a local file with Streamlit and return its session URL."""

    if media_manager is None:
        from streamlit.runtime import get_instance

        media_manager = get_instance().media_file_mgr
    return media_manager.add(str(item.path), media_mime_type(item), coordinate)


def build_player_data(
    current: MediaItem,
    next_entry: QueueEntry | None,
    *,
    favorite: bool,
    can_previous: bool,
    autoplay: bool,
    queue_count: int,
    media_manager: Any | None = None,
) -> dict[str, Any]:
    """Create the trusted payload passed to the continuous player component."""

    current_data = _track_data(
        current,
        media_url(current, "streamfetch-player-current", media_manager),
    )
    next_data = None
    if next_entry is not None:
        next_data = _track_data(
            next_entry.item,
            media_url(next_entry.item, "streamfetch-player-next", media_manager),
        )
        next_data["entry_id"] = next_entry.id
    return {
        "current": current_data,
        "next": next_data,
        "favorite": favorite,
        "can_previous": can_previous,
        "autoplay": autoplay,
        "queue_count": queue_count,
    }


def render_continuous_player(data: dict[str, Any]) -> Any:
    """Mount the continuous player and return its action result."""

    return _PLAYER_COMPONENT(
        data=data,
        key="streamfetch_continuous_player",
        on_action_change=lambda: None,
        height="content",
    )


def _track_data(item: MediaItem, url: str) -> dict[str, Any]:
    return {
        "path": str(item.path),
        "url": url,
        "title": item.title,
        "artist": item.artist,
        "album": item.album,
        "media_type": item.media_type,
    }

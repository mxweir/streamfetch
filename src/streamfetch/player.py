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
    <button type="button" data-repeat aria-label="Change repeat mode">REPEAT OFF</button>
  </div>
  <div class="sf-player-footer">
    <label>
      VOL
      <input data-volume type="range" min="0" max="1" step="0.05" value="1" aria-label="Volume">
    </label>
    <span data-queue>QUEUE EMPTY</span>
    <button type="button" data-crossfade aria-label="Change crossfade duration">XF 0S</button>
  </div>
  <details class="sf-player-up-next">
    <summary>UP NEXT · DRAG TO REORDER</summary>
    <ol data-queue-list></ol>
  </details>
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
  grid-template-columns: .7fr 1.7fr .7fr .7fr 1fr;
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

.sf-player-footer button,
.sf-player-up-next button {
  background: transparent;
  border: 1.5px solid #111111;
  border-radius: 999px;
  cursor: pointer;
  font: inherit;
  font-weight: 900;
  padding: .25rem .55rem;
}

.sf-player-up-next {
  border-top: 1.5px solid #111111;
  font-size: .72rem;
  font-weight: 800;
  margin-top: .7rem;
  padding-top: .65rem;
}

.sf-player-up-next summary {
  cursor: pointer;
  letter-spacing: .08em;
}

.sf-player-up-next ol {
  display: grid;
  gap: .4rem;
  list-style: none;
  margin: .6rem 0 0;
  padding: 0;
}

.sf-player-up-next li {
  align-items: center;
  background: rgba(255, 255, 255, .55);
  border: 1.5px solid #111111;
  border-radius: 10px;
  cursor: grab;
  display: grid;
  gap: .5rem;
  grid-template-columns: auto 1fr auto;
  padding: .45rem .55rem;
}

.sf-player-up-next li.is-dragging {
  opacity: .45;
}

@media (max-width: 620px) {
  .sf-player-controls {
    grid-template-columns: .6fr 1.3fr .6fr .6fr 1fr;
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
  const repeat = root.querySelector("[data-repeat]");
  const crossfade = root.querySelector("[data-crossfade]");
  const volume = root.querySelector("[data-volume]");
  const queue = root.querySelector("[data-queue]");
  const queueList = root.querySelector("[data-queue-list]");

  const state = root.__streamfetchState ?? {
    track: null,
    nextTrack: null,
    fadeTimer: null,
    restoring: false,
  };
  state.nextTrack = data.next ?? null;
  state.queueItems = data.queue ?? [];
  root.__streamfetchState = state;

  const activeMedia = () => state.track?.media_type === "video" ? video : audio;

  const syncMeta = (track) => {
    title.textContent = track.title;
    byline.textContent = `${track.artist} · ${track.album}`;
    favorite.textContent = data.favorite ? "♥" : "♡";
    favorite.setAttribute("aria-label", data.favorite ? "Remove favorite" : "Add favorite");
    previous.disabled = !data.can_previous;
    next.disabled = !state.nextTrack;
    repeat.textContent = `REPEAT ${data.repeat_mode.toUpperCase()}`;
    crossfade.textContent = `XF ${data.crossfade_seconds}S`;
    queue.textContent = data.queue_count
      ? `QUEUE · ${data.queue_count}`
      : "QUEUE EMPTY";
  };

  const renderQueue = () => {
    queueList.replaceChildren();
    state.queueItems.forEach((item, index) => {
      const row = document.createElement("li");
      row.draggable = true;
      row.dataset.entryId = String(item.entry_id);
      const handle = document.createElement("span");
      handle.textContent = "↕";
      const label = document.createElement("span");
      label.textContent = `${item.title} — ${item.artist}`;
      const playNow = document.createElement("button");
      playNow.type = "button";
      playNow.textContent = "PLAY";
      playNow.onclick = () => emit("jump", { entry_id: item.entry_id });
      row.append(handle, label, playNow);
      row.ondragstart = () => {
        state.draggedId = item.entry_id;
        row.classList.add("is-dragging");
      };
      row.ondragend = () => row.classList.remove("is-dragging");
      row.ondragover = (event) => event.preventDefault();
      row.ondrop = (event) => {
        event.preventDefault();
        const from = state.queueItems.findIndex((entry) => entry.entry_id === state.draggedId);
        const to = state.queueItems.findIndex((entry) => entry.entry_id === item.entry_id);
        if (from < 0 || to < 0 || from === to) return;
        const reordered = [...state.queueItems];
        const [moved] = reordered.splice(from, 1);
        reordered.splice(to, 0, moved);
        state.queueItems = reordered;
        state.nextTrack = reordered[0] ?? null;
        renderQueue();
        emit("reorder", { entry_ids: reordered.map((entry) => entry.entry_id) });
      };
      queueList.appendChild(row);
    });
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
      state.restoring = true;
    }
    const fadeIn = shouldPlay && track.media_type === "audio"
      ? Number(data.crossfade_seconds)
      : 0;
    media.volume = fadeIn > 0 ? 0 : Number(volume.value);
    syncMeta(track);
    syncProgress();
    syncPlayback();

    if (shouldPlay) {
      media.play().catch(() => {
        status.textContent = "PRESS PLAY";
      });
      if (fadeIn > 0) {
        if (state.fadeTimer) clearInterval(state.fadeTimer);
        const started = performance.now();
        state.fadeTimer = setInterval(() => {
          const progress = Math.min(1, (performance.now() - started) / (fadeIn * 1000));
          media.volume = Number(volume.value) * progress;
          if (progress >= 1) {
            clearInterval(state.fadeTimer);
            state.fadeTimer = null;
          }
        }, 50);
      }
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
    if (data.repeat_mode === "one") {
      const media = activeMedia();
      media.currentTime = 0;
      media.volume = Number(volume.value);
      media.play();
      emit("replay");
    } else if (state.nextTrack) {
      advance();
    } else if (data.repeat_mode === "all") {
      const media = activeMedia();
      media.currentTime = 0;
      media.volume = Number(volume.value);
      media.play();
      emit("replay");
    } else {
      status.textContent = "QUEUE ENDED";
      play.textContent = "PLAY";
    }
  };
  const onPlay = () => syncPlayback();
  const onPause = () => syncPlayback();
  const onTime = () => {
    syncProgress();
    const media = activeMedia();
    const fade = Number(data.crossfade_seconds);
    if (
      fade > 0
      && state.nextTrack?.media_type === "audio"
      && state.track?.media_type === "audio"
      && Number.isFinite(media.duration)
    ) {
      const remaining = media.duration - media.currentTime;
      media.volume = remaining < fade
        ? Math.max(0, Number(volume.value) * (remaining / fade))
        : Number(volume.value);
    }
  };
  const onLoaded = () => {
    if (state.restoring && data.resume_position > 0) {
      const media = activeMedia();
      if (!Number.isFinite(media.duration) || data.resume_position < media.duration - 3) {
        media.currentTime = data.resume_position;
      }
      state.restoring = false;
    }
    syncProgress();
  };

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
      emit("position", { position: media.currentTime });
    }
  };
  previous.onclick = () => emit("previous");
  next.onclick = () => advance();
  favorite.onclick = () => emit("favorite");
  repeat.onclick = () => {
    const modes = ["off", "all", "one"];
    const mode = modes[(modes.indexOf(data.repeat_mode) + 1) % modes.length];
    repeat.textContent = `REPEAT ${mode.toUpperCase()}`;
    emit("repeat", { mode });
  };
  crossfade.onclick = () => {
    const values = [0, 2, 4, 6];
    const seconds = values[(values.indexOf(data.crossfade_seconds) + 1) % values.length];
    crossfade.textContent = `XF ${seconds}S`;
    emit("crossfade", { seconds });
  };
  seek.oninput = () => {
    const media = activeMedia();
    if (Number.isFinite(media.duration)) {
      media.currentTime = (Number(seek.value) / 1000) * media.duration;
    }
  };
  seek.onchange = () => emit("position", { position: activeMedia().currentTime });
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

  renderQueue();

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
    queue_entries: tuple[QueueEntry, ...],
    *,
    favorite: bool,
    can_previous: bool,
    autoplay: bool,
    repeat_mode: str,
    crossfade_seconds: int,
    resume_position: float,
    media_manager: Any | None = None,
) -> dict[str, Any]:
    """Create the trusted payload passed to the continuous player component."""

    current_data = _track_data(
        current,
        media_url(current, "streamfetch-player-current", media_manager),
    )
    next_data = None
    if queue_entries:
        next_entry = queue_entries[0]
        next_data = _track_data(
            next_entry.item,
            media_url(next_entry.item, "streamfetch-player-next", media_manager),
        )
        next_data["entry_id"] = next_entry.id
    queue_data = [
        {
            "entry_id": entry.id,
            "title": entry.item.title,
            "artist": entry.item.artist,
        }
        for entry in queue_entries
    ]
    return {
        "current": current_data,
        "next": next_data,
        "queue": queue_data,
        "favorite": favorite,
        "can_previous": can_previous,
        "autoplay": autoplay,
        "queue_count": len(queue_entries),
        "repeat_mode": repeat_mode,
        "crossfade_seconds": crossfade_seconds,
        "resume_position": resume_position,
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

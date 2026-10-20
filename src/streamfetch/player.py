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
  <audio data-audio preload="auto"></audio>
  <video data-video preload="metadata" playsinline></video>
  <div class="sf-player-bar">
    <div class="sf-player-art" data-media-icon>♫</div>
    <div class="sf-player-track">
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
    </div>
    <div class="sf-player-controls">
      <button type="button" data-previous aria-label="Previous item">&#10094;</button>
      <button type="button" class="sf-player-play" data-play aria-label="Play">PLAY</button>
      <button type="button" data-next aria-label="Next queued item">&#10095;</button>
      <button type="button" data-favorite aria-label="Toggle favorite">&#9825;</button>
      <button type="button" data-expand aria-label="Expand player"
              aria-expanded="false">&#8963;</button>
    </div>
  </div>
  <div class="sf-player-expanded">
    <div class="sf-player-video" data-video-slot></div>
    <div class="sf-player-visualizer" data-visualizer-wrap>
      <canvas data-visualizer aria-label="Audio visualization"></canvas>
    </div>
    <div class="sf-player-topline">
      <span class="sf-player-status" data-status>READY</span>
      <span data-queue>QUEUE EMPTY</span>
    </div>
    <div class="sf-player-footer">
      <label>VOL <input data-volume type="range" min="0" max="1" step="0.05"
                        value="1" aria-label="Volume"></label>
      <button type="button" data-visualizer-toggle
              aria-label="Change visualization">VIS OFF</button>
      <button type="button" data-repeat aria-label="Change repeat mode">REPEAT OFF</button>
      <button type="button" data-crossfade aria-label="Change crossfade duration">XF 0S</button>
    </div>
    <div class="sf-player-queue-head">
      <strong>UP NEXT · DRAG TO REORDER</strong>
      <div>
        <button type="button" data-shuffle>SHUFFLE</button>
        <button type="button" data-clear>CLEAR</button>
      </div>
    </div>
    <ol class="sf-player-queue" data-queue-list></ol>
  </div>
</section>
"""

PLAYER_CSS = """
:host {
  display: block;
  color: #17151c;
  font-family: Inter, "Helvetica Neue", Arial, sans-serif;
}

.sf-continuous-player {
  overflow: hidden;
  padding: .58rem;
  border: 1px solid rgba(255,255,255,.16);
  border-radius: 20px;
  background: rgba(23, 21, 28, .96);
  box-shadow: 0 24px 70px rgba(15, 12, 22, .35);
  color: #ffffff;
  backdrop-filter: blur(20px);
  outline: none;
}

.sf-continuous-player:focus-visible {
  box-shadow: 0 24px 70px rgba(15, 12, 22, .35), 0 0 0 3px #ffd95a;
}

.sf-player-bar {
  display: flex;
  align-items: center;
  gap: .7rem;
}

.sf-player-art {
  display: grid;
  flex: 0 0 52px;
  height: 52px;
  place-items: center;
  border-radius: 14px;
  background: linear-gradient(140deg, #75b8ff, #d9b8ff);
  color: #17151c;
  font-size: 1.35rem;
  font-weight: 900;
}

.sf-player-track { flex: 1 1 auto; min-width: 0; }
.sf-player-meta {
  align-items: baseline;
  display: flex;
  gap: .55rem;
  min-width: 0;
}
.sf-player-meta strong {
  overflow: hidden;
  max-width: 55%;
  font-size: .9rem;
  font-weight: 800;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sf-player-meta span {
  overflow: hidden;
  color: #aaa3b2;
  font-size: .72rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sf-player-timeline input,
.sf-player-footer input {
  accent-color: #d9b8ff;
  cursor: pointer;
}
.sf-player-timeline { margin-top: .38rem; }
.sf-player-timeline > input { display: block; width: 100%; height: 4px; }
.sf-player-times {
  display: flex;
  justify-content: space-between;
  margin-top: -.15rem;
  color: #8f8897;
  font-size: .58rem;
  font-weight: 700;
}

.sf-player-controls {
  align-items: center;
  display: flex;
  flex: 0 0 auto;
  gap: .28rem;
}
.sf-player-controls button,
.sf-player-footer button,
.sf-player-queue-head button,
.sf-player-queue button {
  border: 0;
  border-radius: 10px;
  background: rgba(255,255,255,.09);
  color: #ffffff;
  cursor: pointer;
  font: inherit;
  font-size: .67rem;
  font-weight: 850;
  min-height: 34px;
  padding: 0 .58rem;
}
.sf-player-controls button:hover:not(:disabled),
.sf-player-footer button:hover,
.sf-player-queue-head button:hover,
.sf-player-queue button:hover {
  background: rgba(255,255,255,.17);
}
.sf-player-controls button:disabled {
  cursor: not-allowed;
  opacity: .28;
}
.sf-player-controls .sf-player-play {
  min-width: 58px;
  background: #ffffff;
  color: #17151c;
}
.sf-player-controls [data-favorite] { color: #ffd95a; font-size: 1rem; }

.sf-player-expanded {
  display: none;
  gap: .65rem;
  padding: .8rem .35rem .25rem;
  border-top: 1px solid rgba(255,255,255,.1);
  margin-top: .6rem;
}
.sf-continuous-player.is-expanded .sf-player-expanded { display: grid; }
.sf-continuous-player.is-expanded [data-expand] { transform: rotate(180deg); }

.sf-player-topline,
.sf-player-footer,
.sf-player-queue-head {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: .6rem;
  color: #aaa3b2;
  font-size: .62rem;
  font-weight: 800;
  letter-spacing: .07em;
}
.sf-player-footer label {
  align-items: center;
  display: flex;
  gap: .35rem;
}
.sf-player-footer input { max-width: 90px; }
.sf-player-status { color: #8ce0b7; }
.sf-player-queue-head > div { display: flex; gap: .3rem; }
.sf-player-queue {
  display: grid;
  gap: .35rem;
  max-height: 210px;
  overflow-y: auto;
  list-style: none;
  margin: 0;
  padding: 0;
}
.sf-player-queue li {
  align-items: center;
  background: rgba(255,255,255,.055);
  border-radius: 9px;
  cursor: grab;
  display: grid;
  gap: .5rem;
  grid-template-columns: auto 1fr auto auto;
  padding: .45rem .55rem;
  color: #ded9e4;
  font-size: .72rem;
}
.sf-player-queue li.is-dragging { opacity: .45; }
.sf-player-video { display: none; }
.sf-player-video.is-visible { display: block; }
.sf-player-video video {
  display: block;
  max-height: 320px;
  width: 100%;
  border-radius: 13px;
  background: #000;
}
.sf-player-visualizer {
  display: none;
  height: 92px;
  overflow: hidden;
  border: 1px solid rgba(217,184,255,.18);
  border-radius: 13px;
  background: linear-gradient(180deg, rgba(217,184,255,.08), rgba(117,184,255,.025));
}
.sf-player-visualizer.is-visible { display: block; }
.sf-player-visualizer canvas { display: block; height: 100%; width: 100%; }
audio, video[data-video] { display: none; }

@media (max-width: 680px) {
  .sf-continuous-player {
    border-radius: 17px;
  }
  .sf-player-art { flex-basis: 44px; height: 44px; }
  .sf-player-meta span { display: none; }
  .sf-player-controls {
    gap: .15rem;
  }
  .sf-player-controls button { min-height: 32px; padding: 0 .42rem; }
  .sf-player-controls [data-favorite] { display: none; }
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
  const componentRoot = parentElement.getRootNode();
  const componentHost = componentRoot.host ?? parentElement;
  const dockContainer = componentHost.closest("[data-testid='stElementContainer']")
    ?? parentElement.closest("[data-testid='stElementContainer']");
  const dockTarget = dockContainer ?? componentHost ?? parentElement;
  const positionDock = () => {
    const mobile = window.innerWidth <= 680;
    Object.assign(dockTarget.style, {
      bottom: mobile ? "10px" : "22px",
      left: "auto",
      position: "fixed",
      right: mobile ? "10px" : "24px",
      width: mobile ? "calc(100vw - 20px)" : "min(700px, calc(100vw - 48px))",
      zIndex: "2147483000",
    });
  };
  dockTarget.setAttribute("data-streamfetch-player-dock", "");
  positionDock();
  window.addEventListener("resize", positionDock);
  const audio = root.querySelector("[data-audio]");
  const video = root.querySelector("[data-video]");
  const videoSlot = root.querySelector("[data-video-slot]");
  const mediaIcon = root.querySelector("[data-media-icon]");
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
  const expand = root.querySelector("[data-expand]");
  const shuffle = root.querySelector("[data-shuffle]");
  const clear = root.querySelector("[data-clear]");
  const volume = root.querySelector("[data-volume]");
  const queue = root.querySelector("[data-queue]");
  const queueList = root.querySelector("[data-queue-list]");
  const visualizerWrap = root.querySelector("[data-visualizer-wrap]");
  const visualizerCanvas = root.querySelector("[data-visualizer]");
  const visualizerToggle = root.querySelector("[data-visualizer-toggle]");
  const labels = {
    play: "PLAY", pause: "PAUSE", shuffle: "SHUFFLE", clear: "CLEAR",
    repeat: "REPEAT", up_next: "UP NEXT · DRAG TO REORDER",
    queue_empty: "QUEUE EMPTY", playing: "PLAYING", paused: "PAUSED",
    press_play: "PRESS PLAY", visualizer: "VIS",
    ...(data.labels ?? {}),
  };
  shuffle.textContent = labels.shuffle;
  clear.textContent = labels.clear;
  root.querySelector(".sf-player-queue-head strong").textContent = labels.up_next;

  const state = root.__streamfetchState ?? {
    track: null,
    nextTrack: null,
    fadeTimer: null,
    restoring: false,
    expanded: false,
    visualizerMode: data.visualizer_mode ?? "off",
    sources: new WeakMap(),
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
    repeat.textContent = `${labels.repeat} ${data.repeat_mode.toUpperCase()}`;
    crossfade.textContent = `XF ${data.crossfade_seconds}S`;
    mediaIcon.textContent = track.media_type === "video" ? "▶" : "♫";
    queue.textContent = data.queue_count
      ? `QUEUE · ${data.queue_count}`
      : labels.queue_empty;
    visualizerToggle.textContent = `${labels.visualizer} ${state.visualizerMode.toUpperCase()}`;
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
      playNow.textContent = labels.play;
      playNow.onclick = () => emit("jump", { entry_id: item.entry_id });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "×";
      remove.setAttribute("aria-label", `Remove ${item.title} from queue`);
      remove.onclick = () => emit("remove", { entry_id: item.entry_id });
      row.append(handle, label, playNow, remove);
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
    play.textContent = media.paused ? labels.play : labels.pause;
    play.setAttribute("aria-label", media.paused ? "Play" : "Pause");
    status.textContent = media.paused ? labels.paused : labels.playing;
  };

  const startVisualizer = () => {
    if (state.visualizerMode === "off") {
      visualizerWrap.classList.remove("is-visible");
      if (state.visualizerFrame) cancelAnimationFrame(state.visualizerFrame);
      state.visualizerFrame = null;
      return;
    }
    visualizerWrap.classList.add("is-visible");
    const media = activeMedia();
    try {
      state.audioContext ??= new (window.AudioContext || window.webkitAudioContext)();
      state.analyser ??= state.audioContext.createAnalyser();
      state.analyser.fftSize = 256;
      if (!state.analyserConnected) {
        state.analyser.connect(state.audioContext.destination);
        state.analyserConnected = true;
      }
      if (!state.sources.has(media)) {
        const source = state.audioContext.createMediaElementSource(media);
        source.connect(state.analyser);
        state.sources.set(media, source);
      }
      state.audioContext.resume();
    } catch (_error) {
      status.textContent = "VISUALIZER UNAVAILABLE";
      return;
    }
    const context = visualizerCanvas.getContext("2d");
    const draw = () => {
      const ratio = window.devicePixelRatio || 1;
      const width = visualizerCanvas.clientWidth;
      const height = visualizerCanvas.clientHeight;
      if (visualizerCanvas.width !== width * ratio || visualizerCanvas.height !== height * ratio) {
        visualizerCanvas.width = width * ratio;
        visualizerCanvas.height = height * ratio;
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
      }
      context.clearRect(0, 0, width, height);
      const gradient = context.createLinearGradient(0, 0, width, height);
      gradient.addColorStop(0, "#d9b8ff");
      gradient.addColorStop(1, "#75b8ff");
      context.fillStyle = gradient;
      context.strokeStyle = "#d9b8ff";
      context.lineWidth = 2;
      if (state.visualizerMode === "spectrum") {
        const values = new Uint8Array(state.analyser.frequencyBinCount);
        state.analyser.getByteFrequencyData(values);
        const gap = 2;
        const barWidth = Math.max(2, width / values.length - gap);
        values.forEach((value, index) => {
          const barHeight = Math.max(2, (value / 255) * (height - 8));
          context.fillRect(index * (barWidth + gap), height - barHeight, barWidth, barHeight);
        });
      } else {
        const values = new Uint8Array(state.analyser.fftSize);
        state.analyser.getByteTimeDomainData(values);
        context.beginPath();
        values.forEach((value, index) => {
          const x = (index / (values.length - 1)) * width;
          const y = (value / 255) * height;
          if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
        });
        context.stroke();
      }
      state.visualizerFrame = requestAnimationFrame(draw);
    };
    if (state.visualizerFrame) cancelAnimationFrame(state.visualizerFrame);
    draw();
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
    if (state.visualizerMode !== "off") startVisualizer();

    if (shouldPlay) {
      media.play().catch(() => {
        status.textContent = labels.press_play;
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
      play.textContent = labels.play;
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
      if (state.visualizerMode !== "off") startVisualizer();
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
    repeat.textContent = `${labels.repeat} ${mode.toUpperCase()}`;
    emit("repeat", { mode });
  };
  crossfade.onclick = () => {
    const values = [0, 2, 4, 6];
    const seconds = values[(values.indexOf(data.crossfade_seconds) + 1) % values.length];
    crossfade.textContent = `XF ${seconds}S`;
    emit("crossfade", { seconds });
  };
  expand.onclick = () => {
    state.expanded = !state.expanded;
    root.classList.toggle("is-expanded", state.expanded);
    expand.setAttribute("aria-expanded", String(state.expanded));
    if (state.expanded) startVisualizer();
  };
  visualizerToggle.onclick = () => {
    const modes = ["off", "spectrum", "waveform"];
    state.visualizerMode = modes[(modes.indexOf(state.visualizerMode) + 1) % modes.length];
    visualizerToggle.textContent = `${labels.visualizer} ${state.visualizerMode.toUpperCase()}`;
    startVisualizer();
    emit("visualization", { mode: state.visualizerMode });
  };
  shuffle.onclick = () => emit("shuffle");
  clear.onclick = () => emit("clear");
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
  root.classList.toggle("is-expanded", state.expanded);
  expand.setAttribute("aria-expanded", String(state.expanded));
  if (state.expanded && state.visualizerMode !== "off") startVisualizer();

  if (state.nextTrack?.media_type === "audio") {
    const preloader = new Audio();
    preloader.preload = "auto";
    preloader.src = state.nextTrack.url;
    state.preloader = preloader;
  }

  return () => {
    window.removeEventListener("resize", positionDock);
    if (state.visualizerFrame) cancelAnimationFrame(state.visualizerFrame);
    dockTarget.removeAttribute("data-streamfetch-player-dock");
    for (const property of ["bottom", "left", "position", "right", "width", "z-index"]) {
      dockTarget.style.removeProperty(property);
    }
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
    visualizer_mode: str = "off",
    labels: dict[str, str] | None = None,
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
        "visualizer_mode": visualizer_mode,
        "labels": labels or {},
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

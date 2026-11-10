"use strict";
const homeGerman = (navigator.languages?.[0] || navigator.language || "").toLowerCase().startsWith("de");
const homeTranslations = {
  "Home Player · StreamFetch": "Heimnetz-Player · StreamFetch",
  "Pair · StreamFetch": "Koppeln · StreamFetch",
  "Connect · StreamFetch": "Verbinden · StreamFetch",
  "Disconnect": "Trennen",
  "YOUR LIBRARY. CONNECTED.": "DEINE MEDIATHEK IM HEIMNETZ",
  "One library.": "Eine Mediathek.",
  "Your choice.": "Du entscheidest.",
  "Connecting to your library…": "Verbindung zur Mediathek wird hergestellt …",
  "Playback destination": "Wiedergabegerät",
  "This device": "Dieses Gerät",
  "Computer speakers": "Computerlautsprecher",
  "Computer connection": "Verbindung zum Computer",
  "COMPUTER": "COMPUTER",
  "Connecting…": "Verbindung wird hergestellt …",
  "Checking permissions…": "Berechtigungen werden geprüft …",
  "Continue here": "Hier weiterhören",
  "Move playback to computer": "Auf dem Computer weiterhören",
  "Computer playback controls": "Wiedergabesteuerung am Computer",
  "← Previous": "← Zurück",
  "Play": "Abspielen",
  "Pause": "Pause",
  "Next →": "Weiter →",
  "Computer position": "Position am Computer",
  "Computer volume": "Lautstärke am Computer",
  "Original-file downloads require permission from the computer owner.": "Der Computer muss Original-Downloads freigeben.",
  "Search library": "Mediathek durchsuchen",
  "Search tracks, artists, albums…": "Titel, Interpret oder Album suchen …",
  "Playlist": "Playlist",
  "All playlists": "Alle Playlists",
  "Media player": "Mediaplayer",
  "Make yourself at home": "Willkommen",
  "Choose a track to begin": "Wähle einen Titel",
  "Previous track": "Vorheriger Titel",
  "Next track": "Nächster Titel",
  "Speed": "Tempo",
  "Sleep": "Einschlaftimer",
  "Off": "Aus",
  "Match loudness": "Lautstärke angleichen",
  "Original sound · not analysed yet": "Originalton · noch nicht analysiert",
  "Save original": "Original speichern",
  "YOUR LIBRARY. YOUR NETWORK.": "DEINE MEDIATHEK. DEIN HEIMNETZ.",
  "A little closer": "Deine Musik",
  "to your music.": "immer dabei.",
  "Enter the pairing code shown in StreamFetch. Only the library selected on your computer is shared.": "Gib den Kopplungscode aus StreamFetch ein. Freigegeben ist die am Computer ausgewählte Mediathek.",
  "Pairing code": "Kopplungscode",
  "Connect to library →": "Mit Mediathek verbinden →",
  "Encrypted HTTPS · Trusted home networks only. Use a one-use QR code from your computer, Never forward this port to the internet.": "Verschlüsselt per HTTPS. Verwende ein vertrautes Heimnetz und einen Einmal-QR-Code vom Computer. Gib den Port niemals ins Internet frei.",
  "PRIVATE CONNECTION": "PRIVATE VERBINDUNG",
  "Your music.": "Deine Musik.",
  "Your network.": "Dein Heimnetz.",
  "Connecting securely…": "Sichere Verbindung wird hergestellt …",
  "Manual pairing": "Manuell koppeln",
  "Generate a new QR code in StreamFetch on your computer.": "Erstelle in StreamFetch am Computer einen neuen QR-Code.",
  "This QR code expired, was already used, or could not connect. Generate a new code on your computer.": "Dieser QR-Code ist abgelaufen, wurde schon verwendet oder konnte keine Verbindung herstellen. Erstelle am Computer einen neuen Code.",
  "Please pair again.": "Bitte kopple das Gerät erneut.",
  "Request refused. Check permissions on your computer.": "Anfrage abgelehnt. Prüfe die Berechtigungen am Computer.",
  "Tap play on this device to enable audio.": "Tippe auf diesem Gerät auf Abspielen, um den Ton zu aktivieren.",
  "Loudness matching is unavailable in this browser.": "Dieser Browser unterstützt die Lautstärkeangleichung nicht.",
  "Local library": "Lokale Mediathek",
  "Original sound · no analysis": "Originalton · keine Analyse",
  "Matched · −18 LUFS target": "Angeglichen · Ziel −18 LUFS",
  "Original sound": "Originalton",
  "Tap play to continue. Your browser may require a gesture or a supported format.": "Tippe zum Fortsetzen auf Abspielen. Prüfe bei Problemen das Dateiformat.",
  "Computer player": "Player am Computer",
  "Playing on this device": "Wiedergabe auf diesem Gerät",
  "Controlling computer speakers": "Steuerung der Computerlautsprecher",
  "tracks": "Titel",
  "Computer control is off. Enable it in StreamFetch → Home player.": "Die Computersteuerung ist aus. Aktiviere sie in StreamFetch unter Heimnetz-Player.",
  "Open this library on your computer and press play once. Keep its tab open.": "Öffne diese Mediathek am Computer und starte die Wiedergabe einmal. Lass den Tab offen.",
  "Audio blocked: press play once on the computer.": "Audio blockiert. Starte die Wiedergabe einmal am Computer.",
  "Connected · paused": "Verbunden · pausiert",
  "Connected · playing on computer": "Verbunden · Wiedergabe am Computer",
  "Save originals with ↓. Copies stay on your device after disconnecting; open them in your music or files app.": "Speichere Originale mit ↓. Die Kopien bleiben auf diesem Gerät und lassen sich in der Musik- oder Dateien-App öffnen.",
  "Saving files is off. Ask the computer owner to enable original-file downloads.": "Das Speichern ist aus. Gib Original-Downloads am Computer frei.",
  "Computer unreachable. Check Wi-Fi, sharing and whether it is awake. Saved files remain available locally.": "Computer nicht erreichbar. Prüfe WLAN, Freigabe und Ruhezustand. Gespeicherte Dateien bleiben verfügbar.",
  "Wait for the current command to finish.": "Warte, bis der aktuelle Befehl abgeschlossen ist.",
  "Computer updated.": "Der Computer hat den Befehl bestätigt.",
  "Press play once on the computer to allow audio. Playback has not moved.": "Starte die Wiedergabe einmal am Computer, um den Ton freizugeben. Die Wiedergabe wurde noch nicht übertragen.",
  "Computer did not confirm. Keep the library tab open and try again.": "Der Computer hat nicht bestätigt. Lass die Mediathek geöffnet und versuche es erneut.",
  "Sleep timer finished.": "Der Einschlaftimer ist abgelaufen.",
  "Cannot play this file. Check the computer is awake and your browser supports the format.": "Die Datei lässt sich nicht abspielen. Prüfe den Ruhezustand am Computer und das Dateiformat."
};
const homeText = text => homeGerman ? homeTranslations[text] || text : text;
if (homeGerman) {
  document.documentElement.lang = "de";
  const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (["SCRIPT", "STYLE"].includes(node.parentElement.tagName)) continue;
    const clean = node.nodeValue.trim().replace(/\s+/g, " ");
    if (homeTranslations[clean]) node.nodeValue = node.nodeValue.replace(/\S[\s\S]*\S|\S/, homeText(clean));
  }
  for (const element of document.querySelectorAll("[aria-label],[placeholder]")) {
    for (const key of ["aria-label", "placeholder"]) {
      if (element.hasAttribute(key)) element.setAttribute(key, homeText(element.getAttribute(key)));
    }
  }
}

# StreamFetch bis 3.0

Stand 10. November 2026. Grundlage sind der veröffentlichte Stand 2.0.1, der lokale Code und getrennte Reviews für Produkt, Architektur und Qualität. Die Reihenfolge ist ein Vorschlag. Die Abnahme bestimmt den Übergang zur nächsten Etappe.

**Produktziel:** Einen Link sammeln, eine Aufnahme oder einen Ausschnitt zuverlässig speichern, die passende Stelle wiederfinden und auf dem gewünschten Gerät weiterhören. Bei einem Update oder Gerätewechsel sollen Bibliothek und persönlicher Hörstand erhalten bleiben.

## Stand heute

StreamFetch hat bereits Link-Inbox, dauerhafte Downloadaufträge, Sammlungen, Lesezeichen, Clips, lokale Transkripte, Abos und verschlüsseltes Heimnetz-Hören. Der Export enthält Originaldateien, M3U8 und Dateiprüfsummen. Der 2.0-Export ist auf 200 Titel und 200 MiB begrenzt und bildet den Bibliothekszustand nicht vollständig ab. Suche und Übersicht beziehen sich auf die jeweils geöffnete Bibliothek. Die Wiedergabe läuft innerhalb der Bibliotheksansicht. [2.0-Produktstand](releases/v2.0.0.md) · [2.0.1-Prüfbericht](releases/v2.0.1.md).

Lokale Prüfung am 10. November: **294 Tests bestanden, 2 übersprungen, Ruff grün**. Die Veröffentlichung von 2.0.1 belegt den Start und die HTTPS-Updateprüfung mit dem veröffentlichten macOS-Artefakt. Interaktive Windows-Bedienung und reale iOS-/Android-Geräte brauchen eine eigene Abnahme. YouTube und SoundCloud waren in dieser erneuten Prüfung nicht Teil des lokalen Testlaufs. [2.0.1-Release](https://github.com/mxweir/streamfetch/releases/tag/v2.0.1).

Ein Risiko hat Vorrang vor neuen Funktionen. Beim Bibliotheksscan entfernt der Code nicht mehr gesehene Pfade aus dem Index. Playlists, Favoriten, Warteschlange und Hörpositionen sind an diese Pfade gebunden und können dadurch verloren gehen. Ein vorübergehend fehlendes Laufwerk oder eine umbenannte Datei braucht deshalb zuerst einen nicht destruktiven Umgang. [Bibliotheksscan und Datenmodell](../src/streamfetch/library.py).

## 2.1 · Downloads und Updates verlässlich machen

- **Abholstation für Aufträge.** Die Liste zeigt Quelle, Auftrag, Ergebnisdatei, konkrete Fehlerursache und die nächste mögliche Aktion. Ein fertiger Auftrag öffnet den passenden Bibliothekseintrag direkt. Fortschritt und Wiederaufnahme nach Abbruch bleiben nachvollziehbar.
- **Aufträge gegen doppelte Ausführung absichern.** Je Workspace einen Schreibprozess oder ein transaktionales Journal erproben. Zwei Instanzen dürfen für dieselbe Quelle, dasselbe Profil und dasselbe Ziel keinen doppelten Auftrag ausführen. Jede Aufgabe veröffentlicht ihre fertig geprüfte Datei erst am Ende.
- **Fehlende Dateien erhalten.** Beim Scan den Status „Datei fehlt“ setzen und Sammlungen und Hörstände weiter verfügbar halten. In 2.2 folgt die dauerhafte Zuordnung.
- **Antrieb prüfen.** yt-dlp, EJS, JavaScript-Runtime, FFmpeg/ffprobe und freien Speicher gemeinsam prüfen. Für YouTube müssen Engine, EJS und unterstützte Laufzeit zusammenpassen. Pakete mit einem bekannten funktionierenden Satz prüfen, eine funktionierende Version vorhalten und Rückwechsel testen. [yt-dlp EJS-Setup](https://github.com/yt-dlp/yt-dlp-wiki/blob/master/EJS.md).
- **Desktop-Updates absichern.** Heute prüft der App-Download HTTPS, während der Engine-Updater zusätzlich den Wheel-Hash prüft. App-Artefakt mit eindeutigem Betriebssystem und Architektur auswählen, temporär laden und den erwarteten Hash vor Freigabe prüfen. Signatur und Publisher separat prüfen, wo verfügbar. Vor Veröffentlichung den tatsächlich auszuliefernden Build in einer sauberen Umgebung starten. Der Launcher soll auf die Bestätigung seines eigenen Serverprozesses warten. Für ein fehlgeschlagenes Update den Rückweg mit der bisherigen Version und dem bisherigen Datenstand testen. [App-Updater](../src/streamfetch/updates.py) · [Engine-Updater](../src/streamfetch/engine_updates.py).

**Abnahme.** Zwei parallele Instanzen, Neustart bei laufendem Download, voller Datenträger, fehlende Runtime, falsche Prüfsumme und abgebrochenes Update enden in einem verständlichen Zustand. Ein autorisierter YouTube- und SoundCloud-Test überprüft mit eigenen oder ausdrücklich freigegebenen Beispielen die tatsächlich erzeugten Dateien. Plattformfehler, lokale Fehler und vorübergehende Netzfehler bekommen eigene Ergebnisse. Ein grüner Offline-Test ist davon getrennt.

## 2.2 · Eine Suche über alle Bibliotheken

- Gewählte Medienordner gemeinsam durchsuchen. Treffer zeigen Bibliothek und Quelle und öffnen Titel, Lesezeichen oder Transkriptstelle. Filter für Typ, Ordner, Quelle, Tags und Verfügbarkeit. Gespeicherte Suchansichten können auf der Startseite stehen.
- Zuerst Suchdauer und Indexaufbau messen. Dann einen inkrementellen Volltextindex für Metadaten, Lesezeichen und vorhandene Transkripte erproben. Bibliotheksdaten bleiben maßgeblich. Der Suchindex ist neu aufbaubar, und das bisherige Teilwortverhalten wird bewusst geprüft.
- Stabile Medien-IDs einführen. Verschobene Dateien nach Vorschau neu verknüpfen und die Migration bestehender Pfadreferenzen mit einer 2.0.1-Bibliothek prüfen. Dubletten im Import übersichtlich behandeln. Gleiches Original und absichtlich verschiedene Formate müssen auseinandergehalten werden. Offline-Laufwerke werden als nicht verfügbar angezeigt.

**Abnahme.** Mit 10.000 Titeln und 100.000 Transkriptsegmenten liegt der lokale p95 für die erste Trefferseite im warmen Lauf auf dokumentierter Referenzhardware unter 300 ms. Änderungen, fehlende Laufwerke und verschobene Dateien erzeugen keine fälschlich abspielbaren Treffer. Der Index lässt sich neu aufbauen und die vorhandenen Sammlungen bleiben vollständig.

## 2.3 · Player in jeder Ansicht und Momente zum Mitnehmen

- Ein Player und eine Warteschlange für Inbox, Download, Suche, Bibliothek, Abos und Einstellungen. Ansichtswechsel erhalten Wiedergabeposition, Lautstärke und Reihenfolge. Tastaturbedienung, sichtbarer Fokus und Benennung für Screenreader gehören zur Grundfunktion.
- Eine gefundene Transkriptstelle oder ein Lesezeichen direkt zum Player schicken und einen Start-/Endpunkt anlegen. Vorhandene Clip-Funktionen für den Export nutzen. Clip, Quelle und Zeitbereich bleiben miteinander verknüpft. So entsteht aus einem Podcast, Vortrag oder Interview eine Sammlung konkreter Stellen.
- Zuerst einen kleinen technischen Versuch mit dauerhaft eingebundenem Player durchführen. Falls die Streamlit-Routen den Player weiterhin neu starten, eine kleine dauerhafte App-Oberfläche erproben. Die Download- und Bibliothekslogik bleibt dabei im bestehenden Python-Kern.

**Abnahme.** Ein Track läuft über alle sieben Hauptansichten ohne Neuinitialisierung weiter. Aus einem Suchtreffer springt der Player zur richtigen Stelle. Ein Clip aus einer bereits vorhandenen lokalen Datei lässt sich ohne erneuten Download erzeugen. Seek, Play/Pause und Übergabe funktionieren per Tastatur.

## 2.4 · Bibliothek sichern und auf ein neues Gerät übernehmen

- Zwei klare Aktionen: **Medien mitnehmen** für portable Dateien und **Workspace sichern** für Bibliotheken, Sammlungen, Lesezeichen, Transkripte und Hörstände. Metadaten-Sicherung mit optionalen Originalen, Größenanzeige und Wiederherstellungsvorschau.
- Originale großer Sammlungen auf Wunsch in einen Ordner kopieren oder in begrenzten Teilen exportieren. Geprüfte Übernahme über ein Manifest. Pfade lassen sich auf neue Ordner abbilden. Konflikte vor dem Schreiben anzeigen, Rückkehr zur vorherigen Bibliothek ermöglichen.
- Dokumentierten Wechsel von 2.0.1 und den Zwischenversionen testen. Wiederherstellung zunächst in einen neuen Workspace. Die bereits vorhandenen Pre-Update-Sicherungen und SQLite-Snapshots als Ausgangspunkt verwenden.

**Abnahme.** Ein Workspace mit mehreren Bibliotheken, Wiedergabepositionen, Tags, Playlists und Transkripten lässt sich auf einer sauberen Installation öffnen. Originaldateien stimmen per SHA-256 überein. Beschädigte oder abgebrochene Sicherungen erzeugen keinen scheinbar fertigen Workspace. Das Limit des kleinen Exportmodus wird vor dem Kopieren sichtbar.

## 2.5 · Heimnetz auf echten Geräten rund machen

- Die vorhandene QR-Kopplung und Übergabe mit verständlichem Verbindungsstatus, Abspielposition und Rückmeldung bei Gerätewechsel ausbauen. Mobile Oberfläche auf Deutsch und Englisch, inklusive klarer Fehler und Wiedergabekontrolle.
- Eine Sammlung für ein verbundenes Gerät auswählen. Zuerst den bestehenden Download der Originale mit einer verständlichen Auswahl und Platzanzeige erproben. Eine browserbasierte Offline-Bibliothek erst nach einem Test mit realer Speicherbereinigung und vollständigem Neustart freigeben.
- Abos mit Vorschau, neuen Einträgen und sinnvoller Reihenfolge ins tägliche Öffnen integrieren. Bereits vorhandene Dateien wiederverwenden und die Auswahl vor dem Download beibehalten.

**Abnahme.** Reales iPhone mit Safari und Android mit Chrome durchlaufen QR-Kopplung, einen Trackwechsel, Übergabe in beide Richtungen und Mitnahme eines Originals. Schlafmodus, WLAN-Wechsel, Neustart und Widerruf bekommen eigene Ergebnisse. Offline-Wiedergabe wird nur für die auf dem jeweiligen Gerät tatsächlich erprobte Variante ausgewiesen.

## 3.0 · Freigabe des durchgehenden Ablaufs

- Pakettests auf frischen Zielsystemen mit Download, Suche, Player, Wechsel von 2.0.1 und Wiederherstellung. Veröffentlichte Plattformen und Architekturen einzeln nachweisen. Signatur und macOS-Notarisierung nur für überprüfte Artefakte ausweisen.
- Mindestens fünf externe Testende bearbeiten denselben Ablauf: Link sammeln, eine autorisierte Datei speichern, eine bestimmte Stelle wiederfinden, beim Navigieren weiterhören und eine Sammlung auf einem zweiten Gerät öffnen. Ziel sind mindestens vier selbstständige Erfolge je Kernaufgabe. Datenverlust, fälschlich als fertig gemeldete Aufträge und reproduzierbare Blocker im Kernablauf verhindern die stabile Freigabe.
- Suchlauf, große Bibliothek, Sicherung und Wiedergabe auf festgelegter Hardware messen. Tastatur, Zoom und ein realer Screenreader-Durchgang gehören zur Abnahme. Release-Bericht und Screenshots stammen aus dem geprüften Paket.

**Bewusst später:** Cloud-Konten, automatische Hintergrunddownloads und zusätzliche Plattformen haben geringere Priorität als durchgehende Wiedergabe, verlässliche Updates und geprüfte Datenübernahme.

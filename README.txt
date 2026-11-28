TEMPO - practice player and song library
=========================================

Slow songs down or speed them up without changing the pitch, loop passages,
transpose, and organise your songs into
collections (per student, book, exam, concert...). Split a song into
instruments (vocals, drums, bass, piano...) and mute or solo any of them.

Speed changes use the Rubber Band R3 engine, the same library professional
audio software uses. At 100% speed the audio plays untouched.


INSTALL ON WINDOWS
------------------
1. Unzip the folder somewhere permanent, e.g. Documents\Tempo.
2. Double-click "Install Tempo (Windows).bat".
   - If Python is missing, a download page opens. Install Python 3.13 and
     tick "Add python.exe to PATH". Then run the installer again.
   - If Windows shows "Windows protected your PC", click "More info" and then
     "Run anyway".
3. Start Tempo with "Start Tempo (Windows).bat".
   Tip: right-click it > Send to > Desktop (create shortcut).


INSTALL ON MAC
--------------
1. Unzip the folder somewhere permanent, e.g. Documents/Tempo.
2. Right-click "Install Tempo (Mac).command" and choose Open, then Open again.
   (Right-click is needed the first time because the file came from the internet.)
   - If Python is missing, a download page opens. Install Python 3.13, then
     run the installer again.
3. Start Tempo with "Start Tempo (Mac).command" (right-click > Open the first time).

The installer prints "Studio engine (Rubber Band R3): ready" at the end. If it
says "not available", Tempo still works with its built-in engine (the same one
as the web version).


USING TEMPO
-----------
Library
  - "Add songs..." / "Add folder..." or drag files and folders onto the window.
    Songs stay where they are on your computer; Tempo only remembers them.
  - Left side: All songs, Favorites, Recently played, and your collections.
    Make a collection with "+ New collection", then drag songs onto it.
  - Click the star to mark a favourite. Right-click a song for details
    (BPM, key, tags), collections, ordering and removing.
  - Search looks in title, artist, album, tags and key.

Player (double-click a song)
  - Speed 25-200% with the slider or the presets. Enter the song's BPM under
    details to see the resulting tempo.
  - Pitch: transpose in semitones; "Fine tune" (cents) matches a recording to
    a piano that isn't at A440.
  - Tempo finds each song's BPM, beats and key by itself (in the background,
    a few seconds per song). They appear in the BPM and Key columns; you can
    correct them under Edit details. If the tempo is shown at half or double
    speed, type the right BPM there and the click follows.
  - Click: a metronome click on every beat that stays in time at any speed
    (the first beat of each bar is higher).
  - Count-in: one bar of clicks before the music starts, either only when you
    press play or also before every loop repeat.
  - Loop: Set A / Set B, or drag across the waveform.
  - Each song opens at 100% speed, original pitch and no loop.
  - "Save track..." writes MP3/WAV/M4A/FLAC at the current speed and
    pitch, for the whole song or just the loop. Handy for students.

Lyrics (sidebar on the right, toggle with the "Lyrics" button)
  - Opening a song looks up its lyrics automatically by title and artist,
    from LRCLIB (lrclib.net), a free and open lyrics database. Needs internet;
    found lyrics are kept, so a song is only looked up once.
  - Many songs have timed lyrics: the current line is highlighted and the
    sidebar scrolls along, also at slower speeds. Click a line to jump there.
  - Out of step? Timed lyrics are made for one particular recording, so a
    different version (longer intro, radio edit, live) can be off. Use
    "Earlier" / "Later" (a quarter second per click), or click "Sync" and then
    the line that is being sung right now. The timing is saved per song.
  - Wrong song or nothing found? Edit the search box (e.g. add the artist),
    pick another version from the list, or use "Paste lyrics..." to add your own.

Keyboard: Space play/pause, Enter back to the start, Left/Right 5 s, [ and ] speed -/+5%,
A and B set loop points, L loop on/off, Ctrl/Cmd+F search.


SPLITTING INSTRUMENTS (optional add-on)
---------------------------------------
Open a song and click "Download instrument splitter" in the Instruments panel
(one-time download, about 200-300 MB; the Python version installs it into
Tempo's own environment). Then click "Split into instruments". "4 parts" gives vocals, drums, bass, other. "6 parts" adds
piano and guitar (piano separation is the least clean of the six).
It takes a few minutes per song on a normal computer; the very first time it
also downloads the separation model (about 80-160 MB). The result is saved, so
each song is only split once.
Windows with an NVIDIA graphics card: splitting gets much faster with the CUDA
version of PyTorch. Get the pip command from pytorch.org and run it with
.venv\Scripts\python.exe -m pip ...


SYNC BETWEEN COMPUTERS
----------------------
Keep the same library on several computers (Windows and Mac can be mixed):
1. Install Google Drive for desktop (or Dropbox, iCloud Drive, OneDrive).
   Google Drive: in its settings choose "Mirror files", or make the Tempo
   Library folder available offline, so songs open instantly.
2. In Tempo click "Sync" > "Choose sync folder..." and pick a folder in
   your Drive, for example "My Drive". Tempo creates "Tempo Library" there
   and copies your songs into it (your original files are not changed).
3. On the other computer, click "Sync" and choose the same folder. Both
   libraries are combined.
Synced: songs, collections, favourites, song details (BPM, key, tags),
lyrics and their timing, separated instruments, and the BPM/key analysis.
Not synced (per computer): window layout, volume, Click/Count-in settings.
Songs you add while sync is on are copied into the sync folder automatically.
You can also drop audio files straight into "Tempo Library/Songs" with
Explorer or Finder (sub-folders are fine): Tempo adds them within about
10 seconds. Songs you remove from the library stay in that folder and are
not added again unless you add them yourself.
Changes from other computers appear within about 10 seconds. If the same
song is changed on two computers at once, the latest change is kept.

WHERE YOUR DATA IS
------------------
Without sync, the library and separated instruments are in:
  Windows: %APPDATA%\Tempo\Tempo
  Mac:     ~/Library/Application Support/Tempo/Tempo
Back up that folder to keep your library. Your song files are never changed.

UPDATING
  Click "Updates" in Tempo's toolbar (it also checks once a day and shows
  "Update available"). Most updates are quick: only Tempo's own code is
  downloaded (a few hundred KB) and Tempo restarts by itself in seconds.
  When a version changes Tempo's built-in parts, the whole app is downloaded
  instead; Tempo then replaces itself and restarts. Your library is kept.
  New versions are published at https://github.com/ZystemProd/Tempo/releases

PROBLEMS
  Errors are written to tempo-log.txt in the Tempo folder.

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
  - Loop: Set A / Set B, or drag across the waveform.
  - Speed trainer: while a loop plays, Tempo raises the speed step by step,
    e.g. every 2 loops add 5% until 100%.
  - Each song opens at 100% speed, original pitch and no loop.
  - "Save practice track..." writes MP3/WAV/M4A/FLAC at the current speed and
    pitch, for the whole song or just the loop. Handy for students.

Lyrics (sidebar on the right, toggle with the "Lyrics" button)
  - Opening a song looks up its lyrics automatically by title and artist,
    from LRCLIB (lrclib.net), a free and open lyrics database. Needs internet;
    found lyrics are kept, so a song is only looked up once.
  - Many songs have timed lyrics: the current line is highlighted and the
    sidebar scrolls along, also at slower speeds. Click a line to jump there.
  - Wrong song or nothing found? Edit the search box (e.g. add the artist),
    pick another version from the list, or use "Paste lyrics..." to add your own.

Keyboard: Space play/pause, Left/Right 5 s, [ and ] speed -/+5%,
A and B set loop points, L loop on/off, Ctrl/Cmd+F search.


SPLITTING INSTRUMENTS
---------------------
Included in the install. Open a song and click "Split into instruments" in the
Instruments panel. "4 parts" gives vocals, drums, bass, other. "6 parts" adds
piano and guitar (piano separation is the least clean of the six).
It takes a few minutes per song on a normal computer; the very first time it
also downloads the separation model (about 80-160 MB). The result is saved, so
each song is only split once.
Windows with an NVIDIA graphics card: splitting gets much faster with the CUDA
version of PyTorch. Get the pip command from pytorch.org and run it with
.venv\Scripts\python.exe -m pip ...


WHERE YOUR DATA IS
------------------
Library and separated instruments:
  Windows: %APPDATA%\Tempo\Tempo
  Mac:     ~/Library/Application Support/Tempo/Tempo
Back up that folder to keep your library. Your song files are never changed.

UPDATING
  Click "Updates" in Tempo's toolbar. Tempo downloads the newest version,
  updates itself and restarts. Your library is kept. It also checks quietly
  once a day and shows "Update available" when there is something new.
  New versions are published at https://github.com/ZystemProd/Tempo/releases

PROBLEMS
  Errors are written to tempo-log.txt in the Tempo folder.

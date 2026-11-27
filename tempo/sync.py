"""Library sync through a folder kept in step by Google Drive, Dropbox, iCloud Drive or OneDrive.

Layout of the sync folder ("Tempo Library"):

    Songs/                     audio files (copied in when added)
    stems/<uid>/<name>.wav     separated instruments
    data/songs/<uid>.json      one file per song: details, lyrics, analysis, ...
    data/collections/<uid>.json  one file per collection: name and song order

One small file per item means two computers editing different songs never touch the same
file. For the same item, the newest change wins ("modified" timestamp). Deleting leaves a
small marker file ({"deleted": true}) so the deletion reaches the other computers too.
Files are written atomically (temporary name, then rename) so a sync app never sees half a file.
"""
import json
import os
import shutil
import threading
import uuid

SONG_FIELDS = ('title', 'artist', 'album', 'duration', 'favorite', 'bpm', 'key', 'tags', 'notes',
               'lyrics', 'analysis', 'stems', 'added', 'last_played', 'play_count')
LIB_NAME = 'Tempo Library'


def new_uid():
    return uuid.uuid4().hex


def resolve_root(chosen):
    """The folder the user picked may be the library itself or the folder that should contain it."""
    if os.path.isdir(os.path.join(chosen, 'data', 'songs')):
        return chosen
    inner = os.path.join(chosen, LIB_NAME)
    return inner


class SyncFolder:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.songs_dir = os.path.join(self.root, 'Songs')
        self.stems_root = os.path.join(self.root, 'stems')
        self.data_songs = os.path.join(self.root, 'data', 'songs')
        self.data_cols = os.path.join(self.root, 'data', 'collections')
        for d in (self.songs_dir, self.stems_root, self.data_songs, self.data_cols):
            os.makedirs(d, exist_ok=True)
        self._seen = {}
        self._lock = threading.Lock()

    # ---------- paths ----------
    def rel(self, path):
        """Path relative to the sync folder with '/' separators, or None if outside it."""
        try:
            r = os.path.relpath(os.path.abspath(path), self.root)
        except ValueError:  # another drive on Windows
            return None
        if r.startswith('..') or os.path.isabs(r):
            return None
        return r.replace(os.sep, '/')

    def abs(self, rel):
        return os.path.join(self.root, *rel.split('/'))

    def stems_dir(self, uid):
        return os.path.join(self.stems_root, uid)

    def contains(self, path):
        return self.rel(path) is not None

    # ---------- writing ----------
    def _write(self, folder, uid, data):
        tmp = os.path.join(folder, '.%s.%s.tmp' % (uid, os.getpid()))
        dst = os.path.join(folder, uid + '.json')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, dst)
        with self._lock:
            try:
                self._seen[dst] = os.stat(dst).st_mtime_ns
            except OSError:
                pass

    def write_song(self, row):
        rec = {k: row.get(k) for k in SONG_FIELDS}
        rel = self.rel(row['path'])
        rec.update(uid=row['uid'], modified=row.get('modified') or 0, rel_path=rel,
                   abs_path=None if rel else row['path'], deleted=False)
        self._write(self.data_songs, row['uid'], rec)

    def delete_song(self, uid, modified):
        self._write(self.data_songs, uid, {'uid': uid, 'deleted': True, 'modified': modified})

    def write_collection(self, uid, name, song_uids, modified):
        self._write(self.data_cols, uid, {'uid': uid, 'name': name, 'songs': song_uids,
                                          'modified': modified, 'deleted': False})

    def delete_collection(self, uid, modified):
        self._write(self.data_cols, uid, {'uid': uid, 'deleted': True, 'modified': modified})

    # ---------- reading ----------
    def changed(self, everything=False):
        """Records whose files changed since the last call: (songs, collections)."""
        out = ([], [])
        for i, folder in enumerate((self.data_songs, self.data_cols)):
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for e in entries:
                if e.name.startswith('.') or not e.name.endswith('.json'):
                    continue
                try:
                    mt = e.stat().st_mtime_ns
                except OSError:
                    continue
                with self._lock:
                    if not everything and self._seen.get(e.path) == mt:
                        continue
                try:
                    with open(e.path, encoding='utf-8') as f:
                        rec = json.load(f)
                except (OSError, ValueError):
                    continue  # still downloading, or a broken copy: try again next time
                with self._lock:
                    self._seen[e.path] = mt
                if isinstance(rec, dict) and rec.get('uid'):
                    out[i].append(rec)
        return out

    def forget_collection(self, uid):
        with self._lock:
            self._seen.pop(os.path.join(self.data_cols, uid + '.json'), None)

    # ---------- copying files in ----------
    def copy_in(self, path, sub=''):
        """Copy an audio file into Songs/ (keeping a sub-folder if given). Returns the new path.
        Reuses an existing file with the same name and size."""
        name = os.path.basename(path)
        dest_dir = os.path.join(self.songs_dir, *[p for p in sub.replace('\\', '/').split('/') if p])
        os.makedirs(dest_dir, exist_ok=True)
        dst = os.path.join(dest_dir, name)
        base, ext = os.path.splitext(name)
        n = 2
        while os.path.exists(dst):
            try:
                if os.path.getsize(dst) == os.path.getsize(path):
                    return dst
            except OSError:
                pass
            dst = os.path.join(dest_dir, '%s (%d)%s' % (base, n, ext))
            n += 1
        shutil.copy2(path, dst)
        return dst

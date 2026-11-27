"""Song library stored in SQLite: songs, collections, tags and per-song data.

With a SyncFolder attached, every change is also written to the sync folder, and
apply_remote() merges changes made on other computers (see sync.py).
"""
import json
import os
import shutil
import sqlite3
import time

from .audio import is_audio, read_tags
from .sync import SONG_FIELDS, new_uid

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs(
  id INTEGER PRIMARY KEY,
  path TEXT UNIQUE NOT NULL,
  title TEXT, artist TEXT, album TEXT,
  duration REAL,
  added REAL, last_played REAL, play_count INTEGER DEFAULT 0,
  favorite INTEGER DEFAULT 0,
  bpm REAL, key TEXT, tags TEXT DEFAULT '', notes TEXT DEFAULT '',
  speed REAL DEFAULT 1.0, semis REAL DEFAULT 0.0,
  loops TEXT DEFAULT '{}',
  stems TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS collections(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, created REAL
);
CREATE TABLE IF NOT EXISTS collection_songs(
  collection_id INTEGER, song_id INTEGER, pos REAL,
  PRIMARY KEY(collection_id, song_id)
);
"""

EDITABLE = {'title', 'artist', 'album', 'duration', 'favorite', 'bpm', 'key', 'tags', 'notes',
            'speed', 'semis', 'loops', 'stems', 'lyrics', 'analysis', 'last_played', 'play_count', 'path'}


class Library:
    def __init__(self, db_path, sync=None):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = sqlite3.connect(db_path, timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute('PRAGMA table_info(songs)')}
        for col, decl in (('lyrics', "TEXT DEFAULT ''"), ('analysis', "TEXT DEFAULT ''"),
                          ('uid', 'TEXT'), ('modified', 'REAL DEFAULT 0')):
            if col not in cols:
                self.db.execute('ALTER TABLE songs ADD COLUMN %s %s' % (col, decl))
        ccols = {r[1] for r in self.db.execute('PRAGMA table_info(collections)')}
        for col, decl in (('uid', 'TEXT'), ('modified', 'REAL DEFAULT 0')):
            if col not in ccols:
                self.db.execute('ALTER TABLE collections ADD COLUMN %s %s' % (col, decl))
        for table in ('songs', 'collections'):
            for (rid,) in self.db.execute('SELECT id FROM %s WHERE uid IS NULL' % table).fetchall():
                self.db.execute('UPDATE %s SET uid=? WHERE id=?' % table, (new_uid(), rid))
        self.db.commit()
        self.sync = sync

    # ---------- sync helpers ----------
    def _export_song(self, sid):
        if self.sync:
            row = self.get(sid)
            if row:
                try:
                    self.sync.write_song(row)
                except OSError:
                    pass

    def _export_collection(self, cid):
        if not self.sync:
            return
        c = self.db.execute('SELECT * FROM collections WHERE id=?', (cid,)).fetchone()
        if not c:
            return
        uids = [r[0] for r in self.db.execute(
            'SELECT s.uid FROM collection_songs cs JOIN songs s ON s.id=cs.song_id '
            'WHERE cs.collection_id=? ORDER BY cs.pos', (cid,))]
        try:
            self.sync.write_collection(c['uid'], c['name'], uids, c['modified'] or 0)
        except OSError:
            pass

    def _touch_collection(self, cid):
        self.db.execute('UPDATE collections SET modified=? WHERE id=?', (time.time(), cid))
        self.db.commit()
        self._export_collection(cid)

    # ---------- songs ----------
    def add_file(self, path, sub=''):
        path = os.path.abspath(path)
        if not is_audio(path) or not os.path.isfile(path):
            return None
        if self.sync and not self.sync.contains(path):
            row = self.db.execute('SELECT id FROM songs WHERE path=?', (path,)).fetchone()
            if row:
                return row['id']
            path = self.sync.copy_in(path, sub)
        row = self.db.execute('SELECT id FROM songs WHERE path=?', (path,)).fetchone()
        if row:
            return row['id']
        t = read_tags(path)
        now = time.time()
        cur = self.db.execute('INSERT INTO songs(path,title,artist,album,duration,added,uid,modified) '
                              'VALUES(?,?,?,?,?,?,?,?)',
                              (path, t['title'], t['artist'], t['album'], t['duration'], now, new_uid(), now))
        self.db.commit()
        self._export_song(cur.lastrowid)
        return cur.lastrowid

    def add_paths(self, paths, progress=None):
        """Add files and folders (folders are scanned recursively). Returns list of song ids.
        With sync on, files from outside the sync folder are copied into it (keeping folder names)."""
        files = []
        for p in paths:
            if os.path.isdir(p):
                base = os.path.dirname(os.path.abspath(p))
                for root, dirs, names in os.walk(p):
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    sub = os.path.relpath(root, base)
                    files += [(os.path.join(root, n), sub) for n in sorted(names)
                              if is_audio(n) and not n.startswith('._')]
            elif is_audio(p):
                files.append((p, ''))
        ids = []
        for i, (f, sub) in enumerate(files):
            sid = self.add_file(f, sub)
            if sid:
                ids.append(sid)
            if progress:
                progress(i + 1, len(files))
        return ids

    def get(self, sid):
        r = self.db.execute('SELECT * FROM songs WHERE id=?', (sid,)).fetchone()
        return dict(r) if r else None

    def update(self, sid, **fields):
        fields = {k: v for k, v in fields.items() if k in EDITABLE}
        if not fields:
            return
        fields['modified'] = time.time()
        cols = ', '.join('%s=?' % k for k in fields)
        self.db.execute('UPDATE songs SET %s WHERE id=?' % cols, list(fields.values()) + [sid])
        self.db.commit()
        self._export_song(sid)

    def mark_played(self, sid):
        self.db.execute('UPDATE songs SET last_played=?, play_count=play_count+1, modified=? WHERE id=?',
                        (time.time(), time.time(), sid))
        self.db.commit()
        self._export_song(sid)

    def remove(self, sids):
        touched = set()
        for sid in sids:
            row = self.get(sid)
            touched.update(r[0] for r in self.db.execute(
                'SELECT collection_id FROM collection_songs WHERE song_id=?', (sid,)))
            self.db.execute('DELETE FROM songs WHERE id=?', (sid,))
            self.db.execute('DELETE FROM collection_songs WHERE song_id=?', (sid,))
            if row and self.sync:
                try:
                    self.sync.delete_song(row['uid'], time.time())
                except OSError:
                    pass
        self.db.commit()
        for cid in touched:
            self._touch_collection(cid)

    def songs(self, view='all', search=''):
        """view: 'all' | 'favorites' | 'recent' | 'collection:<id>'"""
        q = 'SELECT s.* FROM songs s'
        args = []
        where = []
        order = 's.title COLLATE NOCASE'
        if view == 'favorites':
            where.append('s.favorite=1')
        elif view == 'recent':
            where.append('s.last_played IS NOT NULL')
            order = 's.last_played DESC'
        elif view.startswith('collection:'):
            q += ' JOIN collection_songs c ON c.song_id=s.id'
            where.append('c.collection_id=?')
            args.append(int(view.split(':', 1)[1]))
            order = 'c.pos'
        for word in search.split():
            like = '%' + word + '%'
            where.append('(s.title LIKE ? OR s.artist LIKE ? OR s.album LIKE ? OR s.tags LIKE ? OR s.key LIKE ?)')
            args += [like] * 5
        if where:
            q += ' WHERE ' + ' AND '.join(where)
        q += ' ORDER BY ' + order
        if view == 'recent':
            q += ' LIMIT 50'
        return [dict(r) for r in self.db.execute(q, args)]

    def all_tags(self):
        tags = set()
        for (t,) in self.db.execute("SELECT tags FROM songs WHERE tags<>''"):
            tags.update(x.strip() for x in t.split(',') if x.strip())
        return sorted(tags, key=str.lower)

    # ---------- per-song practice state ----------
    def loops(self, sid):
        s = self.get(sid)
        try:
            d = json.loads(s['loops'] or '{}') if s else {}
        except ValueError:
            d = {}
        if isinstance(d, list):
            d = {'saved': d}
        d.setdefault('saved', [])
        d.setdefault('current', None)
        return d

    def set_loops(self, sid, data):
        self.update(sid, loops=json.dumps(data))

    # ---------- collections ----------
    def collections(self):
        return [dict(r) for r in self.db.execute(
            'SELECT c.id, c.name, COUNT(cs.song_id) AS n FROM collections c '
            'LEFT JOIN collection_songs cs ON cs.collection_id=c.id GROUP BY c.id ORDER BY c.name COLLATE NOCASE')]

    def create_collection(self, name):
        name = name.strip()
        if not name:
            return None
        now = time.time()
        cur = self.db.execute('INSERT OR IGNORE INTO collections(name, created, uid, modified) VALUES(?,?,?,?)',
                              (name, now, new_uid(), now))
        self.db.commit()
        cid = self.db.execute('SELECT id FROM collections WHERE name=?', (name,)).fetchone()['id']
        if cur.rowcount:
            self._export_collection(cid)
        return cid

    def rename_collection(self, cid, name):
        self.db.execute('UPDATE collections SET name=? WHERE id=?', (name.strip(), cid))
        self._touch_collection(cid)

    def delete_collection(self, cid):
        c = self.db.execute('SELECT uid FROM collections WHERE id=?', (cid,)).fetchone()
        self.db.execute('DELETE FROM collections WHERE id=?', (cid,))
        self.db.execute('DELETE FROM collection_songs WHERE collection_id=?', (cid,))
        self.db.commit()
        if c and self.sync:
            try:
                self.sync.delete_collection(c['uid'], time.time())
            except OSError:
                pass

    def add_to_collection(self, cid, sids):
        mx = self.db.execute('SELECT COALESCE(MAX(pos),0) FROM collection_songs WHERE collection_id=?', (cid,)).fetchone()[0]
        for i, sid in enumerate(sids):
            self.db.execute('INSERT OR IGNORE INTO collection_songs VALUES(?,?,?)', (cid, sid, mx + i + 1))
        self._touch_collection(cid)

    def remove_from_collection(self, cid, sids):
        for sid in sids:
            self.db.execute('DELETE FROM collection_songs WHERE collection_id=? AND song_id=?', (cid, sid))
        self._touch_collection(cid)

    def move_in_collection(self, cid, sid, delta):
        rows = [r[0] for r in self.db.execute('SELECT song_id FROM collection_songs WHERE collection_id=? ORDER BY pos', (cid,))]
        if sid not in rows:
            return
        i = rows.index(sid)
        j = max(0, min(len(rows) - 1, i + delta))
        rows.insert(j, rows.pop(i))
        for k, s in enumerate(rows):
            self.db.execute('UPDATE collection_songs SET pos=? WHERE collection_id=? AND song_id=?', (k, cid, s))
        self._touch_collection(cid)

    # ---------- sync: merging changes from other computers ----------
    def apply_remote(self, songs, collections):
        """Merge records read from the sync folder. Newest change wins. Returns the number of changes."""
        sync = self.sync
        n = 0
        for rec in songs:
            uid, mod = rec['uid'], rec.get('modified') or 0
            row = self.db.execute('SELECT * FROM songs WHERE uid=?', (uid,)).fetchone()
            if rec.get('deleted'):
                if row and (row['modified'] or 0) <= mod:
                    self.db.execute('DELETE FROM collection_songs WHERE song_id=?', (row['id'],))
                    self.db.execute('DELETE FROM songs WHERE id=?', (row['id'],))
                    n += 1
                continue
            path = sync.abs(rec['rel_path']) if rec.get('rel_path') else rec.get('abs_path')
            if not path:
                continue
            if row is None:
                same = self.db.execute('SELECT * FROM songs WHERE path=?', (path,)).fetchone()
                if same:  # the same file was added on both computers: keep one identity
                    self.db.execute('UPDATE songs SET uid=? WHERE id=?', (uid, same['id']))
                    row = self.db.execute('SELECT * FROM songs WHERE id=?', (same['id'],)).fetchone()
                else:
                    vals = {k: rec.get(k) for k in SONG_FIELDS}
                    vals.update(path=path, uid=uid, modified=mod)
                    vals['play_count'] = vals['play_count'] or 0
                    vals['favorite'] = vals['favorite'] or 0
                    cols = ', '.join(vals)
                    self.db.execute('INSERT INTO songs(%s) VALUES(%s)' % (cols, ','.join('?' * len(vals))),
                                    list(vals.values()))
                    n += 1
                    continue
            if (row['modified'] or 0) >= mod:
                if (row['modified'] or 0) > mod:
                    self._export_song(row['id'])  # ours is newer: make sure the folder has it
                continue
            vals = {k: rec.get(k) for k in SONG_FIELDS}
            vals['play_count'] = vals['play_count'] or 0
            vals['favorite'] = vals['favorite'] or 0
            other = self.db.execute('SELECT id FROM songs WHERE path=? AND id<>?', (path, row['id'])).fetchone()
            if not other:
                vals['path'] = path
            vals['modified'] = mod
            self.db.execute('UPDATE songs SET %s WHERE id=?' % ', '.join('%s=?' % k for k in vals),
                            list(vals.values()) + [row['id']])
            n += 1
        self.db.commit()
        for rec in collections:
            uid, mod = rec['uid'], rec.get('modified') or 0
            row = self.db.execute('SELECT * FROM collections WHERE uid=?', (uid,)).fetchone()
            if rec.get('deleted'):
                if row and (row['modified'] or 0) <= mod:
                    self.db.execute('DELETE FROM collection_songs WHERE collection_id=?', (row['id'],))
                    self.db.execute('DELETE FROM collections WHERE id=?', (row['id'],))
                    n += 1
                continue
            name = (rec.get('name') or 'Collection').strip()
            if row is None:
                same = self.db.execute('SELECT * FROM collections WHERE name=?', (name,)).fetchone()
                if same:  # same name made on both computers: merge into one
                    self.db.execute('UPDATE collections SET uid=? WHERE id=?', (uid, same['id']))
                    row = self.db.execute('SELECT * FROM collections WHERE id=?', (same['id'],)).fetchone()
                    mine = [r[0] for r in self.db.execute(
                        'SELECT s.uid FROM collection_songs cs JOIN songs s ON s.id=cs.song_id '
                        'WHERE cs.collection_id=? ORDER BY cs.pos', (row['id'],))]
                    rec = dict(rec, songs=list(rec.get('songs') or []) + [u for u in mine if u not in (rec.get('songs') or [])])
                    mod = max(mod, row['modified'] or 0) + 0.001  # the merge is a new change
                else:
                    self.db.execute('INSERT INTO collections(name, created, uid, modified) VALUES(?,?,?,?)',
                                    (self._free_name(name), time.time(), uid, mod))
                    row = self.db.execute('SELECT * FROM collections WHERE uid=?', (uid,)).fetchone()
            elif (row['modified'] or 0) > mod:  # ours is newer (equal: apply again, e.g. a song arrived late)
                self._export_collection(row['id'])
                continue
            cid = row['id']
            if row['name'] != name:
                self.db.execute('UPDATE collections SET name=? WHERE id=?', (self._free_name(name, cid), cid))
            self.db.execute('DELETE FROM collection_songs WHERE collection_id=?', (cid,))
            missing = False
            for pos, su in enumerate(rec.get('songs') or []):
                srow = self.db.execute('SELECT id FROM songs WHERE uid=?', (su,)).fetchone()
                if srow:
                    self.db.execute('INSERT OR IGNORE INTO collection_songs VALUES(?,?,?)', (cid, srow['id'], pos))
                else:
                    missing = True
            self.db.execute('UPDATE collections SET modified=? WHERE id=?', (mod, cid))
            self.db.commit()
            if missing:  # a song has not arrived yet: read this collection again next time
                sync.forget_collection(uid)
            if mod > (rec.get('modified') or 0):
                self._export_collection(cid)
            n += 1
        self.db.commit()
        return n

    def _free_name(self, name, cid=None):
        cand, k = name, 2
        while True:
            r = self.db.execute('SELECT id FROM collections WHERE name=?', (cand,)).fetchone()
            if not r or r['id'] == cid:
                return cand
            cand = '%s (%d)' % (name, k)
            k += 1

    def to_copy(self):
        """Songs whose files are outside the sync folder: (count, total bytes)."""
        n = size = 0
        for r in self.db.execute('SELECT path FROM songs'):
            if not self.sync.contains(r[0]) and os.path.isfile(r[0]):
                n += 1
                size += os.path.getsize(r[0])
        return n, size

    def join(self, old_stems_dir, progress=None):
        """Start syncing: merge what is already in the folder, then copy this computer's songs and
        separated instruments in and write all records. old_stems_dir(row) -> local stems folder."""
        sync = self.sync
        self.apply_remote(*sync.changed(everything=True))
        rows = [dict(r) for r in self.db.execute('SELECT * FROM songs')]
        for i, row in enumerate(rows):
            if progress:
                progress(i, len(rows), row['title'] or os.path.basename(row['path']))
            if not sync.contains(row['path']) and os.path.isfile(row['path']):
                new = sync.copy_in(row['path'])
                taken = self.db.execute('SELECT id FROM songs WHERE path=? AND id<>?', (new, row['id'])).fetchone()
                if taken:  # the same file is already in the library through the folder
                    continue
                self.db.execute('UPDATE songs SET path=? WHERE id=?', (new, row['id']))
                self.db.commit()
            src = old_stems_dir(row)
            dst = sync.stems_dir(row['uid'])
            if src and os.path.isdir(src) and not os.path.isdir(dst) and os.listdir(src):
                shutil.copytree(src, dst)
            self._export_song(row['id'])
        for c in self.db.execute('SELECT id FROM collections').fetchall():
            self._export_collection(c[0])
        if progress:
            progress(len(rows), len(rows), '')

"""Song library stored in SQLite: songs, collections, tags, notes and per-song practice settings."""
import json
import os
import sqlite3
import time

from .audio import is_audio, read_tags

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
    def __init__(self, db_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute('PRAGMA table_info(songs)')}
        if 'lyrics' not in cols:
            self.db.execute("ALTER TABLE songs ADD COLUMN lyrics TEXT DEFAULT ''")
        if 'analysis' not in cols:
            self.db.execute("ALTER TABLE songs ADD COLUMN analysis TEXT DEFAULT ''")
        self.db.commit()

    # ---------- songs ----------
    def add_file(self, path):
        path = os.path.abspath(path)
        if not is_audio(path) or not os.path.isfile(path):
            return None
        row = self.db.execute('SELECT id FROM songs WHERE path=?', (path,)).fetchone()
        if row:
            return row['id']
        t = read_tags(path)
        cur = self.db.execute('INSERT INTO songs(path,title,artist,album,duration,added) VALUES(?,?,?,?,?,?)',
                              (path, t['title'], t['artist'], t['album'], t['duration'], time.time()))
        self.db.commit()
        return cur.lastrowid

    def add_paths(self, paths, progress=None):
        """Add files and folders (folders are scanned recursively). Returns list of song ids."""
        files = []
        for p in paths:
            if os.path.isdir(p):
                for root, dirs, names in os.walk(p):
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    files += [os.path.join(root, n) for n in sorted(names) if is_audio(n) and not n.startswith('._')]
            elif is_audio(p):
                files.append(p)
        ids = []
        for i, f in enumerate(files):
            sid = self.add_file(f)
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
        cols = ', '.join('%s=?' % k for k in fields)
        self.db.execute('UPDATE songs SET %s WHERE id=?' % cols, list(fields.values()) + [sid])
        self.db.commit()

    def mark_played(self, sid):
        self.db.execute('UPDATE songs SET last_played=?, play_count=play_count+1 WHERE id=?', (time.time(), sid))
        self.db.commit()

    def remove(self, sids):
        for sid in sids:
            self.db.execute('DELETE FROM songs WHERE id=?', (sid,))
            self.db.execute('DELETE FROM collection_songs WHERE song_id=?', (sid,))
        self.db.commit()

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
        self.db.execute('INSERT OR IGNORE INTO collections(name, created) VALUES(?,?)', (name, time.time()))
        self.db.commit()
        return self.db.execute('SELECT id FROM collections WHERE name=?', (name,)).fetchone()['id']

    def rename_collection(self, cid, name):
        self.db.execute('UPDATE collections SET name=? WHERE id=?', (name.strip(), cid))
        self.db.commit()

    def delete_collection(self, cid):
        self.db.execute('DELETE FROM collections WHERE id=?', (cid,))
        self.db.execute('DELETE FROM collection_songs WHERE collection_id=?', (cid,))
        self.db.commit()

    def add_to_collection(self, cid, sids):
        mx = self.db.execute('SELECT COALESCE(MAX(pos),0) FROM collection_songs WHERE collection_id=?', (cid,)).fetchone()[0]
        for i, sid in enumerate(sids):
            self.db.execute('INSERT OR IGNORE INTO collection_songs VALUES(?,?,?)', (cid, sid, mx + i + 1))
        self.db.commit()

    def remove_from_collection(self, cid, sids):
        for sid in sids:
            self.db.execute('DELETE FROM collection_songs WHERE collection_id=? AND song_id=?', (cid, sid))
        self.db.commit()

    def move_in_collection(self, cid, sid, delta):
        rows = [r[0] for r in self.db.execute('SELECT song_id FROM collection_songs WHERE collection_id=? ORDER BY pos', (cid,))]
        if sid not in rows:
            return
        i = rows.index(sid)
        j = max(0, min(len(rows) - 1, i + delta))
        rows.insert(j, rows.pop(i))
        for k, s in enumerate(rows):
            self.db.execute('UPDATE collection_songs SET pos=? WHERE collection_id=? AND song_id=?', (k, cid, s))
        self.db.commit()

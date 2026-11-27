"""Lyrics lookup through LRCLIB (https://lrclib.net), a free and open lyrics database."""
import json
import re
import ssl
import urllib.parse
import urllib.request

BASE = 'https://lrclib.net/api/'
UA = 'Tempo/1.0 (personal music practice player)'
_TIME = re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\]')


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _get(endpoint, params):
    url = BASE + endpoint + '?' + urllib.parse.urlencode({k: v for k, v in params.items() if v})
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=12, context=_ctx()) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def search(query, title='', artist='', duration=None):
    """Return a list of matches (dicts with trackName, artistName, albumName, duration,
    instrumental, plainLyrics, syncedLyrics), best first."""
    exact = None
    if title and artist:
        exact = _get('get', {'track_name': title, 'artist_name': artist,
                             'duration': int(round(duration)) if duration else None})
    found = [r for r in (_get('search', {'q': query}) or []) if not exact or r.get('id') != exact.get('id')]
    if duration:  # prefer versions with the same length as the recording
        found.sort(key=lambda r: abs((r.get('duration') or 0) - duration))
    results = ([exact] if exact else []) + found
    return [r for r in results if r.get('plainLyrics') or r.get('syncedLyrics') or r.get('instrumental')]


def parse(record):
    """-> (lines, synced) where lines is a list of (seconds or None, text)."""
    synced = record.get('syncedLyrics') or ''
    if synced.strip():
        out = []
        for raw in synced.splitlines():
            stamps = _TIME.findall(raw)
            text = _TIME.sub('', raw).strip()
            for m, s in stamps:
                out.append((int(m) * 60 + float(s), text))
        out.sort(key=lambda x: x[0])
        if out:
            return out, True
    plain = record.get('plainLyrics') or ''
    if record.get('instrumental') and not plain:
        return [(None, '(Instrumental)')], False
    return [(None, l.rstrip()) for l in plain.splitlines()], False


def parse_text(text):
    """Lyrics the user pasted: LRC with [mm:ss] stamps is treated as synced."""
    return parse({'syncedLyrics': text} if _TIME.search(text) else {'plainLyrics': text})

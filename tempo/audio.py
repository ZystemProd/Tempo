"""Reading and writing audio files (via ffmpeg) and reading song tags."""
import os
import shutil
import subprocess
import sys
import wave

import numpy as np

AUDIO_EXTS = {'.mp3', '.m4a', '.aac', '.wav', '.flac', '.ogg', '.opus', '.wma', '.aif', '.aiff', '.alac', '.mp4', '.webm'}
_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0
_ff = None


def ffmpeg_exe():
    global _ff
    if _ff:
        return _ff
    try:
        import imageio_ffmpeg
        _ff = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        _ff = shutil.which('ffmpeg')
    if not _ff:
        raise RuntimeError('ffmpeg was not found. Run the installer again.')
    return _ff


def is_audio(path):
    return os.path.splitext(path)[1].lower() in AUDIO_EXTS


def decode(path, sr):
    """Decode any audio file to a float32 array of shape (frames, 2) at sample rate sr."""
    cmd = [ffmpeg_exe(), '-v', 'error', '-nostdin', '-i', path, '-vn',
           '-f', 'f32le', '-acodec', 'pcm_f32le', '-ac', '2', '-ar', str(int(sr)), '-']
    p = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)
    if p.returncode != 0 or not p.stdout:
        msg = p.stderr.decode('utf-8', 'replace').strip().splitlines()
        raise RuntimeError(msg[-1] if msg else 'Could not decode the file.')
    a = np.frombuffer(p.stdout, dtype='<f4')
    a = a[: len(a) - (len(a) % 2)]
    return a.reshape(-1, 2)


def write_wav(path, data, sr):
    """Write (frames, 2) float audio as 16-bit PCM WAV."""
    pcm = (np.clip(data, -1.0, 1.0) * 32767.0).astype('<i2')
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm.tobytes())


def export(path, data, sr):
    """Save as WAV, or as MP3/M4A/FLAC through ffmpeg depending on the extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.wav':
        write_wav(path, data, sr)
        return
    codec = {'.mp3': ['-c:a', 'libmp3lame', '-b:a', '256k'],
             '.m4a': ['-c:a', 'aac', '-b:a', '256k'],
             '.flac': ['-c:a', 'flac']}.get(ext, [])
    cmd = [ffmpeg_exe(), '-v', 'error', '-y', '-f', 'f32le', '-ar', str(int(sr)), '-ac', '2', '-i', '-'] + codec + [path]
    p = subprocess.run(cmd, input=np.ascontiguousarray(data, dtype='<f4').tobytes(),
                       capture_output=True, creationflags=_NO_WINDOW)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode('utf-8', 'replace').strip() or 'Export failed.')


def read_tags(path):
    """Return dict with title, artist, album, duration (seconds or None)."""
    info = {'title': os.path.splitext(os.path.basename(path))[0], 'artist': '', 'album': '', 'duration': None}
    try:
        import mutagen
        f = mutagen.File(path, easy=True)
        if f is not None:
            if getattr(f, 'info', None) is not None and getattr(f.info, 'length', None):
                info['duration'] = float(f.info.length)
            tags = f.tags or {}
            for k in ('title', 'artist', 'album'):
                v = tags.get(k) if hasattr(tags, 'get') else None
                if v:
                    info[k] = str(v[0] if isinstance(v, (list, tuple)) else v)
    except Exception:
        pass
    return info


def peaks(data, cols=1600):
    """Waveform overview: one 0..1 value per column."""
    n = len(data)
    if n == 0:
        return np.zeros(cols, dtype=np.float32)
    mono = np.abs(data[:, 0]) + np.abs(data[:, 1])
    edges = np.linspace(0, n, cols + 1).astype(np.int64)
    out = np.maximum.reduceat(mono, edges[:-1]) if n >= cols else np.interp(np.linspace(0, n - 1, cols), np.arange(n), mono)
    m = float(out.max()) or 1.0
    return (out / m).astype(np.float32)

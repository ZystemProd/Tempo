"""Playback: a source reader (loops, instrument stems) feeding a stretch engine into the sound card."""
import threading

import numpy as np

from .stretch import make_engine


class Source:
    """Reads the song (or a mix of its separated instruments) as a continuous stream,
    jumping from B back to A with a short crossfade when a loop is on."""

    def __init__(self, sr):
        self.sr = sr
        self.main = np.zeros((0, 2), dtype=np.float32)
        self.stems = {}
        self.gains = {}
        self.use_stems = False
        self.n = 0
        self.idx = 0
        self.loop = None
        self.xf = int(0.008 * sr)

    def set_audio(self, main):
        self.main = main
        self.stems = {}
        self.gains = {}
        self.use_stems = False
        self.n = len(main)
        self.idx = 0

    def set_stems(self, stems):
        self.stems = stems
        self.gains = {k: self.gains.get(k, 1.0) for k in stems}

    def _get(self, idx):
        valid = (idx >= 0) & (idx < self.n)
        if self.n == 0:
            return np.zeros((len(idx), 2), dtype=np.float32)
        ii = np.clip(idx, 0, self.n - 1)
        if self.use_stems and self.stems:
            y = np.zeros((len(idx), 2), dtype=np.float32)
            for name, a in self.stems.items():
                g = self.gains.get(name, 1.0)
                if g == 0 or len(a) == 0:
                    continue
                y += a[np.minimum(ii, len(a) - 1)] * np.float32(g)
        else:
            y = self.main[ii].astype(np.float32, copy=True)
        y[~valid] = 0.0
        return y

    def read(self, n):
        idx = self.idx + np.arange(n, dtype=np.int64)
        if self.loop:
            A, B = self.loop
            L = B - A
            over = idx >= B
            idx[over] = A + (idx[over] - B) % L
            y = self._get(idx)
            X = min(self.xf, L // 4, A)
            if X > 0:
                m = (idx >= B - X) & (idx < B)
                if m.any():
                    g = ((idx[m] - (B - X)) / X).astype(np.float32)[:, None]
                    y[m] = y[m] * (1.0 - g) + self._get(idx[m] - L) * g
            self.idx = int(idx[-1]) + 1
        else:
            y = self._get(idx)
            self.idx += n
        return y


class Player:
    def __init__(self):
        import sounddevice as sd
        self.sd = sd
        try:
            self.sr = int(sd.query_devices(kind='output')['default_samplerate']) or 44100
        except Exception:
            self.sr = 44100
        self.lock = threading.RLock()
        self.src = Source(self.sr)
        self.engine = make_engine(self.sr)
        self.engine_name = self.engine.name
        self.stream = None
        self.playing = False
        self.ended = False
        self.speed = 1.0
        self.semis = 0.0
        self.volume = 0.9
        self.play_pos = 0.0
        self.bypass = True
        self.error = ''

    # ---- stream ----
    def _ensure_stream(self):
        if self.stream is None:
            self.stream = self.sd.OutputStream(samplerate=self.sr, channels=2, dtype='float32',
                                               blocksize=1024, latency='high', callback=self._cb)
            self.stream.start()

    def _cb(self, outdata, frames, t, status):
        with self.lock:
            if not self.playing or self.src.n == 0:
                outdata.fill(0)
                return
            try:
                y = self.src.read(frames) if self.bypass else self.engine.render(frames, self.src.read)
                outdata[:] = y * np.float32(self.volume)
            except Exception as e:
                outdata.fill(0)
                self.error = str(e)
                self.playing = False
                return
            self.play_pos += frames * self.speed
            lp = self.src.loop
            if lp:
                A, B = lp
                if self.play_pos >= B:
                    self.play_pos = A + (self.play_pos - B) % (B - A)
            elif self.play_pos >= self.src.n:
                self.playing = False
                self.ended = True

    def close(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    # ---- control ----
    def load(self, audio, stems=None):
        with self.lock:
            self.playing = False
            self.ended = False
            self.src.set_audio(audio)
            if stems:
                self.src.set_stems(stems)
            self._seek_samples(0)

    @property
    def duration(self):
        return self.src.n / self.sr

    def position(self):
        """The position you are hearing now: what has been sent to the sound card minus its delay."""
        lat = 0.0
        if self.stream is not None and self.playing:
            try:
                lat = float(self.stream.latency)
            except Exception:
                lat = 0.0
        pos = self.play_pos - lat * self.sr * self.speed
        lp = self.src.loop
        if lp and pos < lp[0] and self.play_pos >= lp[0]:
            pos += lp[1] - lp[0]
        return max(0.0, pos) / self.sr

    def _seek_samples(self, p):
        p = int(max(0, min(self.src.n, p)))
        self.src.idx = p
        self.play_pos = float(p)
        self.engine.reset()

    def seek(self, seconds):
        with self.lock:
            self.ended = False
            self._seek_samples(seconds * self.sr)

    def play(self):
        self._ensure_stream()
        with self.lock:
            if self.ended or self.play_pos >= self.src.n - 1:
                self._seek_samples(self.src.loop[0] if self.src.loop else 0)
            self.ended = False
            self.error = ''
            self.playing = True

    def pause(self):
        with self.lock:
            self.playing = False

    def _update_bypass(self):
        b = abs(self.speed - 1.0) < 1e-9 and abs(self.semis) < 1e-9
        if b != self.bypass:
            self.bypass = b
            self._seek_samples(self.play_pos)

    def set_speed(self, s):
        with self.lock:
            self.speed = float(s)
            self.engine.set_speed(self.speed)
            self._update_bypass()

    def set_pitch(self, semis):
        with self.lock:
            self.semis = float(semis)
            self.engine.set_pitch(self.semis)
            self._update_bypass()

    def set_loop(self, a, b):
        """a, b in seconds, or None to turn the loop off."""
        with self.lock:
            if a is None or b is None or b - a < 0.05:
                self.src.loop = None
                return
            A, B = int(a * self.sr), int(b * self.sr)
            self.src.loop = (A, B)
            if self.play_pos >= B or self.play_pos < A - self.sr * 0.05:
                self._seek_samples(A)

    def set_stems(self, stems):
        with self.lock:
            self.src.set_stems(stems or {})
            if not stems:
                self.src.use_stems = False

    def set_mix(self, use_stems, gains):
        with self.lock:
            self.src.use_stems = bool(use_stems) and bool(self.src.stems)
            self.src.gains.update(gains)


def render_offline(main, stems, gains, use_stems, sr, speed, semis, start_s, end_s,
                   progress=None, cancelled=None):
    """Render a section at the given speed/pitch for saving to a file."""
    src = Source(sr)
    src.set_audio(main)
    if stems:
        src.set_stems(stems)
        src.gains.update(gains)
        src.use_stems = use_stems
    a = int(start_s * sr)
    b = int(min(end_s * sr, src.n))
    src.idx = a

    def read(k):
        base = src.idx
        y = src.read(k)
        over = base + np.arange(k) >= b
        y[over] = 0.0
        return y

    total = max(0, int((b - a) / speed))
    out = np.zeros((total, 2), dtype=np.float32)
    if abs(speed - 1) < 1e-9 and abs(semis) < 1e-9:
        out[:] = read(total)
    else:
        eng = make_engine(sr)
        eng.set_speed(speed)
        eng.set_pitch(semis)
        eng.reset()
        got = 0
        while got < total:
            if cancelled and cancelled():
                return None
            k = min(8192, total - got)
            out[got:got + k] = eng.render(k, read)
            got += k
            if progress:
                progress(got / total)
    f = min(total // 2, int(sr * 0.005))
    if f > 0:
        ramp = np.linspace(0, 1, f, dtype=np.float32)[:, None]
        out[:f] *= ramp
        out[-f:] *= ramp[::-1]
    return out

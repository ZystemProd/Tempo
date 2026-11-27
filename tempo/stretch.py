"""Time-stretch / pitch-shift engines.

Both engines pull audio from a `read(n) -> (n, 2) float32` callable and
produce output with `render(n, read)`, so speed and pitch can change at any time.

* RubberBandEngine - Rubber Band Library, R3 "finer" engine (via pylibrb). Best quality.
* PhaseVocoderEngine - built-in fallback (numpy), the same engine as the web version.
"""
import numpy as np

TWO_PI = 2.0 * np.pi
_engine_status = {'checked': False, 'ok': False, 'error': ''}


class PhaseVocoderEngine:
    name = 'Built-in phase vocoder'

    def __init__(self, sr, N=4096):
        self.sr = sr
        self.N = N
        self.Hs = N // 8
        self.half = N // 2
        n = np.arange(N)
        self.win = (0.5 - 0.5 * np.cos(TWO_PI * n / N)).astype(np.float64)
        self.norm = self.Hs / float(np.sum(self.win ** 2))
        k = np.arange(self.half + 1)
        self.omega = TWO_PI * k * self.Hs / N
        self.speed = 1.0
        self.ratio = 1.0
        self.reset()

    def set_speed(self, s):
        self.speed = float(s)

    def set_pitch(self, semis):
        self.ratio = 2.0 ** (float(semis) / 12.0)

    def reset(self):
        pad = self.half + self.Hs
        self.inbuf = np.zeros((pad, 2), dtype=np.float32)
        self.in_start = -pad
        self.read_pos = 0.0
        self.acc = np.zeros((self.N, 2), dtype=np.float64)
        self.out = np.zeros((0, 2), dtype=np.float32)
        self.out_phase = None
        self.frac = 0.0
        self.skip = self.half
        self.cool_until = -1e18

    def _ensure(self, upto, read):
        need = upto - (self.in_start + len(self.inbuf))
        if need > 0:
            self.inbuf = np.concatenate([self.inbuf, np.asarray(read(need), dtype=np.float32)])

    def _hop(self, read):
        N, Hs, half, w = self.N, self.Hs, self.half, self.win
        p = int(round(self.read_pos))
        s0 = p - half
        s1 = s0 - Hs
        self._ensure(s0 + N, read)
        a = s0 - self.in_start
        b = s1 - self.in_start
        fr = self.inbuf[a:a + N].astype(np.float64)
        pv = self.inbuf[b:b + N].astype(np.float64)
        XL = np.fft.rfft(fr[:, 0] * w)
        XR = np.fft.rfft(fr[:, 1] * w)
        XS = XL + XR
        XP = np.fft.rfft((pv[:, 0] + pv[:, 1]) * w)
        magS, phS = np.abs(XS), np.angle(XS)
        magP, phP = np.abs(XP), np.angle(XP)
        tot = magS.sum()
        up = np.maximum(magS - magP, 0).sum()
        trans = False
        if p >= self.cool_until and tot > 1e-4 and up / tot > 0.22:
            trans = True
            self.cool_until = p + half
        if self.out_phase is None:
            new = phS.copy()
        else:
            d = phS - phP - self.omega
            d -= TWO_PI * np.round(d / TWO_PI)
            adv = self.out_phase + self.omega + d
            m = magS
            c = m[2:-3]
            pk = np.nonzero((c > m[1:-4]) & (c >= m[3:-2]) & (c > m[:-5]) & (c >= m[4:-1]))[0] + 2
            if len(pk):
                mids = (pk[:-1] + pk[1:]) // 2
                owner = np.searchsorted(mids, np.arange(len(m)), side='left')
                kp = pk[owner]
                new = adv[kp] + (phS - phS[kp])
            else:
                new = adv
            if trans:
                mask = magS > 2.0 * magP + 1e-9
                new[mask] = phS[mask]
            new -= TWO_PI * np.round(new / TWO_PI)
        self.out_phase = new
        rot = np.exp(1j * (new - phS))
        rot[0] = 1.0
        rot[-1] = 1.0
        yl = np.fft.irfft(XL * rot, N)
        yr = np.fft.irfft(XR * rot, N)
        g = w * self.norm
        self.acc[:, 0] += yl * g
        self.acc[:, 1] += yr * g
        chunk = self.acc[:Hs].astype(np.float32)
        self.acc[:-Hs] = self.acc[Hs:]
        self.acc[-Hs:] = 0.0
        if self.skip:
            k = min(self.skip, Hs)
            chunk = chunk[k:]
            self.skip -= k
        self.out = np.concatenate([self.out, chunk]) if len(self.out) else chunk
        self.read_pos += Hs * self.speed / self.ratio
        keep = int(self.read_pos) - half - Hs - 2
        cut = keep - self.in_start
        if cut > 4096:
            self.inbuf = self.inbuf[cut:]
            self.in_start += cut

    def render(self, n, read):
        r = self.ratio
        need = int(np.floor(self.frac + n * r)) + 4
        while len(self.out) < need:
            self._hop(read)
        if r == 1.0:
            y = self.out[:n].copy()
            self.out = self.out[n:]
            self.frac = 0.0
            return y
        pos = self.frac + np.arange(n) * r
        ip = np.floor(pos).astype(np.int64)
        t = (pos - ip)[:, None]
        o = self.out
        y0, y1, y2, y3 = o[ip], o[ip + 1], o[ip + 2], o[ip + 3]
        c1 = 0.5 * (y2 - y0)
        c2 = y0 - 2.5 * y1 + 2.0 * y2 - 0.5 * y3
        c3 = 0.5 * (y3 - y0) + 1.5 * (y1 - y2)
        y = (((c3 * t + c2) * t + c1) * t + y1).astype(np.float32)
        end = self.frac + n * r
        adv = int(np.floor(end))
        self.out = self.out[adv:]
        self.frac = end - adv
        return y


class RubberBandEngine:
    """Rubber Band R3 ("finer") engine in real-time mode, through the pylibrb bindings.

    pylibrb's exact property names have varied between versions, so everything is
    looked up defensively; `selftest()` verifies the result before it is used.
    """
    name = 'Rubber Band R3 (studio quality)'

    def __init__(self, sr):
        import pylibrb as rb
        self.rb = rb
        O = rb.Option
        opts = O.PROCESS_REALTIME | O.ENGINE_FINER
        for nm in ('CHANNELS_TOGETHER', 'PITCH_HIGH_CONSISTENCY'):
            v = getattr(O, nm, None)
            if v is not None:
                opts = opts | v
        self.st = rb.RubberBandStretcher(sample_rate=int(sr), channels=2, options=opts, initial_time_ratio=1.0)
        f = getattr(self.st, 'set_max_process_size', None)
        if f:
            f(4096)
        probe = rb.create_audio_array(channels_num=2, samples_num=8)
        self.ch_first = probe.shape[0] == 2 and probe.shape[-1] == 8
        self.dtype = probe.dtype
        self.sr = sr
        self.speed = 1.0
        self.pitch = 1.0
        self.reset()

    def _set(self, name, v):
        try:
            setattr(self.st, name, v)
            return
        except Exception:
            pass
        f = getattr(self.st, 'set_' + name, None)
        if f is None:
            raise AttributeError('pylibrb has no ' + name)
        f(v)

    def _int(self, *names):
        for nm in names:
            a = getattr(self.st, nm, None)
            if a is None:
                continue
            try:
                return int(a() if callable(a) else a)
            except Exception:
                continue
        return None

    def set_speed(self, s):
        self.speed = float(s)
        self._set('time_ratio', 1.0 / self.speed)

    def set_pitch(self, semis):
        self.pitch = 2.0 ** (float(semis) / 12.0)
        self._set('pitch_scale', self.pitch)

    def reset(self):
        self.st.reset()
        self._set('time_ratio', 1.0 / self.speed)
        self._set('pitch_scale', self.pitch)
        self.pad = self._int('preferred_start_pad', 'get_preferred_start_pad') or 0
        self.skip = self._int('start_delay', 'get_start_delay') or 0
        self.out = np.zeros((0, 2), dtype=np.float32)

    def _to(self, block):
        block = np.asarray(block, dtype=self.dtype)
        return np.ascontiguousarray(block.T if self.ch_first else block)

    def _from(self, arr):
        arr = np.asarray(arr, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr[:, None].repeat(2, axis=1)
        return arr.T if self.ch_first else arr

    def render(self, n, read):
        tries = 0
        while len(self.out) < n:
            tries += 1
            if tries > 400:
                raise RuntimeError('Rubber Band produced no output')
            if self.pad > 0:
                block = np.zeros((self.pad, 2), dtype=np.float32)
                self.pad = 0
            else:
                req = self._int('samples_required', 'get_samples_required') or 1024
                block = read(min(max(req, 128), 4096))
            self.st.process(self._to(block))
            av = self.st.available()
            av = int(av() if callable(av) else av)
            if av > 0:
                y = self._from(self.st.retrieve(av))
                if self.skip:
                    k = min(self.skip, len(y))
                    y = y[k:]
                    self.skip -= k
                if len(y):
                    self.out = np.concatenate([self.out, y]) if len(self.out) else y
        y = self.out[:n]
        self.out = self.out[n:]
        return y


def _measure_freq(x, sr):
    s = x[:, 0]
    z = np.nonzero((s[:-1] < 0) & (s[1:] >= 0))[0]
    if len(z) < 3:
        return 0.0
    return (len(z) - 1) / ((z[-1] - z[0]) / sr)


def selftest(engine_cls, sr=44100):
    """Stretch a 440 Hz tone to 75% speed, +3 semitones; check pitch, level and length."""
    n = int(sr * 2.0)
    t = np.arange(n) / sr
    tone = (0.5 * np.sin(TWO_PI * 440.0 * t)).astype(np.float32)
    src = np.stack([tone, tone], axis=1)
    state = {'i': 0}

    def read(k):
        i = state['i']
        y = np.zeros((k, 2), dtype=np.float32)
        part = src[i:i + k]
        y[:len(part)] = part
        state['i'] = i + k
        return y

    eng = engine_cls(sr)
    eng.set_speed(0.75)
    eng.set_pitch(3)
    eng.reset()
    outs = [eng.render(1024, read) for _ in range(int(n / 0.75 / 1024) - 4)]
    y = np.concatenate(outs)
    mid = y[len(y) // 4: 3 * len(y) // 4]
    f = _measure_freq(mid, sr)
    rms = float(np.sqrt(np.mean(mid ** 2)))
    want = 440.0 * 2 ** 0.25
    consumed = state['i'] / sr
    expect_consumed = len(y) * 0.75 / sr
    ok = abs(f - want) / want < 0.02 and 0.15 < rms < 0.6 and abs(consumed - expect_consumed) < 0.5
    return ok, 'freq %.1f (want %.1f), rms %.3f, input %.2fs for %.2fs out' % (f, want, rms, consumed, len(y) / sr)


def rubberband_available():
    if not _engine_status['checked']:
        _engine_status['checked'] = True
        try:
            ok, info = selftest(RubberBandEngine)
            _engine_status['ok'] = ok
            _engine_status['error'] = '' if ok else 'self-test failed: ' + info
        except Exception as e:
            _engine_status['error'] = '%s: %s' % (type(e).__name__, e)
    return _engine_status['ok']


def make_engine(sr):
    if rubberband_available():
        return RubberBandEngine(sr)
    return PhaseVocoderEngine(sr)


def engine_problem():
    return _engine_status['error']

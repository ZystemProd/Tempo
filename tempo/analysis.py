"""Find a song's tempo (BPM), beats, first beat of the bar, and key. numpy only.

* Onsets: spectral flux of a log-magnitude spectrogram.
* Tempo: autocorrelation of the onset curve, with harmonics and a preference for 70-160 BPM.
* Beats: dynamic-programming beat tracker (Ellis 2007, as in librosa).
* Bar start: the beat phase (of 4) with the strongest bass hits and chord changes.
* Key: average chroma correlated with Krumhansl-Kessler major/minor key profiles.
"""
import numpy as np

from .audio import decode

VERSION = 1
SR = 22050
N_FFT = 2048
HOP = 512
FPS = SR / HOP
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_MAJ_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
_MIN_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B']


def _spectrogram(x, n_fft=N_FFT, hop=HOP):
    """Magnitudes, shape (frames, n_fft // 2 + 1), computed in blocks to limit memory."""
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    win = np.hanning(n_fft).astype(np.float32)
    frames = 1 + (len(x) - n_fft) // hop
    out = np.empty((frames, n_fft // 2 + 1), dtype=np.float32)
    view = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop]
    for i in range(0, frames, 1024):
        out[i:i + 1024] = np.abs(np.fft.rfft(view[i:i + 1024] * win, axis=1))
    return out


def _mel_bands(n_bands=40, fmin=30.0, fmax=8000.0):
    """Triangular mel filterbank, shape (bins, bands)."""
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / SR)
    mel = lambda f: 2595.0 * np.log10(1.0 + f / 700.0)
    inv = lambda m: 700.0 * (10 ** (m / 2595.0) - 1.0)
    edges = inv(np.linspace(mel(fmin), mel(fmax), n_bands + 2))
    fb = np.zeros((len(freqs), n_bands), dtype=np.float32)
    for b in range(n_bands):
        lo, c, hi = edges[b], edges[b + 1], edges[b + 2]
        up = (freqs - lo) / (c - lo)
        down = (hi - freqs) / (hi - c)
        fb[:, b] = np.maximum(0, np.minimum(up, down))
    fb /= fb.sum(axis=0, keepdims=True) + 1e-9
    return fb


def _onsets(S):
    """Onset strength: mean positive change of log mel-band energy (kick and snare count alike)."""
    M = S @ _mel_bands()
    logM = np.log1p(1000.0 * M / (M.max() + 1e-9))
    o = _flux(logM) / logM.shape[1]
    g = np.exp(-0.5 * (np.arange(-3, 4) / 1.2) ** 2)
    return _normalize(np.convolve(o, g / g.sum(), mode='same'))


def _flux(logS):
    d = np.diff(logS, axis=0, prepend=logS[:1])
    return np.maximum(d, 0).sum(axis=1)


def _normalize(o):
    k = int(FPS * 0.4) | 1
    local = np.convolve(o, np.ones(k) / k, mode='same')
    o = np.maximum(o - local, 0)
    sd = o.std()
    return o / sd if sd > 0 else o


def _tempo(o):
    n = len(o)
    f = np.fft.rfft(o - o.mean(), 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    ac = ac / (ac[0] or 1)
    bpms = np.arange(50.0, 220.0, 0.25)
    lag = 60.0 * FPS / bpms

    def at(L):
        L = np.clip(L, 0, n - 2)
        i = L.astype(int)
        t = L - i
        return ac[i] * (1 - t) + ac[i + 1] * t

    score = at(lag) + 0.5 * at(2 * lag) + 0.33 * at(3 * lag) + 0.25 * at(lag / 2)
    prior = np.exp(-0.5 * (np.log2(bpms / 115.0) / 0.9) ** 2)
    best = float(bpms[int(np.argmax(score * prior))])
    # Half/double ambiguity (a kick-snare pattern also repeats every two beats): prefer the usual
    # 78-160 BPM range when the beat at that tempo is clearly present.
    if not 78 <= best <= 160:
        for alt in (best * 2, best / 2):
            if 78 <= alt <= 160 and at(np.array([60.0 * FPS / alt]))[0] > 0.3:
                return alt
    return best


def _track(o, bpm, tightness=100.0):
    period = 60.0 * FPS / bpm
    w = np.arange(-int(period), int(period) + 1)
    local = np.convolve(o, np.exp(-0.5 * (w * 32.0 / period) ** 2), mode='same')
    n = len(local)
    window = np.arange(-int(round(2 * period)), -int(round(period / 2)) + 1)
    txwt = -tightness * np.log(-window / period) ** 2
    score = np.zeros(n)
    back = np.full(n, -1, dtype=np.int64)
    thresh = 0.01 * local.max()
    started = False
    for t in range(n):
        z = t + window
        ok = z >= 0
        if ok.any() and started:
            cand = score[z[ok]] + txwt[ok]
            j = int(np.argmax(cand))
            score[t] = local[t] + cand[j]
            back[t] = z[ok][j]
        else:
            score[t] = local[t]
        if local[t] > thresh:
            started = True
    tail = max(1, int(2 * period))
    t = n - tail + int(np.argmax(score[n - tail:]))
    beats = []
    while t >= 0:
        beats.append(t)
        t = back[t]
    beats = np.array(beats[::-1])
    # drop beats in silent stretches at the start and end
    strong = local[beats] > 0.15 * np.median(local[beats]) if len(beats) else beats
    if len(beats) and strong.any():
        first, last = np.argmax(strong), len(strong) - np.argmax(strong[::-1])
        beats = beats[first:last]
    return beats


def _chroma(S):
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / SR)
    sel = (freqs > 60) & (freqs < 2100)
    pc = (np.round(12 * np.log2(freqs[sel] / 440.0)) + 69).astype(int) % 12
    M = np.zeros((sel.sum(), 12), dtype=np.float32)
    M[np.arange(sel.sum()), pc] = 1.0
    C = np.log1p(S[:, sel] * 10.0) @ M
    return C


def _key_chroma(x):
    """Chroma for key finding: fine frequency resolution, overtones removed, bass weighted up."""
    n_fft, hop = 8192, 2048
    S = _spectrogram(x, n_fft, hop)
    lo, hi = 28, 100  # MIDI E1 .. E7
    # spectral peaks only, at their interpolated frequency (no leakage into neighbouring semitones)
    a, b, c = S[:, :-2], S[:, 1:-1], S[:, 2:]
    pk = (b > a) & (b >= c) & (b > 1e-4 * S.max())
    fr, kb = np.nonzero(pk)
    k = kb + 1
    A_, B_, C_ = S[fr, k - 1], S[fr, k], S[fr, k + 1]
    den = A_ - 2 * B_ + C_
    off = np.where(np.abs(den) > 1e-12, 0.5 * (A_ - C_) / np.where(den == 0, 1, den), 0.0)
    f = (k + np.clip(off, -0.5, 0.5)) * SR / n_fft
    good = (f > 39) & (f < 2700)
    fr, f, mag = fr[good], f[good], B_[good]
    midi = np.round(12 * np.log2(f / 440.0) + 69).astype(int)
    ok = (midi >= lo) & (midi <= hi)
    X = np.zeros((len(S), hi - lo + 1), dtype=np.float64)
    np.add.at(X, (fr[ok], midi[ok] - lo), mag[ok] ** 2)
    X = np.sqrt(X)
    Y = X.copy()
    for interval, w in ((12, 0.5), (19, 0.35), (24, 0.25), (28, 0.3), (31, 0.17), (34, 0.14)):
        Y[:, interval:] -= w * X[:, :-interval]
    Y = np.maximum(Y, 0)
    Y[Y < 0.15 * Y.max(axis=1, keepdims=True)] = 0  # keep notes within ~16 dB of the loudest one
    Y = np.sqrt(Y)
    notes = np.arange(lo, hi + 1)
    chroma = np.zeros((len(Y), 12), dtype=np.float32)
    for pc in range(12):
        chroma[:, pc] = Y[:, notes % 12 == pc].sum(axis=1) + 1.5 * Y[:, (notes % 12 == pc) & (notes < 52)].sum(axis=1)
    return chroma


def _key(C):
    energy = C.sum(axis=1)
    keep = energy > 0.1 * np.median(energy[energy > 0]) if (energy > 0).any() else energy >= 0
    prof = C[keep].sum(axis=0)
    prof = prof - prof.mean()
    best, name, conf = -2.0, '', 0.0
    scores = []
    for tonic in range(12):
        for mode, P, names in (('major', _MAJOR, _MAJ_NAMES), ('minor', _MINOR, _MIN_NAMES)):
            p = np.roll(P, tonic) - P.mean()
            r = float(np.dot(prof, p) / (np.linalg.norm(prof) * np.linalg.norm(p) + 1e-9))
            scores.append(r)
            if r > best:
                best, name = r, '%s %s' % (names[tonic], mode)
    scores.sort()
    conf = scores[-1] - scores[-2]
    return name, best, conf


def _downbeat(beats, S, C):
    if len(beats) < 8:
        return 0
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / SR)
    low = np.log1p(S[:, freqs < 180] * 10.0)
    bass = _normalize(_flux(low))
    Cn = C / (np.linalg.norm(C, axis=1, keepdims=True) + 1e-9)
    change = np.r_[0, 1 - (Cn[1:] * Cn[:-1]).sum(axis=1)]
    k = 4
    change = np.convolve(change, np.ones(k) / k, mode='same')
    sc = []
    for ph in range(4):
        b = beats[ph::4]
        sc.append(bass[b].mean() + 2.0 * change[np.minimum(b + 2, len(change) - 1)].mean())
    return int(np.argmax(sc))


def analyze_audio(mono, sr=SR):
    """mono: float32 array at SR. Returns dict(version, bpm, key, key_conf, beats, downbeat)."""
    if sr != SR:
        raise ValueError('expected %d Hz' % SR)
    S = _spectrogram(np.asarray(mono, dtype=np.float32))
    o = _onsets(S)
    bpm = _tempo(o)
    beats = _track(o, bpm)
    if len(beats) > 8:  # refine the tempo: straight-line fit through the beat times
        slope = np.polyfit(np.arange(len(beats)), beats / FPS, 1)[0]
        if slope > 0:
            bpm = float(60.0 / slope)
    C = _chroma(S)
    key, key_r, key_conf = _key(_key_chroma(np.asarray(mono, dtype=np.float32)))
    down = _downbeat(beats, S, C)
    times = (beats * HOP + N_FFT / 2) / SR
    return {'version': VERSION, 'bpm': round(bpm, 1), 'key': key, 'key_conf': round(key_conf, 3),
            'beats': [round(float(t), 3) for t in times], 'downbeat': down}


def analyze(path):
    st = decode(path, SR)
    return analyze_audio(st.mean(axis=1))


def beats_for(analysis, user_bpm=None):
    """Beat times (seconds) and bar-start index, adjusted if the user set half or double the detected tempo."""
    beats = np.asarray(analysis.get('beats') or [], dtype=np.float64)
    down = int(analysis.get('downbeat') or 0)
    det = analysis.get('bpm') or 0
    if user_bpm and det and len(beats) > 2:
        r = user_bpm / det
        if 0.45 < r < 0.55:
            beats, down = beats[down % 2::2], down // 2
        elif 1.8 < r < 2.2:
            mids = (beats[:-1] + beats[1:]) / 2
            both = np.empty(len(beats) + len(mids))
            both[0::2], both[1::2] = beats, mids
            beats, down = both, down * 2
    return beats, down

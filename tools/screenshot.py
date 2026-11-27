"""Render Tempo's window offscreen with a test song and save screenshots (used in CI)."""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)

import types  # noqa: E402

_sd = types.ModuleType('sounddevice')  # CI machines have no sound card
_sd.query_devices = lambda kind=None: {'default_samplerate': 44100.0}


class _Stream:
    latency = 0.0

    def __init__(self, **k):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass


_sd.OutputStream = _Stream
sys.modules['sounddevice'] = _sd

from tempo import app as tapp, audio  # noqa: E402

out_dir = sys.argv[1] if len(sys.argv) > 1 else 'screens'
os.makedirs(out_dir, exist_ok=True)
QApplication.setApplicationName('Tempo')
qa = QApplication([])
qa.setStyle('Fusion')
qa.setStyleSheet(tapp.QSS)

sr = 44100
t = np.arange(sr * 200) / sr
x = (0.3 * np.sin(2 * np.pi * 220 * t) * (0.6 + 0.4 * np.sin(t))).astype(np.float32)
song = os.path.join(tempfile.mkdtemp(), 'Black or White (Single Version).wav')
audio.write_wav(song, np.stack([x, x], 1), sr)

w = tapp.MainWindow()
for f in ('ACDC - TNT.wav', 'Castle On The Hill.wav'):
    audio.write_wav(os.path.join(os.path.dirname(song), f), np.stack([x[:sr], x[:sr]], 1), sr)
ids = w.lib.add_paths([os.path.dirname(song)])
for name in ('Drums', 'Guitar', 'Piano', 'Vocal'):
    w.lib.create_collection(name)
w.refresh_sidebar()
w.refresh()
s = w.lib.get(w.lib.songs('all', 'Black')[0]['id'])
w._pending = (s, False)
w.load_token = 1
a = audio.decode(s['path'], w.player.sr)
w._on_loaded(1, a, {}, audio.peaks(a))
w.set_loop(40.0, 62.0, True)
w.player.seek(55.0)
for size in ((1440, 830), (1280, 760)):
    if size[0] < 1400:
        w.findChild(tapp.QSplitter).setSizes([190, 1000, 260])
        w.vsplit.setSizes([175, 480])
    w.resize(*size)
    w.show()
    for _ in range(5):
        qa.processEvents()
    w._tick()
    qa.processEvents()
    w.grab().save(os.path.join(out_dir, 'tempo-%dx%d.png' % size))
    print('saved', size)
w.player.close()

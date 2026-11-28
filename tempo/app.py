"""Tempo desktop: song library + high-quality practice player."""
import bisect
import heapq
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time

import numpy as np
from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QObject, QProcess, QSettings,
                            QSortFilterProxyModel, QStandardPaths, Qt, QTimer, Signal, QMimeData, QByteArray)
from PySide6.QtCore import QPoint, QPointF, QRectF, QSize
from PySide6.QtGui import (QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPainterPath, QPalette,
                           QPen, QPixmap, QPolygonF, QShortcut, QBrush, QDrag, QFontMetrics)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QBoxLayout, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QStyledItemDelegate, QMenu, QMessageBox, QPlainTextEdit, QProgressDialog,
                               QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QSplitter, QStyleFactory,
                               QTableView, QTabWidget, QToolBar, QVBoxLayout, QWidget)

from . import __version__, addons, analysis, audio, lyrics, updater
from .sync import SyncFolder, resolve_root
from .library import Library
from .player import Player, render_offline
from .stretch import engine_problem

APP = 'Tempo'
MIME = 'application/x-tempo-song-ids'
INK, BG, PANEL, LINE, SOFT, ACC = '#f1ece2', '#151311', '#1f1c1a', '#34302d', '#a59d91', '#c8174a'
LOOP = '#4cc9f0'  # loop markers and region; the playhead stays red
STEM_LABELS = {'vocals': 'Vocals', 'drums': 'Drums', 'bass': 'Bass', 'other': 'Other', 'piano': 'Piano', 'guitar': 'Guitar'}
INTERVALS = ['original key', 'half step', 'whole step', 'minor 3rd', 'major 3rd', 'perfect 4th', 'tritone',
             'perfect 5th', 'minor 6th', 'major 6th', 'minor 7th', 'major 7th', 'octave']

QSS = f"""
* {{ color: {INK}; font-size: 14px; }}
QMainWindow, QWidget#root, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {BG}; }}
QToolBar {{ background: {BG}; border: 0; border-bottom: 4px solid {ACC}; padding: 8px 16px; spacing: 8px; }}
QGroupBox {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 10px; margin-top: 18px; padding: 6px 10px 8px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; top: 2px; color: {SOFT}; font-weight: 600; }}
QPushButton {{ background: #2a2624; border: 1px solid {LINE}; border-radius: 8px; padding: 5px 10px; min-height: 20px; }}
QPushButton:hover {{ background: #36312e; }}
QPushButton:checked, QPushButton#accent {{ background: {ACC}; border-color: {ACC}; color: white; }}
QPushButton:disabled {{ color: #6f685f; }}
QPushButton#loopOn:checked {{ background: {LOOP}; border-color: {LOOP}; color: #0d1b22; }}
QPushButton#play {{ background: {ACC}; border: 0; border-radius: 26px; min-width: 52px; max-width: 52px; min-height: 52px; max-height: 52px; padding: 0; }}
QPushButton#play:hover {{ background: #de2a5d; }}
QPushButton#play:pressed {{ background: #a01240; }}
QPushButton#round {{ background: transparent; border: 1px solid {LINE}; border-radius: 20px; min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px; padding: 0; }}
QPushButton#round:hover {{ background: #2a2624; border-color: #5a534c; }}
QPushButton#round:pressed {{ background: #36312e; }}
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: #121110; border: 1px solid {LINE}; border-radius: 8px; padding: 6px 8px; selection-background-color: {ACC}; }}
QComboBox QAbstractItemView {{ background: {PANEL}; selection-background-color: {ACC}; }}
QTableView, QListWidget {{ background: #121110; border: 1px solid {LINE}; border-radius: 8px; gridline-color: {LINE}; selection-background-color: #5a1428; alternate-background-color: #181615; }}
QListWidget::item {{ padding: 7px 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {ACC}; color: white; }}
QHeaderView::section {{ background: {PANEL}; color: {SOFT}; border: 0; border-bottom: 1px solid {LINE}; padding: 6px; font-weight: 600; }}
QSlider::groove:horizontal {{ height: 6px; background: {LINE}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACC}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {INK}; width: 18px; height: 18px; margin: -7px 0; border-radius: 9px; }}
QTabWidget::pane {{ border: 1px solid {LINE}; border-radius: 10px; background: {PANEL}; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {SOFT}; padding: 8px 14px; font-weight: 600; }}
QTabBar::tab:selected {{ color: {INK}; border-bottom: 3px solid {ACC}; }}
QStatusBar {{ color: {SOFT}; }}
QLabel#big {{ font-size: 34px; font-weight: 700; }}
QLabel#title {{ font-size: 19px; font-weight: 700; }}
QLabel#soft {{ color: {SOFT}; }}
QLabel#time {{ font-size: 18px; font-weight: 600; }}
QListWidget#lyrics {{ background: {BG}; border: 0; font-size: 16px; }}
QListWidget#lyrics::item {{ padding: 4px 2px; border-radius: 0; }}
QListWidget#lyrics::item:selected {{ background: transparent; }}
QFrame#lyricsPanel {{ border-left: 1px solid {LINE}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: #4a4440; border-radius: 4px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: #6a625b; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QMenu {{ background: {PANEL}; border: 1px solid {LINE}; }}
QMenu::item:selected {{ background: {ACC}; }}
QProgressBar {{ border: 1px solid {LINE}; border-radius: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {ACC}; }}
"""


def fmt(t, tenths=False):
    t = max(0.0, float(t or 0))
    m, s = divmod(t, 60)
    return '%d:%04.1f' % (m, s) if tenths else '%d:%02d' % (m, int(s))


def make_icon(kind, color, size=48):
    """Crisp vector transport icons, drawn the same on Windows and Mac."""
    pm = QPixmap(size * 3, size * 3)
    pm.setDevicePixelRatio(3)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    s = float(size)
    if kind == 'play':
        path = QPainterPath()
        path.moveTo(s * 0.36, s * 0.24)
        path.lineTo(s * 0.78, s * 0.50)
        path.lineTo(s * 0.36, s * 0.76)
        path.closeSubpath()
        pen = QPen(c, s * 0.09)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(c)
        p.drawPath(path)
    elif kind == 'pause':
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        w = s * 0.15
        for x in (0.29, 0.56):
            p.drawRoundedRect(QRectF(s * x, s * 0.24, w, s * 0.52), w * 0.3, w * 0.3)
    else:  # 'back' / 'fwd': circular arrow with a 5 inside
        back = kind == 'back'
        pen = QPen(c, s * 0.075)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        r = QRectF(s * 0.17, s * 0.19, s * 0.66, s * 0.66)
        p.drawArc(r, 90 * 16, (-290 if back else 290) * 16)
        cx, top = r.center().x(), r.top()
        d = -1 if back else 1
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(cx + d * s * 0.13, top), QPointF(cx - d * s * 0.03, top - s * 0.11),
                                 QPointF(cx - d * s * 0.03, top + s * 0.11)]))
        f = QFont()
        f.setPixelSize(int(s * 0.30))
        f.setBold(True)
        p.setFont(f)
        p.setPen(c)
        p.drawText(r, Qt.AlignCenter, '5')
    p.end()
    return QIcon(pm)


def _size(n):
    for unit in ('bytes', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return ('%d %s' % (n, unit)) if unit == 'bytes' else ('%.1f %s' % (n, unit))
        n /= 1024.0


def data_dir():
    d = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    os.makedirs(d, exist_ok=True)
    return d


def reveal(path):
    try:
        if sys.platform == 'win32':
            subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', '-R', path])
        else:
            subprocess.Popen(['xdg-open', os.path.dirname(path)])
    except Exception:
        pass


class Bus(QObject):
    """Signals used to hand results from worker threads back to the window."""
    loaded = Signal(int, object, object, object)
    load_failed = Signal(int, str)
    added = Signal(int)
    progress = Signal(float)
    exported = Signal(str, str)
    lyrics = Signal(int, object, str)
    update_info = Signal(object, str, bool)
    update_done = Signal(str, str)
    analyzed = Signal(int, object, str)
    synced = Signal(int, str)
    joined = Signal(str)
    join_progress = Signal(int, int, str)
    addon_progress = Signal(float, str)
    addon_done = Signal(str)


# ---------------------------------------------------------------- waveform
class Waveform(QWidget):
    seek = Signal(float)
    loop_selected = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(84)
        self.setMaximumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setCursor(Qt.PointingHandCursor)
        self.peaks = None
        self.dur = 0.0
        self.pos = 0.0
        self.loop = (None, None, False)
        self.drag = None
        self.setToolTip('Click to jump. Drag to choose a passage to loop.')

    def set_data(self, peaks, dur):
        self.peaks, self.dur = peaks, dur
        self.update()

    def set_pos(self, p):
        self.pos = p
        self.update()

    def set_loop(self, a, b, on):
        self.loop = (a, b, on)
        self.update()

    def _t(self, x):
        return max(0.0, min(1.0, x / max(1, self.width()))) * self.dur

    def mousePressEvent(self, e):
        if self.dur:
            x = e.position().x()
            self.drag = [x, self._t(x), self._t(x), False]

    def mouseMoveEvent(self, e):
        if self.drag:
            x = e.position().x()
            if abs(x - self.drag[0]) > 6:
                self.drag[3] = True
            self.drag[2] = self._t(x)
            self.update()

    def mouseReleaseEvent(self, e):
        if not self.drag:
            return
        d, self.drag = self.drag, None
        if d[3]:
            a, b = sorted((d[1], d[2]))
            if b - a > 0.2:
                self.loop_selected.emit(a, b)
        else:
            self.seek.emit(d[1])
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        W, H = self.width(), self.height()
        p.fillRect(0, 0, W, H, QColor('#1f1c1a'))
        base, top = H - 22, 6
        mid, amp = (base + top) / 2, (base - top) / 2
        x = (lambda t: t / self.dur * W) if self.dur else (lambda t: 0)
        a, b, on = self.loop
        if self.drag and self.drag[3]:
            a, b, on = min(self.drag[1:3]), max(self.drag[1:3]), True
        if a is not None and b is not None:
            p.fillRect(int(x(a)), 0, max(1, int(x(b) - x(a))), base + 3,
                       QColor(76, 201, 240, 60) if on else QColor(255, 255, 255, 18))
        if self.peaks is not None and len(self.peaks):
            px = x(self.pos)
            n = len(self.peaks)
            played, rest = QColor(INK), QColor('#6f675d')
            for i in range(0, W, 2):
                v = float(self.peaks[min(n - 1, int(i / W * n))]) * amp * 0.95 + 0.5
                p.fillRect(i, int(mid - v), 1, max(1, int(2 * v)), played if i < px else rest)
        p.setPen(QColor('#7d756a'))
        f = QFont()
        f.setPointSize(9)
        p.setFont(f)
        if self.dur:
            step = next(s for s in (5, 10, 15, 30, 60, 120, 300, 600) if W / (self.dur / s) > 60)
            t = 0.0
            while t <= self.dur:
                tx = int(x(t))
                if tx < W - 30:
                    p.drawLine(tx, base + 2, tx, base + 6)
                    p.drawText(tx + 3, H - 4, fmt(t))
                t += step
        pen = QPen(QColor(LOOP))
        pen.setWidth(2)
        p.setPen(pen)
        if not (self.drag and self.drag[3]):
            for t, lab in ((self.loop[0], 'A'), (self.loop[1], 'B')):
                if t is not None:
                    p.drawLine(int(x(t)), 0, int(x(t)), base + 3)
                    p.drawText(int(min(W - 12, x(t) + 4)), 16, lab)
        pen = QPen(QColor('#ff4d6d'))
        pen.setWidth(3)
        p.setPen(pen)
        p.drawLine(int(x(self.pos)), 0, int(x(self.pos)), base + 3)
        p.end()


# ---------------------------------------------------------------- song table
class SongModel(QAbstractTableModel):
    COLS = ['★', 'Title', 'Artist', 'Length', 'BPM', 'Key', 'Tags', 'Last played']

    def __init__(self):
        super().__init__()
        self.rows = []
        self.playing_id = None

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        for r in rows:
            r['_missing'] = not os.path.exists(r['path'])
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLS)

    def headerData(self, s, o, role=Qt.DisplayRole):
        if o == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLS[s]

    def data(self, idx, role=Qt.DisplayRole):
        r = self.rows[idx.row()]
        c = idx.column()
        if role == Qt.DisplayRole:
            if c == 0:
                return '★' if r['favorite'] else '☆'
            if c == 1:
                return ('▶  ' if r['id'] == self.playing_id else '') + (r['title'] or '')
            if c == 2:
                return r['artist'] or ''
            if c == 3:
                return fmt(r['duration']) if r['duration'] else ''
            if c == 4:
                return ('%g' % r['bpm']) if r['bpm'] else ''
            if c == 5:
                return r['key'] or ''
            if c == 6:
                return r['tags'] or ''
            if c == 7:
                return time.strftime('%Y-%m-%d', time.localtime(r['last_played'])) if r['last_played'] else ''
        if role == Qt.UserRole:
            return [r['favorite'], (r['title'] or '').lower(), (r['artist'] or '').lower(), r['duration'] or 0,
                    r['bpm'] or 0, r['key'] or '', (r['tags'] or '').lower(), r['last_played'] or 0][c]
        if role == Qt.ForegroundRole:
            if r['_missing']:
                return QColor('#6f675d')
            if c == 0 and r['favorite']:
                return QColor('#ff4d6d')
        if role == Qt.ToolTipRole and r['_missing']:
            return 'File not found: ' + r['path']
        if role == Qt.TextAlignmentRole and c in (3, 4):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.FontRole and r['id'] == self.playing_id:
            f = QFont()
            f.setBold(True)
            return f

    def flags(self, idx):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled

    def mimeTypes(self):
        return [MIME]

    def mimeData(self, idxs):
        ids = sorted({self.rows[i.row()]['id'] for i in idxs})
        m = QMimeData()
        m.setData(MIME, QByteArray(json.dumps(ids).encode()))
        return m


def drag_pixmap(text, dpr=1.0):
    """A small, see-through label for dragging songs: sits below-right of the cursor
    so the place you drop on stays visible."""
    f = QFont()
    f.setPixelSize(13)
    f.setBold(True)
    fm = QFontMetrics(f)
    text = fm.elidedText(text, Qt.ElideRight, 260)
    pad_x, off_x, off_y = 12, 22, 4  # empty space up-left keeps the label clear of the cursor
    w, h = fm.horizontalAdvance(text) + 2 * pad_x, 28
    pm = QPixmap(int((w + off_x) * dpr), int((h + off_y) * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setOpacity(0.82)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(ACC))
    p.drawRoundedRect(QRectF(off_x, off_y, w, h), h / 2, h / 2)
    p.setOpacity(1.0)
    p.setPen(QColor('#ffffff'))
    p.setFont(f)
    p.drawText(QRectF(off_x, off_y, w, h), Qt.AlignCenter, text)
    p.end()
    return pm


class SongTable(QTableView):
    """Song list whose drag image is a small label instead of a picture of the whole rows."""

    def startDrag(self, actions):
        idxs = self.selectionModel().selectedRows(1)
        if not idxs:
            return
        mime = self.model().mimeData(idxs)
        if mime is None:
            return
        n = len(idxs)
        title = str(self.model().data(idxs[0]) or '').replace('▶', '').strip()
        text = ('♪  ' + title) if n == 1 else '♪  %d songs' % n
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(drag_pixmap(text, self.devicePixelRatioF()))
        drag.setHotSpot(QPoint(0, 0))
        drag.exec(Qt.CopyAction)


class _DropTargetDelegate(QStyledItemDelegate):
    """Paints the 'drop here' highlight under the item text (the style sheet would hide an item colour)."""

    def __init__(self, sidebar):
        super().__init__(sidebar)
        self.sidebar = sidebar

    def paint(self, painter, option, index):
        hl = self.sidebar._hl
        if hl is not None and self.sidebar.row(hl) == index.row():
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor(ACC), 1.5))
            painter.setBrush(QColor(200, 23, 74, 120))
            painter.drawRoundedRect(QRectF(option.rect).adjusted(1, 1, -1, -1), 6, 6)
            painter.restore()
        super().paint(painter, option, index)


class Sidebar(QListWidget):
    """Library views and collections. Songs (or audio files) can be dropped on a collection;
    the collection under the cursor lights up while dragging."""
    dropped = Signal(int, list)
    files_dropped = Signal(object, list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self._hl = None
        self.setItemDelegate(_DropTargetDelegate(self))

    @staticmethod
    def _cid(it):
        key = str(it.data(Qt.UserRole)) if it else ''
        return int(key.split(':')[1]) if key.startswith('collection:') else None

    def _highlight(self, it):
        if it is self._hl:
            return
        self._hl = it
        self.viewport().update()

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasFormat(MIME) or md.hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        it = self.itemAt(e.position().toPoint())
        cid = self._cid(it)
        if cid is not None:
            self._highlight(it)
            e.acceptProposedAction()
        elif e.mimeData().hasUrls():  # files dropped elsewhere in the sidebar: just add to the library
            self._highlight(None)
            e.acceptProposedAction()
        else:
            self._highlight(None)
            e.ignore()

    def dragLeaveEvent(self, e):
        self._highlight(None)

    def dropEvent(self, e):
        it = self.itemAt(e.position().toPoint())
        cid = self._cid(it)
        self._highlight(None)
        md = e.mimeData()
        if md.hasFormat(MIME) and cid is not None:
            self.dropped.emit(cid, json.loads(bytes(md.data(MIME)).decode()))
            e.acceptProposedAction()
        elif md.hasUrls():
            paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
            if paths:
                self.files_dropped.emit(cid, paths)
                e.acceptProposedAction()


class SyncDialog(QDialog):
    """Explains sync and lets you pick, change or turn off the sync folder."""

    def __init__(self, parent, root):
        super().__init__(parent)
        self.setWindowTitle('Sync between computers')
        self.setMinimumWidth(520)
        self.action = None
        v = QVBoxLayout(self)
        v.setSpacing(10)
        intro = QLabel('Keep the same library on all your computers. Choose a folder that Google Drive, '
                       'Dropbox, iCloud Drive or OneDrive keeps in sync. Tempo keeps your songs, collections, '
                       'song details, favourites, lyrics and separated instruments there.')
        intro.setWordWrap(True)
        v.addWidget(intro)
        state = QLabel(('<b>Sync is on.</b><br>' + root.replace('&', '&amp;').replace('<', '&lt;'))
                       if root else '<b>Sync is off.</b> Your library is only on this computer.')
        state.setWordWrap(True)
        state.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(state)
        tips = QLabel('Tips\n'
                      '• Google Drive: in the Drive app\'s settings choose “Mirror files”, or right-click the '
                      'Tempo Library folder and make it available offline, so songs open instantly.\n'
                      '• On your other computer, open Tempo, click Sync and choose the same folder.\n'
                      '• If the same song is changed on two computers at once, the latest change is kept.')
        tips.setObjectName('soft')
        tips.setWordWrap(True)
        v.addWidget(tips)
        row = QHBoxLayout()
        pick = QPushButton('Change folder…' if root else 'Choose sync folder…', objectName='accent')
        pick.clicked.connect(lambda: self._done('choose'))
        row.addWidget(pick)
        if root:
            off = QPushButton('Turn off sync')
            off.clicked.connect(lambda: self._done('off'))
            row.addWidget(off)
        row.addStretch(1)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        row.addWidget(close)
        v.addLayout(row)

    def _done(self, action):
        self.action = action
        self.accept()


def cloud_start_dir():
    """Where the folder picker opens: the Google Drive folder if the Drive app is installed."""
    home = os.path.expanduser('~')
    if sys.platform == 'darwin':
        cs = os.path.join(home, 'Library', 'CloudStorage')
        if os.path.isdir(cs):
            for name in sorted(os.listdir(cs)):
                if name.startswith('GoogleDrive'):
                    return os.path.join(cs, name)
            return cs
    elif sys.platform == 'win32':
        for d in ('G:\\My Drive', 'G:\\Min enhet', 'G:\\'):
            if os.path.isdir(d):
                return d
    return home


class InfoDialog(QDialog):
    def __init__(self, parent, song, all_tags):
        super().__init__(parent)
        self.setWindowTitle('Song details')
        self.setMinimumWidth(460)
        f = QFormLayout(self)
        self.title = QLineEdit(song['title'] or '')
        self.artist = QLineEdit(song['artist'] or '')
        self.album = QLineEdit(song['album'] or '')
        self.bpm = QDoubleSpinBox()
        self.bpm.setRange(0, 400)
        self.bpm.setDecimals(1)
        self.bpm.setSpecialValueText('Unknown')
        self.bpm.setValue(song['bpm'] or 0)
        self.key = QLineEdit(song['key'] or '')
        self.key.setPlaceholderText('e.g. G major')
        self.tags = QLineEdit(song['tags'] or '')
        self.tags.setPlaceholderText('Comma separated, e.g. Grade 3, Emma, exam piece')
        if all_tags:
            self.tags.setToolTip('Tags in use: ' + ', '.join(all_tags))
        for lab, w in (('Title', self.title), ('Artist', self.artist), ('Album', self.album), ('Tempo (BPM)', self.bpm),
                       ('Key', self.key), ('Tags', self.tags)):
            f.addRow(lab, w)
        path = QLabel(song['path'])
        path.setObjectName('soft')
        path.setWordWrap(True)
        path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f.addRow('File', path)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def values(self):
        tags = ', '.join(t.strip() for t in self.tags.text().split(',') if t.strip())
        return dict(title=self.title.text().strip(), artist=self.artist.text().strip(), album=self.album.text().strip(),
                    bpm=self.bpm.value() or None, key=self.key.text().strip(), tags=tags)


# ---------------------------------------------------------------- background analysis
class Analyzer:
    """Finds BPM, beats and key one song at a time in a background thread.
    The song you open goes to the front of the queue."""

    def __init__(self, bus):
        self.bus = bus
        self.q = []
        self.pending = set()
        self.seq = 0
        self.cv = threading.Condition()
        threading.Thread(target=self._run, daemon=True).start()

    def add(self, sid, path, urgent=False):
        with self.cv:
            if sid in self.pending and not urgent:
                return
            self.seq += 1
            heapq.heappush(self.q, (0 if urgent else 1, self.seq, sid, path))
            self.pending.add(sid)
            self.cv.notify()

    def _run(self):
        while True:
            with self.cv:
                while not self.q:
                    self.cv.wait()
                _, _, sid, path = heapq.heappop(self.q)
                if sid not in self.pending:
                    continue
                self.pending.discard(sid)
            try:
                self.bus.analyzed.emit(sid, analysis.analyze(path), '')
            except Exception as e:
                self.bus.analyzed.emit(sid, None, str(e) or type(e).__name__)
            time.sleep(0.05)


# ---------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP)
        self.settings = QSettings(APP, APP)
        self.db_path = os.path.join(data_dir(), 'library.sqlite')
        self.sync = None
        root = self.settings.value('sync_folder', '') or ''
        self._sync_missing = False
        if root:
            if os.path.isdir(root):
                try:
                    self.sync = SyncFolder(root)
                except OSError:
                    self._sync_missing = True
            else:
                self._sync_missing = True
        self.lib = Library(self.db_path, self.sync)
        self._sync_busy = False
        self._last_sync = None
        self.bus = Bus()
        self.bus.loaded.connect(self._on_loaded)
        self.bus.load_failed.connect(self._on_load_failed)
        self.bus.lyrics.connect(self._on_lyrics)
        self.bus.update_info.connect(self._on_update_info)
        self.bus.update_done.connect(self._on_update_done)
        self.bus.addon_progress.connect(self._on_addon_progress)
        self.bus.addon_done.connect(self._on_addon_done)
        self.update_rel = None
        self._split = None
        self.ly_lines, self.ly_times, self.ly_synced, self.ly_cur = [], [], False, -1
        self.ly_results, self.ly_token, self.ly_song = [], 0, None
        self.ly_rec, self.ly_offset = None, 0.0
        self.bus.added.connect(lambda n: (self.refresh_sidebar(), self.refresh(),
                                          self.status('Added %d song%s' % (n, '' if n == 1 else 's')),
                                          self._queue_analysis()))
        self.bus.analyzed.connect(self._on_analyzed)
        self.bus.synced.connect(self._on_synced)
        self.bus.joined.connect(self._on_joined)
        self.bus.join_progress.connect(self._on_join_progress)
        self.analyzer = Analyzer(self.bus)
        self._refresh_later = QTimer(self, singleShot=True, interval=600, timeout=self.refresh)
        self.player = Player()
        self.song = None
        self.main_audio = None
        self.stems = {}
        self.load_token = 0
        self.loop_a = self.loop_b = None
        self.loop_on = False
        self.loop_count = 0
        self.last_pos = 0.0
        self.stem_proc = None
        self.view = 'all'
        self.whole = 0
        self._resume_after = None
        self._keep_settings = False
        self._build()
        self.refresh_sidebar()
        self.refresh()
        g = self.settings.value('geometry')
        if g:
            self.restoreGeometry(g)
        else:
            scr = QApplication.primaryScreen().availableGeometry()
            self.resize(min(1280, scr.width() - 40), min(860, scr.height() - 30))
        s = self.settings.value('splitter')
        if s:
            self.vsplit.restoreState(s)
        self.timer = QTimer(self, interval=33, timeout=self._tick)
        self.timer.start()
        self.status('Engine: ' + self.player.engine_name + ('' if 'Rubber' in self.player.engine_name else
                    '  (Rubber Band unavailable: %s)' % engine_problem()))
        self.engine_lbl.setText(self.player.engine_name)
        self.setWindowTitle('%s %s' % (APP, __version__))
        self.click_btn.setChecked(self.settings.value('click', 'false') in (True, 'true'))
        self._set_countin(int(self.settings.value('countin', 0) or 0))
        QTimer.singleShot(2500, self._queue_analysis)
        self._update_sync_btn()
        self.sync_timer = QTimer(self, interval=10000, timeout=self._poll_sync)
        self.sync_timer.start()
        QTimer.singleShot(1200, self._poll_sync)
        if self._sync_missing:
            self.status('Sync folder not found. Is Google Drive (or your sync app) running? Working offline for now.')
        last = float(self.settings.value('update_check', 0) or 0)
        if time.time() - last > 20 * 3600:
            QTimer.singleShot(4000, lambda: self.check_updates(manual=False))
        self._build_stems_ui()
        self._update_player_ui()

    # ---------- layout ----------
    def _build(self):
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)
        logo = QLabel('  Tempo  ')
        logo.setStyleSheet('font-size: 24px; font-weight: 800;')
        tb.addWidget(logo)
        for text, fn in (('Add songs…', self.add_files), ('Add folder…', self.add_folder)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            tb.addWidget(b)
        sp = QWidget()
        sp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(sp)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search title, artist, tags…')
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(300)
        self.search.textChanged.connect(lambda: self.refresh())
        tb.addWidget(self.search)
        self.ly_btn = QPushButton('Side panel', checkable=True)
        self.ly_btn.setToolTip('Show or hide lyrics and instruments')
        self.ly_btn.toggled.connect(self._toggle_lyrics)
        tb.addWidget(self.ly_btn)
        self.sync_btn = QPushButton('Sync')
        self.sync_btn.clicked.connect(self.open_sync)
        tb.addWidget(self.sync_btn)
        self.upd_btn = QPushButton('Updates')
        self.upd_btn.setToolTip('Tempo %s. Check for a newer version.' % __version__)
        self.upd_btn.clicked.connect(lambda: self.check_updates(manual=True))
        tb.addWidget(self.upd_btn)

        root = QWidget(objectName='root')
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(20, 14, 20, 16)
        hsplit = QSplitter(Qt.Horizontal)
        lay.addWidget(hsplit)

        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        self.sidebar = Sidebar()
        self.sidebar.currentItemChanged.connect(self._view_changed)
        self.sidebar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sidebar.customContextMenuRequested.connect(self._sidebar_menu)
        self.sidebar.dropped.connect(lambda cid, ids: (self.lib.add_to_collection(cid, ids), self.refresh_sidebar(),
                                                       self.status('Added to collection')))
        self.sidebar.files_dropped.connect(lambda cid, paths: self._add_paths(
            paths, 'collection:%d' % cid if cid is not None else 'all'))
        sl.addWidget(self.sidebar)
        nb = QPushButton('+ New collection')
        nb.clicked.connect(self.new_collection)
        sl.addWidget(nb)
        side.setMinimumWidth(190)
        hsplit.addWidget(side)

        self.vsplit = QSplitter(Qt.Vertical)
        hsplit.addWidget(self.vsplit)
        self.side_tabs = QTabWidget()
        self.side_tabs.setMinimumWidth(240)
        self.side_tabs.addTab(self._build_lyrics(), 'Lyrics')
        inst = QWidget()
        self.stems_lay = QVBoxLayout(inst)
        self.stems_lay.setContentsMargins(12, 12, 12, 12)
        self.side_tabs.addTab(inst, 'Instruments')
        self.side_tabs.setCurrentIndex(int(self.settings.value('side_tab', 0) or 0))
        self.side_tabs.currentChanged.connect(lambda i: self.settings.setValue('side_tab', i))
        self.ly_panel = self.side_tabs
        hsplit.addWidget(self.side_tabs)
        hsplit.setStretchFactor(1, 1)
        hsplit.setStretchFactor(2, 0)
        scr_w = QApplication.primaryScreen().availableGeometry().width()
        hsplit.setSizes([190, 1000, 300 if scr_w >= 1400 else 260])
        show = self.settings.value('lyrics', 'true') in (True, 'true')
        self.ly_btn.setChecked(show)
        self.ly_panel.setVisible(show)

        self.model = SongModel()
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.UserRole)
        self.table = SongTable()
        self.table.setModel(self.proxy)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(QAbstractItemView.DragOnly)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(False)
        for c, w in enumerate([34, 300, 130, 64, 50, 64, 110, 96]):
            self.table.setColumnWidth(c, w)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setMinimumSectionSize(30)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.doubleClicked.connect(lambda i: self.open_song(self._row(i)['id']))
        self.table.clicked.connect(self._table_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        self.empty = QLabel('Your library is empty.\nClick “Add songs…” or “Add folder…”, or drop audio files here.')
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName('soft')
        tw = QWidget()
        tl = QVBoxLayout(tw)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.table)
        tl.addWidget(self.empty)
        self.vsplit.addWidget(tw)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self._build_player())
        self.vsplit.addWidget(scroll)
        scr_h = QApplication.primaryScreen().availableGeometry().height()
        self.vsplit.setSizes([230, 480] if scr_h >= 880 else [175, 480])
        self.setAcceptDrops(True)

        for key, fn in ((Qt.Key_Space, self.toggle), (Qt.Key_Left, lambda: self.seek_rel(-5)),
                        (Qt.Key_Right, lambda: self.seek_rel(5)), (Qt.Key_BracketLeft, lambda: self.nudge_speed(-5)),
                        (Qt.Key_BracketRight, lambda: self.nudge_speed(5)), (Qt.Key_A, self.set_a),
                        (Qt.Key_B, self.set_b), (Qt.Key_L, self.toggle_loop)):
            QShortcut(QKeySequence(key), self, activated=fn)
        QShortcut(QKeySequence.Find, self, activated=self.search.setFocus)
        for key in (Qt.Key_Return, Qt.Key_Enter):
            QShortcut(QKeySequence(key), self, activated=self._enter_pressed)

    def _build_player(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 6, 12, 4)
        v.setSpacing(8)
        head = QHBoxLayout()
        tv = QVBoxLayout()
        tv.setSpacing(0)
        self.title_lbl = QLabel('No song loaded', objectName='title')
        self.sub_lbl = QLabel('Double-click a song to open it.', objectName='soft')
        tv.addWidget(self.title_lbl)
        tv.addWidget(self.sub_lbl)
        head.addLayout(tv, 1)
        self.engine_lbl = QLabel('', objectName='soft')
        head.addWidget(self.engine_lbl, 0, Qt.AlignRight | Qt.AlignTop)
        v.addLayout(head)

        self.wave = Waveform()
        self.wave.seek.connect(self.seek)
        self.wave.loop_selected.connect(lambda a, b: self.set_loop(a, b, True, jump=True))
        v.addWidget(self.wave)

        tr = QHBoxLayout()
        self.icons = {k: make_icon(k, '#ffffff' if k in ('play', 'pause') else INK) for k in ('play', 'pause', 'back', 'fwd')}
        self.back_btn = QPushButton(objectName='round', clicked=lambda: self.seek_rel(-5))
        self.play_btn = QPushButton(objectName='play', clicked=self.toggle)
        self.fwd_btn = QPushButton(objectName='round', clicked=lambda: self.seek_rel(5))
        self._shown_playing = None
        for b, k, px in ((self.back_btn, 'back', 30), (self.play_btn, 'play', 30), (self.fwd_btn, 'fwd', 30)):
            b.setIcon(self.icons[k])
            b.setIconSize(QSize(px, px))
        self.back_btn.setToolTip('Back 5 s (←)')
        self.fwd_btn.setToolTip('Forward 5 s (→)')
        self.play_btn.setToolTip('Play / pause (Space)')
        self.time_lbl = QLabel('0:00 / 0:00', objectName='time')
        for x in (self.back_btn, self.play_btn, self.fwd_btn):
            tr.addWidget(x)
        tr.addSpacing(8)
        tr.addWidget(self.time_lbl)
        tr.addSpacing(12)
        self.click_btn = QPushButton('Click', checkable=True)
        self.click_btn.setToolTip('Metronome click on every beat, in time at any speed (bar starts are higher)')
        self.click_btn.toggled.connect(self._toggle_click)
        tr.addWidget(self.click_btn)
        self.countin_btn = QPushButton('Count-in', checkable=True)
        self.countin_btn.setToolTip('One bar of clicks before the music starts')
        m = QMenu(self.countin_btn)
        self.countin_actions = []
        for i, label in enumerate(('Off', 'Before playing', 'Before playing and every loop repeat')):
            act = m.addAction(label)
            act.setCheckable(True)
            act.triggered.connect(lambda _=False, i=i: self._set_countin(i))
            self.countin_actions.append(act)
        self.countin_btn.setMenu(m)
        tr.addWidget(self.countin_btn)
        tr.addStretch(1)
        self.vol = QSlider(Qt.Horizontal, minimum=0, maximum=100, value=90)
        self.vol.setToolTip('Volume')
        self.vol.setFixedWidth(110)
        self.vol.valueChanged.connect(lambda x: setattr(self.player, 'volume', x / 100))
        tr.addWidget(self.vol)
        self.export_btn = QPushButton('Save track…', clicked=self.export)
        self.export_btn.setToolTip('Save the song at this speed and pitch as an audio file')
        tr.addSpacing(10)
        tr.addWidget(self.export_btn)
        v.addLayout(tr)

        self.ctl_row = QBoxLayout(QBoxLayout.LeftToRight)
        self.ctl_row.setSpacing(12)
        self.ctl_row.addWidget(self._speed_box(), 1, Qt.AlignTop)
        mid = QVBoxLayout()
        mid.setSpacing(10)
        mid.addWidget(self._pitch_box())
        mid.addWidget(self._loop_box())
        mid.addStretch(1)
        self.ctl_row.addLayout(mid, 1)
        v.addLayout(self.ctl_row)
        v.addStretch(1)
        w.installEventFilter(self)
        self._player_w = w
        return w

    def eventFilter(self, obj, ev):
        if obj is getattr(self, '_player_w', None) and ev.type() == ev.Type.Resize:
            want = QBoxLayout.TopToBottom if obj.width() < 600 else QBoxLayout.LeftToRight
            if self.ctl_row.direction() != want:
                self.ctl_row.setDirection(want)
        return super().eventFilter(obj, ev)

    def _speed_box(self):
        g = QGroupBox('Speed')
        v = QVBoxLayout(g)
        top = QHBoxLayout()
        self.speed_lbl = QLabel('100%', objectName='big')
        top.addWidget(self.speed_lbl)
        top.addStretch(1)
        self.bpm_lbl = QLabel('', objectName='soft')
        top.addWidget(self.bpm_lbl, 0, Qt.AlignBottom)
        v.addLayout(top)
        self.speed_sl = QSlider(Qt.Horizontal, minimum=25, maximum=200, value=100)
        self.speed_sl.valueChanged.connect(lambda x: self.set_speed(x / 100, from_slider=True))
        v.addWidget(self.speed_sl)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.preset_btns = {}
        for i, p in enumerate([50, 60, 70, 75, 80, 90, 100, 110, 125, 150]):
            b = QPushButton('%d%%' % p, checkable=True)
            b.clicked.connect(lambda _=False, p=p: self.set_speed(p / 100))
            self.preset_btns[p] = b
            grid.addWidget(b, i // 5, i % 5)
        v.addLayout(grid)
        v.addStretch(1)
        return g

    def _pitch_box(self):
        g = QGroupBox('Pitch')
        v = QVBoxLayout(g)
        r = QHBoxLayout()
        self.p_down = QPushButton('−1', clicked=lambda: self._step_pitch(-1))
        self.p_val = QLabel('0')
        self.p_val.setStyleSheet('font-size: 24px; font-weight: 700; min-width: 44px;')
        self.p_val.setAlignment(Qt.AlignCenter)
        self.p_up = QPushButton('+1', clicked=lambda: self._step_pitch(1))
        self.p_name = QLabel('original key', objectName='soft')
        for x in (self.p_down, self.p_val, self.p_up, self.p_name):
            r.addWidget(x)
        r.addStretch(1)
        v.addLayout(r)
        c = QHBoxLayout()
        c.addWidget(QLabel('Fine'))
        self.cents = QSlider(Qt.Horizontal, minimum=-50, maximum=50, value=0)
        self.cents.valueChanged.connect(lambda x: self.set_pitch(self.whole + x / 100))
        self.cents_lbl = QLabel('0 ¢')
        self.cents_lbl.setMinimumWidth(44)
        c.addWidget(self.cents, 1)
        c.addWidget(self.cents_lbl)
        rb = QPushButton('Reset', clicked=self._reset_pitch)
        c.addWidget(rb)
        v.addLayout(c)
        return g

    def _cents(self):
        return self.cents.value() / 100

    def _step_pitch(self, d):
        self.whole = max(-12, min(12, self.whole + d))
        self.set_pitch(self.whole + self._cents())

    def _reset_pitch(self):
        self.whole = 0
        self.cents.blockSignals(True)
        self.cents.setValue(0)
        self.cents.blockSignals(False)
        self.set_pitch(0)

    def _loop_box(self):
        g = QGroupBox('Loop')
        v = QVBoxLayout(g)
        r = QHBoxLayout()
        self.a_btn = QPushButton('Set A', clicked=self.set_a)
        self.b_btn = QPushButton('Set B', clicked=self.set_b)
        self.loop_btn = QPushButton('Loop off', objectName='loopOn', checkable=True, clicked=self.toggle_loop)
        self.toa_btn = QPushButton('To A', clicked=lambda: self.seek(self.loop_a or 0))
        self.toa_btn.setToolTip('Back to the start of the loop')
        clr = QPushButton('Clear', clicked=lambda: self.set_loop(None, None, False))
        for x in (self.a_btn, self.b_btn):
            r.addWidget(x, 1)
        r2 = QHBoxLayout()
        for x in (self.loop_btn, self.toa_btn, clr):
            r2.addWidget(x, 1)
        v.addLayout(r)
        v.addLayout(r2)
        return g

    # ---------- lyrics ----------
    def _build_lyrics(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        r = QHBoxLayout()
        self.ly_query = QLineEdit()
        self.ly_query.setPlaceholderText('Song title and artist')
        self.ly_query.returnPressed.connect(lambda: self.search_lyrics(manual=True))
        r.addWidget(self.ly_query, 1)
        r.addWidget(QPushButton('Search', clicked=lambda: self.search_lyrics(manual=True)))
        v.addLayout(r)
        self.ly_pick = QComboBox()
        self.ly_pick.setToolTip('Other versions found')
        self.ly_pick.activated.connect(self._show_lyrics_result)
        self.ly_pick.hide()
        v.addWidget(self.ly_pick)
        self.ly_list = QListWidget(objectName='lyrics')
        self.ly_list.setWordWrap(True)
        self.ly_list.setFocusPolicy(Qt.NoFocus)
        self.ly_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.ly_list.itemClicked.connect(self._lyric_clicked)
        v.addWidget(self.ly_list, 1)
        self.ly_status = QLabel('Open a song to see its lyrics.', objectName='soft')
        self.ly_status.setWordWrap(True)
        v.addWidget(self.ly_status)
        t = QHBoxLayout()
        self.ly_timing_lbl = QLabel('Timing')
        t.addWidget(self.ly_timing_lbl)
        self.ly_earlier = QPushButton('Earlier', clicked=lambda: self._nudge_lyrics(-0.25))
        self.ly_earlier.setToolTip('Highlight lines a quarter second sooner')
        self.ly_later = QPushButton('Later', clicked=lambda: self._nudge_lyrics(0.25))
        self.ly_later.setToolTip('Highlight lines a quarter second later')
        self.ly_off_lbl = QLabel('0.0 s')
        self.ly_off_lbl.setMinimumWidth(48)
        self.ly_off_lbl.setAlignment(Qt.AlignCenter)
        self.ly_sync = QPushButton('Sync', checkable=True)
        self.ly_sync.setToolTip('Click Sync, then click the line that is being sung right now. '
                                'Everything lines up from there.')
        self.ly_sync.toggled.connect(self._sync_mode)
        for x in (self.ly_earlier, self.ly_off_lbl, self.ly_later, self.ly_sync):
            t.addWidget(x)
        t.addStretch(1)
        v.addLayout(t)
        self.ly_timing = [self.ly_timing_lbl, self.ly_earlier, self.ly_later, self.ly_sync, self.ly_off_lbl]
        for x in self.ly_timing:
            x.hide()
        b = QHBoxLayout()
        self.ly_follow = QCheckBox('Auto-scroll')
        self.ly_follow.setToolTip('Keep the current line in view')
        self.ly_follow.setChecked(True)
        b.addWidget(self.ly_follow)
        b.addStretch(1)
        b.addWidget(QPushButton('Paste lyrics…', clicked=self._paste_lyrics))
        v.addLayout(b)
        return w

    def _toggle_lyrics(self, on):
        self.ly_panel.setVisible(on)
        self.settings.setValue('lyrics', 'true' if on else 'false')
        if on and self.song and self.ly_song != self.song['id']:
            self._lyrics_for_song()

    def _lyrics_for_song(self):
        s = self.song
        if not s:
            return
        self.ly_song = s['id']
        self.ly_pick.hide()
        self.ly_query.setText(' '.join(x for x in (s['title'], s['artist']) if x))
        cached = s.get('lyrics') or ''
        if cached:
            try:
                rec = json.loads(cached)
                self._show_lyrics(*lyrics.parse(rec), rec)
                return
            except ValueError:
                pass
        self._show_lyrics([], False, None)
        if self.ly_panel.isVisible():
            self.search_lyrics()

    def search_lyrics(self, manual=False):
        q = self.ly_query.text().strip()
        if not q:
            return
        s = self.song or {}
        title, artist = ('', '') if manual else (s.get('title') or '', s.get('artist') or '')
        dur = s.get('duration')
        self.ly_token += 1
        tok = self.ly_token
        self.ly_status.setText('Searching for lyrics…')

        def work():
            try:
                self.bus.lyrics.emit(tok, lyrics.search(q, title, artist, dur), '')
            except Exception as e:
                self.bus.lyrics.emit(tok, [], str(e) or type(e).__name__)

        threading.Thread(target=work, daemon=True).start()

    def _on_lyrics(self, tok, results, err):
        if tok != self.ly_token:
            return
        self.ly_results = results
        if err:
            self.ly_status.setText('Could not reach the lyrics service. Check your internet connection. (%s)' % err)
            return
        if not results:
            self._show_lyrics([], False, None)
            self.ly_status.setText('No lyrics found. Try other words in the search box, or paste them yourself.')
            return
        self.ly_pick.clear()
        for r in results:
            tag = 'synced' if r.get('syncedLyrics') else ('instrumental' if r.get('instrumental') else 'text only')
            self.ly_pick.addItem('%s – %s  (%s, %s)' % (r.get('trackName') or '?', r.get('artistName') or '?',
                                                        fmt(r.get('duration') or 0), tag))
        self.ly_pick.setVisible(len(results) > 1)
        self.ly_pick.setCurrentIndex(0)
        self._show_lyrics_result(0)

    def _show_lyrics_result(self, i):
        if not (0 <= i < len(self.ly_results)):
            return
        r = self.ly_results[i]
        rec = {k: r.get(k) for k in ('trackName', 'artistName', 'plainLyrics', 'syncedLyrics', 'instrumental')}
        rec['offset'] = 0.0
        self._cache_lyrics(rec)
        self._show_lyrics(*lyrics.parse(rec), rec)

    def _cache_lyrics(self, rec):
        if self.song:
            data = json.dumps(rec)
            self.lib.update(self.song['id'], lyrics=data)
            self.song['lyrics'] = data

    def _show_lyrics(self, lines, synced, rec):
        self.ly_list.clear()
        self.ly_rec = rec
        self.ly_lines, self.ly_synced, self.ly_cur = lines, synced, -1
        try:
            off = float((rec or {}).get('offset') or 0.0)
        except (TypeError, ValueError):
            off = 0.0
        self.ly_offset = off
        self.ly_off_lbl.setText('%+.1f s' % off if abs(off) >= 0.05 else '0.0 s')
        self.ly_sync.setChecked(False)
        for x in self.ly_timing:
            x.setVisible(bool(synced))
        self.ly_times = [t for t, _ in lines] if synced else []
        for t, text in lines:
            it = QListWidgetItem(text or ' ')
            if synced:
                it.setForeground(QColor(SOFT))
                it.setToolTip('Jump to %s' % fmt(t))
            self.ly_list.addItem(it)
        self._lyrics_status()

    def _lyrics_status(self):
        rec, src = self.ly_rec, ''
        if rec and rec.get('trackName'):
            src = ' Lyrics from LRCLIB.'
        if not self.ly_lines:
            self.ly_status.setText('')
        elif self.ly_synced:
            self.ly_status.setText('')
        else:
            self.ly_status.setText('These lyrics have no timing, so they don’t follow the music.' + src)

    def _lyric_clicked(self, it):
        i = self.ly_list.row(it)
        if not (self.ly_synced and 0 <= i < len(self.ly_times) and self.song):
            return
        if self.ly_sync.isChecked():
            self._set_lyrics_offset(self.player.position() - self.ly_times[i])
            self.ly_sync.setChecked(False)
            self.status('Lyrics synced: that line starts now.')
            return
        self.seek(max(0.0, self.ly_times[i] + self.ly_offset - 0.3))

    def _sync_mode(self, on):
        if on:
            self.ly_status.setText('Now click the line that is being sung right now.')
            if self.song and not self.player.playing:
                self.toggle()
        else:
            self._lyrics_status()

    def _nudge_lyrics(self, d):
        self._set_lyrics_offset(self.ly_offset + d)

    def _set_lyrics_offset(self, off):
        self.ly_offset = round(max(-60.0, min(60.0, off)), 2)
        self.ly_off_lbl.setText('%+.1f s' % self.ly_offset if abs(self.ly_offset) >= 0.05 else '0.0 s')
        if 0 <= self.ly_cur < self.ly_list.count():
            old = self.ly_list.item(self.ly_cur)
            old.setFont(QFont())
            old.setForeground(QColor(SOFT))
        self.ly_cur = -1
        if self.ly_rec is not None:
            self.ly_rec['offset'] = self.ly_offset
            self._cache_lyrics(self.ly_rec)

    def _paste_lyrics(self):
        if not self.song:
            self.ly_status.setText('Open a song first.')
            return
        d = QDialog(self)
        d.setWindowTitle('Lyrics for ' + (self.song['title'] or 'this song'))
        d.resize(460, 560)
        v = QVBoxLayout(d)
        v.addWidget(QLabel('Paste or type the lyrics. Lines starting with a time like [01:23.45] will follow the music.'))
        ed = QPlainTextEdit('\n'.join(t for _, t in self.ly_lines))
        v.addWidget(ed, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        if d.exec():
            text = ed.toPlainText().strip()
            lines, synced = lyrics.parse_text(text)
            rec = {'syncedLyrics': text} if synced else {'plainLyrics': text}
            self._cache_lyrics(rec)
            self.ly_pick.hide()
            self._show_lyrics(lines, synced, rec)

    def _tick_lyrics(self, pos):
        if not self.ly_synced or not self.ly_times:
            return
        i = bisect.bisect_right(self.ly_times, pos - self.ly_offset + 0.15) - 1
        if i == self.ly_cur:
            return
        bold = QFont()
        bold.setBold(True)
        bold.setPixelSize(19)
        if 0 <= self.ly_cur < self.ly_list.count():
            old = self.ly_list.item(self.ly_cur)
            old.setFont(QFont())
            old.setForeground(QColor(SOFT))
        self.ly_cur = i
        if i >= 0:
            it = self.ly_list.item(i)
            it.setFont(bold)
            it.setForeground(QColor(INK))
            if self.ly_follow.isChecked():
                self.ly_list.scrollToItem(it, QAbstractItemView.PositionAtCenter)

    # ---------- sync ----------
    def _update_sync_btn(self):
        if self._sync_missing:
            self.sync_btn.setText('Sync ⚠')
            self.sync_btn.setToolTip('The sync folder can\'t be found. Is Google Drive (or your sync app) running?')
        elif self.sync:
            self.sync_btn.setText('Synced')
            when = time.strftime('%H:%M', time.localtime(self._last_sync)) if self._last_sync else 'not yet'
            self.sync_btn.setToolTip('Syncing with %s\nLast checked: %s' % (self.sync.root, when))
        else:
            self.sync_btn.setText('Sync')
            self.sync_btn.setToolTip('Keep your library on all your computers')

    def open_sync(self):
        root = self.sync.root if self.sync else ''
        if self._sync_missing:
            root = self.settings.value('sync_folder', '')
        d = SyncDialog(self, root)
        if not d.exec():
            return
        if d.action == 'off':
            if QMessageBox.question(self, 'Turn off sync', 'Stop syncing this computer? Your songs and library '
                                    'stay as they are; changes are just no longer shared.') == QMessageBox.Yes:
                self.sync = None
                self.lib.sync = None
                self._sync_missing = False
                self.settings.remove('sync_folder')
                self._update_sync_btn()
                self.status('Sync turned off')
        elif d.action == 'choose':
            chosen = QFileDialog.getExistingDirectory(self, 'Choose the folder to sync through '
                                                      '(for example in Google Drive)', cloud_start_dir())
            if chosen:
                self._start_sync(chosen)

    def _start_sync(self, chosen):
        root = resolve_root(chosen)
        existing = os.path.isdir(os.path.join(root, 'data', 'songs'))
        try:
            sync = SyncFolder(root)
        except OSError as e:
            QMessageBox.warning(self, 'Sync', 'Tempo can\'t use that folder:\n%s' % e)
            return
        probe = Library(self.db_path, sync)
        n, size = probe.to_copy()
        msg = ('Tempo will sync your library through:\n%s\n\n' % root)
        if existing:
            msg += 'This folder already has a Tempo library. It will be combined with the one on this computer.\n\n'
        if n:
            msg += ('%d song%s (%s) will be copied into the folder so your other computers can play them. '
                    'The original files stay where they are.' % (n, '' if n == 1 else 's', _size(size)))
        else:
            msg += 'All your songs are already in the folder.'
        if QMessageBox.question(self, 'Start syncing', msg) != QMessageBox.Yes:
            return
        dlg = QProgressDialog('Setting up sync…', None, 0, 100, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        self._join_dlg = dlg
        self._join_sync = sync
        db, old = self.db_path, lambda row: os.path.join(data_dir(), 'stems', str(row['id']))

        def work():
            try:
                lib = Library(db, sync)
                lib.join(old, lambda i, total, title: self.bus.join_progress.emit(i, total, title))
                self.bus.joined.emit('')
            except Exception as e:
                self.bus.joined.emit(str(e) or type(e).__name__)

        threading.Thread(target=work, daemon=True).start()

    def _on_join_progress(self, i, total, title):
        try:
            self._join_dlg.setMaximum(max(1, total))
            self._join_dlg.setValue(i)
            self._join_dlg.setLabelText('Copying songs into the sync folder…\n%s' % title if title else 'Finishing…')
        except Exception:
            pass

    def _on_joined(self, err):
        try:
            self._join_dlg.close()
        except Exception:
            pass
        if err:
            QMessageBox.warning(self, 'Sync', 'Setting up sync did not finish:\n%s\n\nYou can try again; '
                                'nothing is lost.' % err)
            return
        self.sync = self._join_sync
        self.lib.sync = self.sync
        self._sync_missing = False
        self.settings.setValue('sync_folder', self.sync.root)
        self._last_sync = time.time()
        self._update_sync_btn()
        self.refresh_sidebar()
        self.refresh()
        if self.song:
            self.song = self.lib.get(self.song['id']) or self.song
        self.status('Sync is on. Your other computers can now choose the same folder.')

    def _poll_sync(self):
        if self._sync_missing and not self.sync:
            root = self.settings.value('sync_folder', '')
            if root and os.path.isdir(root):  # the drive came back
                try:
                    self.sync = SyncFolder(root)
                    self.lib.sync = self.sync
                    self._sync_missing = False
                    self._update_sync_btn()
                except OSError:
                    pass
        if not self.sync or self._sync_busy:
            return
        self._sync_busy = True
        sync, db = self.sync, self.db_path

        def work():
            try:
                lib = Library(db, sync)
                n = lib.apply_remote(*sync.changed())
                n += lib.scan_new()
                self.bus.synced.emit(n, '')
            except Exception as e:
                self.bus.synced.emit(0, str(e) or type(e).__name__)

        threading.Thread(target=work, daemon=True).start()

    def _on_synced(self, n, err):
        self._sync_busy = False
        if err:
            self.statusBar().showMessage('Sync problem: ' + err, 5000)
            return
        self._last_sync = time.time()
        self._update_sync_btn()
        if n:
            self.refresh_sidebar()
            self.refresh()
            if self.song:
                fresh = self.lib.get(self.song['id'])
                if fresh:
                    self.song = fresh
                    self._update_title()
            self._queue_analysis()

    # ---------- updates ----------
    def check_updates(self, manual=True):
        if self.update_rel and manual:
            self._offer_update(self.update_rel)
            return
        if manual:
            self.status('Checking for updates…')

        def work():
            try:
                rel = updater.latest_release()
                if updater.is_newer(rel.get('tag_name', '')):
                    rel['_plan'] = updater.plan(rel)
                self.bus.update_info.emit(rel, '', manual)
            except Exception as e:
                self.bus.update_info.emit(None, str(e) or type(e).__name__, manual)

        threading.Thread(target=work, daemon=True).start()

    def _on_update_info(self, rel, err, manual):
        if err:
            if manual:
                QMessageBox.information(self, 'Updates', 'Could not check for updates.\n\n' + err)
            return
        self.settings.setValue('update_check', time.time())
        tag = rel.get('tag_name', '')
        if not updater.is_newer(tag):
            if manual:
                QMessageBox.information(self, 'Updates', 'You have the latest version (%s).' % __version__)
            return
        self.update_rel = rel
        self.upd_btn.setText('Update available')
        self.upd_btn.setStyleSheet('background: %s; border-color: %s; color: white;' % (ACC, ACC))
        self.status('Tempo %s is available. Click “Update available” to install it.' % tag.lstrip('v'))
        if manual:
            self._offer_update(rel)

    def _offer_update(self, rel):
        tag = rel.get('tag_name', '').lstrip('v')
        kind = rel.get('_plan') or updater.plan(rel)
        notes = (rel.get('body') or '').strip()
        if len(notes) > 700:
            notes = notes[:700] + '…'
        size = updater.size_of(rel, kind)
        how = {'code': 'A quick update (%s). Tempo restarts by itself in a few seconds.',
               'source': 'Download: %s. Tempo updates itself and restarts.',
               'full': 'This version includes new built-in parts, so the whole app is downloaded (%s). '
                       'Tempo then replaces itself and restarts.'}[kind] % _size(size)
        msg = 'Tempo %s is available (you have %s).\n\n%s%s\n\nYour library is kept. Update now?' % (
            tag, __version__, (notes + '\n\n') if notes else '', how)
        if QMessageBox.question(self, 'Update Tempo', msg) != QMessageBox.Yes:
            return
        dlg = QProgressDialog('Updating to Tempo %s…' % tag, None, 0, 100, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        self._upd_dlg = dlg
        bus = Bus(self)
        bus.progress.connect(lambda f: dlg.setValue(int(f * 100)))
        self._upd_bus = bus

        def work():
            try:
                if kind == 'code':
                    updater.install_code_update(rel, bus.progress.emit)
                    self.bus.update_done.emit('restart', '')
                elif kind == 'source':
                    updater.install_source_update(rel, bus.progress.emit)
                    self.bus.update_done.emit('restart', '')
                else:
                    cmd = updater.prepare_full_update(rel, bus.progress.emit)
                    self.bus.update_done.emit('full:' + json.dumps(cmd), '')
            except Exception as e:
                self.bus.update_done.emit('', str(e) or type(e).__name__)

        threading.Thread(target=work, daemon=True).start()

    def _on_update_done(self, what, err):
        try:
            self._upd_dlg.close()
        except Exception:
            pass
        if err:
            QMessageBox.warning(self, 'Update failed', err + '\n\nYou can also download it from ' + updater.RELEASES)
            return
        self.status('Restarting with the new version…')
        QApplication.processEvents()
        if what.startswith('full:'):
            updater.launch_detached(json.loads(what[5:]))
            self.close()
        elif what == 'restart':
            self.close()
            updater.restart()

    # ---------- beat, tempo and key ----------
    def _analysis_of(self, song):
        try:
            a = json.loads(song.get('analysis') or '{}')
        except ValueError:
            a = {}
        return a if a.get('version') == analysis.VERSION else None

    def _queue_analysis(self):
        for r in self.lib.songs('all'):
            if not self._analysis_of(r) and os.path.exists(r['path']):
                self.analyzer.add(r['id'], r['path'])

    def _apply_analysis(self):
        s = self.song
        a = self._analysis_of(s) if s else None
        if not a:
            self.player.set_beats([], 0, s.get('bpm') if s else None)
            if s:
                self.analyzer.add(s['id'], s['path'], urgent=True)
                self.status('Finding the beat and key of “%s”…' % (s['title'] or 'this song'))
            return
        beats, down = analysis.beats_for(a, s.get('bpm'))
        self.player.set_beats(beats, down, s.get('bpm') or a.get('bpm'))

    def _on_analyzed(self, sid, res, err):
        if not res:
            if self.song and self.song['id'] == sid:
                self.status('Could not find the beat: ' + err)
            return
        s = self.lib.get(sid)
        if not s:
            return
        fields = {'analysis': json.dumps(res)}
        if not s['bpm'] and res.get('bpm'):
            fields['bpm'] = res['bpm']
        if not (s['key'] or '').strip() and res.get('key'):
            fields['key'] = res['key']
        self.lib.update(sid, **fields)
        if self.song and self.song['id'] == sid:
            self.song = self.lib.get(sid)
            self._apply_analysis()
            self._update_title()
            self.status('“%s”: %s, %g BPM' % (self.song['title'] or 'Song', self.song['key'] or '?', self.song['bpm'] or 0))
        self._refresh_later.start()

    def _toggle_click(self, on):
        self.player.set_click(on)
        self.settings.setValue('click', 'true' if on else 'false')
        if on and not len(self.player.beats) and self.song:
            self.status('Still finding the beat… the click starts as soon as it is found.')

    def _set_countin(self, mode):
        self.player.set_countin(mode)
        self.settings.setValue('countin', mode)
        for i, act in enumerate(self.countin_actions):
            act.setChecked(i == mode)
        self.countin_btn.setChecked(mode > 0)
        self.countin_btn.setToolTip(('One bar of clicks before the music starts (off)',
                                     'One bar of clicks before playing',
                                     'One bar of clicks before playing and before every loop repeat')[mode])

    # ---------- status ----------
    def status(self, text):
        self.statusBar().showMessage(text, 8000)

    # ---------- library views ----------
    def refresh_sidebar(self):
        cur = self.view
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        for label, key in (('All songs', 'all'), ('Favorites', 'favorites'), ('Recently played', 'recent')):
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, key)
            self.sidebar.addItem(it)
        hdr = QListWidgetItem('Collections')
        hdr.setFlags(Qt.NoItemFlags)
        hdr.setForeground(QColor(SOFT))
        f = QFont()
        f.setBold(True)
        hdr.setFont(f)
        self.sidebar.addItem(hdr)
        for c in self.lib.collections():
            it = QListWidgetItem('%s   %d' % (c['name'], c['n']))
            it.setData(Qt.UserRole, 'collection:%d' % c['id'])
            it.setToolTip('Drag songs here to add them')
            self.sidebar.addItem(it)
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).data(Qt.UserRole) == cur:
                self.sidebar.setCurrentRow(i)
                break
        else:
            self.sidebar.setCurrentRow(0)
            self.view = 'all'
        self.sidebar.blockSignals(False)

    def _view_changed(self, it, _prev=None):
        if it and it.data(Qt.UserRole):
            self.view = it.data(Qt.UserRole)
            self.refresh()

    def refresh(self):
        rows = self.lib.songs(self.view, self.search.text())
        self.model.playing_id = self.song['id'] if self.song else None
        self.model.set_rows(rows)
        if self.view.startswith('collection:') or self.view == 'recent':
            self.proxy.sort(-1)
        has = bool(rows) or bool(self.search.text()) or self.view != 'all'
        self.table.setVisible(has)
        self.empty.setVisible(not has)

    def _row(self, proxy_idx):
        return self.model.rows[self.proxy.mapToSource(proxy_idx).row()]

    def _selected(self):
        return [self._row(i) for i in self.table.selectionModel().selectedRows()]

    def _table_clicked(self, idx):
        if idx.column() == 0:
            r = self._row(idx)
            self.lib.update(r['id'], favorite=0 if r['favorite'] else 1)
            self.refresh()

    def _table_menu(self, pt):
        rows = self._selected()
        if not rows:
            return
        ids = [r['id'] for r in rows]
        m = QMenu(self)
        m.addAction('Open', lambda: self.open_song(ids[0]))
        if len(rows) == 1:
            m.addAction('Edit details…', lambda: self.edit_song(ids[0]))
        fav = not all(r['favorite'] for r in rows)
        m.addAction('Add to favorites' if fav else 'Remove from favorites',
                    lambda: ([self.lib.update(i, favorite=int(fav)) for i in ids], self.refresh()))
        cm = m.addMenu('Add to collection')
        for c in self.lib.collections():
            cm.addAction(c['name'], lambda cid=c['id']: (self.lib.add_to_collection(cid, ids), self.refresh_sidebar()))
        cm.addSeparator()
        cm.addAction('New collection…', lambda: self.new_collection(ids))
        if self.view.startswith('collection:'):
            cid = int(self.view.split(':')[1])
            m.addAction('Remove from this collection',
                        lambda: (self.lib.remove_from_collection(cid, ids), self.refresh_sidebar(), self.refresh()))
            if len(ids) == 1:
                m.addAction('Move up', lambda: (self.lib.move_in_collection(cid, ids[0], -1), self.refresh()))
                m.addAction('Move down', lambda: (self.lib.move_in_collection(cid, ids[0], 1), self.refresh()))
        m.addSeparator()
        if len(rows) == 1:
            m.addAction('Show file in folder', lambda: reveal(rows[0]['path']))
        m.addAction('Remove from library', lambda: self.remove_songs(ids))
        m.exec(self.table.viewport().mapToGlobal(pt))

    def _sidebar_menu(self, pt):
        it = self.sidebar.itemAt(pt)
        key = it.data(Qt.UserRole) if it else None
        if not key or not str(key).startswith('collection:'):
            return
        cid = int(key.split(':')[1])
        name = it.text().rsplit('   ', 1)[0]
        m = QMenu(self)
        m.addAction('Rename…', lambda: self._rename_collection(cid, name))
        m.addAction('Delete collection', lambda: self._delete_collection(cid, name))
        m.exec(self.sidebar.mapToGlobal(pt))

    def _rename_collection(self, cid, name):
        n, ok = QInputDialog.getText(self, 'Rename collection', 'Name', text=name)
        if ok and n.strip():
            self.lib.rename_collection(cid, n)
            self.refresh_sidebar()

    def _delete_collection(self, cid, name):
        if QMessageBox.question(self, 'Delete collection', 'Delete “%s”? The songs stay in your library.' % name) == QMessageBox.Yes:
            self.lib.delete_collection(cid)
            self.view = 'all'
            self.refresh_sidebar()
            self.refresh()

    def new_collection(self, ids=None):
        n, ok = QInputDialog.getText(self, 'New collection', 'Name (for example a student, a book or an exam)')
        if ok and n.strip():
            cid = self.lib.create_collection(n)
            if ids:
                self.lib.add_to_collection(cid, ids)
            self.refresh_sidebar()

    def edit_song(self, sid):
        s = self.lib.get(sid)
        d = InfoDialog(self, s, self.lib.all_tags())
        if d.exec():
            self.lib.update(sid, **d.values())
            if self.song and self.song['id'] == sid:
                self.song = self.lib.get(sid)
                self._update_title()
                self._apply_analysis()
            self.refresh()

    def remove_songs(self, ids):
        if QMessageBox.question(self, 'Remove from library',
                                'Remove %d song%s from the library? The files on your computer are not deleted%s.'
                                % (len(ids), '' if len(ids) == 1 else 's',
                                   ' (files in the sync folder stay there, and Tempo won\'t add them again)'
                                   if self.sync else '')) == QMessageBox.Yes:
            self.lib.remove(ids)
            self.refresh_sidebar()
            self.refresh()

    # ---------- adding songs ----------
    def add_files(self):
        exts = ' '.join('*' + e for e in sorted(audio.AUDIO_EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, 'Add songs', self.settings.value('lastdir', ''), 'Audio (%s)' % exts)
        if files:
            self.settings.setValue('lastdir', os.path.dirname(files[0]))
            self._add_paths(files)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, 'Add a folder of songs', self.settings.value('lastdir', ''))
        if d:
            self.settings.setValue('lastdir', d)
            self._add_paths([d])

    def _add_paths(self, paths, target=None):
        self.status('Adding songs…')
        db_path = os.path.join(data_dir(), 'library.sqlite')
        target = target or self.view

        sync = self.sync
        if sync:
            self.status('Adding songs and copying them into your sync folder…')

        def work():
            lib = Library(db_path, sync)
            ids = lib.add_paths(paths)
            if target.startswith('collection:') and ids:
                lib.add_to_collection(int(target.split(':')[1]), ids)
            self.bus.added.emit(len(ids))

        threading.Thread(target=work, daemon=True).start()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self._add_paths(paths)

    # ---------- loading ----------
    def open_song(self, sid, autoplay=True):
        s = self.lib.get(sid)
        if not s:
            return
        if not os.path.exists(s['path']):
            QMessageBox.warning(self, 'File not found', 'This file has been moved or deleted:\n' + s['path'])
            return
        self.player.pause()
        self.load_token += 1
        tok = self.load_token
        self.title_lbl.setText(s['title'] or 'Untitled')
        self.sub_lbl.setText('Loading…')
        sr = self.player.sr
        stem_dir = self._stem_dir(sid)
        stem_names = json.loads(s['stems']) if s['stems'] else []

        def work():
            try:
                a = audio.decode(s['path'], sr)
                stems = {}
                for n in stem_names:
                    f = os.path.join(stem_dir, n + '.wav')
                    if os.path.exists(f):
                        stems[n] = audio.decode(f, sr)
                self.bus.loaded.emit(tok, a, stems, audio.peaks(a))
            except Exception as e:
                self.bus.load_failed.emit(tok, str(e))

        self._pending = (s, autoplay)
        threading.Thread(target=work, daemon=True).start()

    def _on_load_failed(self, tok, msg):
        if tok == self.load_token:
            self.sub_lbl.setText('Could not open this file: ' + msg)

    def _on_loaded(self, tok, a, stems, peaks):
        if tok != self.load_token:
            return
        s, autoplay = self._pending
        self.song = s
        self.main_audio = a
        self.stems = stems
        self.player.load(a, stems)
        if s['duration'] is None or abs((s['duration'] or 0) - len(a) / self.player.sr) > 1:
            self.lib.update(s['id'], duration=len(a) / self.player.sr)
        self.wave.set_data(peaks, self.player.duration)
        if not getattr(self, '_keep_settings', False):
            self.set_speed(1.0)
            self._reset_pitch()
            self.set_loop(None, None, False)
        self._keep_settings = False
        self._update_title()
        self._build_stems_ui()
        if self.ly_song != s['id']:
            self._lyrics_for_song()
        self._apply_analysis()
        self.lib.mark_played(s['id'])
        self.refresh()
        resume, self._resume_after = self._resume_after, None
        if resume:
            self.player.seek(resume[0])
            autoplay = resume[1]
        if autoplay:
            if self.loop_on and self.loop_a is not None and not resume:
                self.player.seek(self.loop_a)
            self.player.play()
        self._update_player_ui()

    def _update_title(self):
        s = self.song
        self.title_lbl.setText(s['title'] or 'Untitled')
        bits = [x for x in (s['artist'], s['key'], ('%g BPM' % s['bpm']) if s['bpm'] else '', s['tags']) if x]
        self.sub_lbl.setText('  ·  '.join(bits) or os.path.basename(s['path']))
        self._update_player_ui()

    # ---------- transport ----------
    def toggle(self):
        if not self.song:
            rows = self._selected() or (self.model.rows[:1] if self.model.rows else [])
            if rows:
                self.open_song(rows[0]['id'])
            return
        if self.player.playing:
            self.player.pause()
        else:
            try:
                self.player.play()
            except Exception as e:
                QMessageBox.warning(self, 'Sound problem', 'Could not start the sound output:\n%s' % e)
        self._update_player_ui()

    def seek(self, t):
        self.player.seek(t)
        self.last_pos = t

    def _enter_pressed(self):
        fw = QApplication.focusWidget()
        if isinstance(fw, QLineEdit):  # keep Enter working in the search boxes
            fw.returnPressed.emit()
            return
        if isinstance(fw, QPlainTextEdit):
            fw.insertPlainText('\n')
            return
        if self.song:
            self.seek(0.0)

    def seek_rel(self, d):
        if self.song:
            self.seek(max(0, min(self.player.duration, self.player.position() + d)))

    def set_speed(self, s, from_slider=False):
        s = max(0.25, min(2.0, round(s, 2)))
        self.player.set_speed(s)
        if not from_slider:
            self.speed_sl.blockSignals(True)
            self.speed_sl.setValue(int(round(s * 100)))
            self.speed_sl.blockSignals(False)
        self._update_player_ui()

    def nudge_speed(self, d):
        self.set_speed(round(self.player.speed * 100 + d) / 100)

    def set_pitch(self, semis):
        semis = max(-12.0, min(12.0, round(semis, 2)))
        self.player.set_pitch(semis)
        self._update_player_ui()

    # ---------- loops ----------
    def set_loop(self, a, b, on, jump=False):
        if a is not None and b is not None and b < a:
            a, b = b, a
        if a is not None and b is not None and b - a < 0.2:
            b = None
        self.loop_a, self.loop_b = a, b
        self.loop_on = bool(on and a is not None and b is not None)
        self.loop_count = 0
        self.player.set_loop(a, b) if self.loop_on else self.player.set_loop(None, None)
        if jump and self.loop_on:
            self.seek(a)
        self.wave.set_loop(a, b, self.loop_on)
        self._update_player_ui()

    def set_a(self):
        if self.song:
            self.set_loop(self.player.position(), self.loop_b, self.loop_b is not None)

    def set_b(self):
        if self.song:
            self.set_loop(self.loop_a or 0.0, self.player.position(), True)

    def toggle_loop(self):
        if self.loop_a is None or self.loop_b is None:
            self.status('Set A and B first, or drag across the waveform.')
            self.loop_btn.setChecked(False)
            return
        self.set_loop(self.loop_a, self.loop_b, not self.loop_on)

    # ---------- periodic UI ----------
    def _tick(self):
        p = self.player
        if p.error:
            self.status('Playback stopped: ' + p.error)
            p.error = ''
        pos = p.position()
        if self.loop_on and p.playing and pos < self.last_pos - 0.05:
            self.loop_count += 1
        self.last_pos = pos
        self.wave.set_pos(pos)
        self._tick_lyrics(pos)
        if p.counting_in():
            self.time_lbl.setText('Count-in…')
        else:
            self.time_lbl.setText('%s / %s' % (fmt(pos), fmt(p.duration)))
        if self._shown_playing != p.playing:
            self._update_player_ui()

    def _update_player_ui(self):
        p = self.player
        pct = int(round(p.speed * 100))
        self.speed_lbl.setText('%d%%' % pct)
        for k, b in self.preset_btns.items():
            b.setChecked(k == pct)
        bpm = self.song['bpm'] if self.song else None
        self.bpm_lbl.setText(('%g → %d BPM' % (bpm, round(bpm * p.speed))) if bpm else '')
        semis = p.semis
        whole = self.whole
        self.p_val.setText('%+d' % whole if whole else '0')
        name = INTERVALS[min(12, abs(whole))]
        self.p_name.setText(name if whole == 0 else ('up a ' if whole > 0 else 'down a ') + name)
        self.cents_lbl.setText('%+d ¢' % self.cents.value() if self.cents.value() else '0 ¢')
        self.a_btn.setText('A  ' + fmt(self.loop_a, True) if self.loop_a is not None else 'Set A')
        self.b_btn.setText('B  ' + fmt(self.loop_b, True) if self.loop_b is not None else 'Set B')
        self.loop_btn.setChecked(self.loop_on)
        self.loop_btn.setText('Loop on' if self.loop_on else 'Loop off')
        if self._shown_playing != p.playing:
            self._shown_playing = p.playing
            self.play_btn.setIcon(self.icons['pause' if p.playing else 'play'])
            self.play_btn.setToolTip('Pause (Space)' if p.playing else 'Play (Space)')
        has = self.song is not None
        for w in (self.export_btn, self.back_btn, self.fwd_btn):
            w.setEnabled(has)

    # ---------- instruments (stems) ----------
    def _stem_dir(self, sid):
        if self.sync:
            s = self.lib.get(sid)
            if s and s.get('uid'):
                return self.sync.stems_dir(s['uid'])
        return os.path.join(data_dir(), 'stems', str(sid))

    def _clear_stems_ui(self):
        while self.stems_lay.count():
            it = self.stems_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                lay = it.layout()
                while lay.count():
                    x = lay.takeAt(0)
                    if x.widget():
                        x.widget().deleteLater()

    def _build_stems_ui(self):
        self._clear_stems_ui()
        L = self.stems_lay
        if not self.song:
            L.addWidget(QLabel('Open a song to split it into instruments.', objectName='soft'))
            L.addStretch(1)
            return
        if not self.stems and not addons.installed(data_dir()):
            info = QLabel('Split songs into separate instruments (vocals, drums, bass, piano…), then mute, solo or '
                          'turn down any of them.\n\nThis is an optional add-on (%s download). '
                          'You only need to download it once.' % addons.SIZE_HINT)
            info.setWordWrap(True)
            L.addWidget(info)
            self.addon_btn = QPushButton('Download instrument splitter', objectName='accent',
                                         clicked=self.install_addon)
            L.addWidget(self.addon_btn, 0, Qt.AlignLeft)
            self.addon_bar = QProgressBar()
            self.addon_bar.setRange(0, 100)
            self.addon_bar.hide()
            L.addWidget(self.addon_bar)
            self.stem_status = QLabel('', objectName='soft')
            self.stem_status.setWordWrap(True)
            L.addWidget(self.stem_status)
            L.addStretch(1)
            return
        if not self.stems:
            sp = self._split
            if sp and sp['sid'] == self.song['id']:
                self.split_stage = QLabel('')
                self.split_stage.setStyleSheet('font-weight: 600;')
                self.split_stage.setWordWrap(True)
                L.addWidget(self.split_stage)
                self.split_bar = QProgressBar()
                self.split_bar.setRange(0, 100)
                self.split_bar.setFormat('%p%')
                self.split_bar.setMinimumHeight(22)
                L.addWidget(self.split_bar)
                self.split_dl = QProgressBar()
                self.split_dl.setRange(0, 100)
                self.split_dl.setFormat('Downloading the model (first time only)  %p%')
                self.split_dl.setMaximumHeight(16)
                self.split_dl.hide()
                L.addWidget(self.split_dl)
                row = QHBoxLayout()
                self.split_time = QLabel('', objectName='soft')
                row.addWidget(self.split_time, 1)
                row.addWidget(QPushButton('Cancel', clicked=self.cancel_split))
                L.addLayout(row)
                self.stem_status = QLabel('You can keep practising while it works.', objectName='soft')
                self.stem_status.setWordWrap(True)
                L.addWidget(self.stem_status)
                L.addStretch(1)
                self._render_split()
                return
            info = QLabel('Split this song into separate instruments, then mute, solo or turn down any of them. '
                          'Runs on your computer and takes a few minutes per song.')
            info.setWordWrap(True)
            L.addWidget(info)
            self.stem_model = QComboBox()
            self.stem_model.addItem('4 parts: vocals, drums, bass, other', 'htdemucs')
            self.stem_model.addItem('6 parts: adds piano and guitar', 'htdemucs_6s')
            L.addWidget(self.stem_model)
            b = QPushButton('Split into instruments', objectName='accent', clicked=self.split_stems)
            L.addWidget(b)
            if addons.outdated(data_dir()) and not sp:
                upd = QPushButton('Update the splitter (shows step-by-step progress)', clicked=self.update_addon)
                upd.setToolTip('Downloads the newest instrument splitter, %s.' % addons.SIZE_HINT)
                L.addWidget(upd, 0, Qt.AlignLeft)
            self.stem_status = QLabel('', objectName='soft')
            self.stem_status.setWordWrap(True)
            if sp:
                b.setEnabled(False)
                self.stem_status.setText('Another song is being split right now (%d%%). '
                                         'You can split this one when it is done.' % sp['pct'])
            L.addWidget(self.stem_status)
            L.addStretch(1)
            return
        self.use_stems = QCheckBox('Play the separated instruments')
        self.use_stems.setChecked(self.player.src.use_stems)
        self.use_stems.toggled.connect(self._apply_mix)
        L.addWidget(self.use_stems)
        self.stem_rows = {}
        grid = QGridLayout()
        for i, name in enumerate(self.stems):
            lab = QLabel(STEM_LABELS.get(name, name.title()))
            mute = QPushButton('Mute', checkable=True)
            solo = QPushButton('Solo', checkable=True)
            sl = QSlider(Qt.Horizontal, minimum=0, maximum=150, value=int(self.player.src.gains.get(name, 1) * 100))
            for wdg in (mute, solo):
                wdg.toggled.connect(self._stem_touched)
            sl.valueChanged.connect(self._stem_touched)
            grid.addWidget(lab, i, 0)
            grid.addWidget(mute, i, 1)
            grid.addWidget(solo, i, 2)
            grid.addWidget(sl, i, 3)
            self.stem_rows[name] = (mute, solo, sl)
        grid.setColumnStretch(3, 1)
        L.addLayout(grid)
        again = QPushButton('Delete separated parts', clicked=self._delete_stems)
        L.addWidget(again, 0, Qt.AlignLeft)
        L.addStretch(1)

    def _stem_touched(self, *_):
        if not self.use_stems.isChecked():
            self.use_stems.blockSignals(True)
            self.use_stems.setChecked(True)
            self.use_stems.blockSignals(False)
        self._apply_mix()

    def _apply_mix(self, *_):
        solos = [n for n, (m, s, sl) in self.stem_rows.items() if s.isChecked()]
        gains = {}
        for n, (m, s, sl) in self.stem_rows.items():
            g = sl.value() / 100
            if m.isChecked() or (solos and n not in solos):
                g = 0.0
            gains[n] = g
        self.player.set_mix(self.use_stems.isChecked(), gains)

    def _delete_stems(self):
        if QMessageBox.question(self, 'Delete separated parts', 'Delete the separated instruments for this song? '
                                'You can split it again later.') != QMessageBox.Yes:
            return
        d = self._stem_dir(self.song['id'])
        for f in os.listdir(d) if os.path.isdir(d) else []:
            try:
                os.remove(os.path.join(d, f))
            except OSError:
                pass
        self.lib.update(self.song['id'], stems='')
        self.stems = {}
        self.player.set_stems({})
        self._build_stems_ui()

    def install_addon(self):
        if getattr(self, '_addon_busy', False):
            return
        self._addon_busy = True
        self.addon_btn.setEnabled(False)
        self.addon_bar.show()
        self.addon_bar.setValue(0)
        dd = data_dir()

        def work():
            try:
                addons.install(dd, lambda f, t: self.bus.addon_progress.emit(f, t))
                self.bus.addon_done.emit('')
            except Exception as e:
                self.bus.addon_done.emit(str(e) or type(e).__name__)

        threading.Thread(target=work, daemon=True).start()

    def update_addon(self):
        addons.remove(data_dir())
        self._build_stems_ui()
        self.install_addon()

    def _on_addon_progress(self, f, text):
        try:
            self.addon_bar.setValue(int(f * 100))
            self.stem_status.setText(text)
        except Exception:
            pass

    def _on_addon_done(self, err):
        self._addon_busy = False
        if err:
            try:
                self.addon_btn.setEnabled(True)
                self.addon_bar.hide()
                self.stem_status.setText('Download failed. ' + err)
            except Exception:
                pass
            return
        self.status('Instrument splitter installed')
        self._build_stems_ui()

    SPLIT_STAGES = 5

    def split_stems(self):
        if not addons.installed(data_dir()):
            self._build_stems_ui()
            return
        if self.stem_proc:
            return
        sid = self.song['id']
        out = self._stem_dir(sid)
        model = self.stem_model.currentData()
        prog = os.path.join(data_dir(), 'stems-progress-%d.txt' % sid)
        try:
            os.remove(prog)
        except OSError:
            pass
        proc = QProcess(self)
        program, args = addons.command(data_dir(), [self.song['path'], out, model, prog])
        proc.setProgram(program)
        proc.setArguments(args)
        proc.setWorkingDirectory(os.path.dirname(program) if updater.FROZEN else updater.APP_DIR)
        proc.setStandardOutputFile(QProcess.nullDevice())
        proc.setStandardErrorFile(QProcess.nullDevice())
        self._split = {'sid': sid, 'title': self.song['title'] or 'song', 'stage': 1,
                       'text': 'Starting the separation engine', 'pct': 0, 'download': None,
                       't0': time.time(), 'sep_t0': None, 'sep_p0': 0, 'result': None, 'off': 0,
                       'cancelled': False}
        sp = self._split

        def read():
            try:
                with open(prog, 'r', encoding='utf-8') as f:
                    f.seek(sp['off'])
                    chunk = f.read()
                    sp['off'] = f.tell()
            except OSError:
                chunk = ''
            for line in chunk.splitlines():
                self._split_line(sp, line.strip())
            self._render_split()

        def done(code, _status):
            poll.stop()
            read()
            self.stem_proc = None
            self._split = None
            res = sp['result']
            if isinstance(res, list):
                self.lib.update(sid, stems=json.dumps(res))
                mins = (time.time() - sp['t0']) / 60
                self.status('“%s” split into %d instruments in %d min' % (sp['title'], len(res), round(mins) or 1))
                if self.song and self.song['id'] == sid:
                    self._resume_after = (self.player.position(), self.player.playing)
                    self._keep_settings = True
                    self.open_song(sid, autoplay=False)
            else:
                if self.song and self.song['id'] == sid:
                    self._build_stems_ui()
                msg = 'Splitting was cancelled.' if sp['cancelled'] else \
                    'Separation failed. %s' % (res or 'Exit code %d' % code)
                self._stem_msg(msg)
            try:
                os.remove(prog)
            except OSError:
                pass

        poll = QTimer(self, interval=400, timeout=read)
        poll.start()
        proc.finished.connect(done)
        self.stem_proc = proc
        proc.start()
        self._build_stems_ui()

    def _split_line(self, sp, line):
        if line.startswith('STAGE '):
            parts = line.split(' ', 2)
            sp['stage'] = int(parts[1])
            sp['text'] = parts[2] if len(parts) > 2 else ''
            sp['download'] = None
            if sp['stage'] == 4:
                sp['sep_t0'], sp['sep_p0'] = time.time(), sp['pct']
        elif line.startswith('STATUS '):  # splitter add-on from Tempo 1.3
            sp['text'] = line[7:]
        elif line.startswith('PROGRESS '):
            try:
                sp['pct'] = max(sp['pct'], min(100, int(float(line.split()[1]))))
            except ValueError:
                pass
            if sp['sep_t0'] is None and sp['pct'] > 5 and 'Separat' in sp['text']:
                sp['sep_t0'], sp['sep_p0'] = time.time(), sp['pct']
        elif line.startswith('DOWNLOAD '):
            try:
                sp['download'] = int(float(line.split()[1]))
            except ValueError:
                pass
        elif line.startswith('DONE '):
            sp['result'] = json.loads(line[5:])
        elif line.startswith('ERROR'):
            sp['result'] = line[6:]

    def _render_split(self):
        sp = self._split
        if not sp:
            return
        elapsed = time.time() - sp['t0']
        eta = ''
        if sp['sep_t0'] and sp['pct'] < 96:
            done_frac = (sp['pct'] - sp['sep_p0']) / max(1, 100 - sp['sep_p0'])
            run = time.time() - sp['sep_t0']
            if done_frac > 0.04 and run > 5:
                left = run * (1 - done_frac) / done_frac
                eta = ' · about %s left' % (('%d min' % round(left / 60)) if left >= 90 else '%d s' % max(5, round(left / 5) * 5))
        try:
            self.split_stage.setText('Step %d of %d: %s…' % (sp['stage'], self.SPLIT_STAGES, sp['text']))
            self.split_bar.setValue(sp['pct'])
            self.split_time.setText('%s elapsed%s' % (fmt(elapsed), eta))
            if sp['download'] is not None and sp['download'] < 100:
                self.split_dl.show()
                self.split_dl.setValue(sp['download'])
            else:
                self.split_dl.hide()
        except (AttributeError, RuntimeError):
            pass
        if not (self.song and self.song['id'] == sp['sid']):
            self.status('Splitting “%s”: %d%%%s' % (sp['title'], sp['pct'], eta))

    def cancel_split(self):
        if self.stem_proc and self._split:
            if QMessageBox.question(self, 'Cancel splitting', 'Stop splitting this song?') == QMessageBox.Yes:
                self._split['cancelled'] = True
                self.stem_proc.kill()

    def _stem_msg(self, text):
        try:
            self.stem_status.setText(text)
        except Exception:
            pass
        self.status(text)

    # ---------- export ----------
    def export(self):
        if not self.song:
            return
        sp, semis = self.player.speed, self.player.semis
        use_loop = False
        if self.loop_a is not None and self.loop_b is not None:
            r = QMessageBox.question(self, 'Save practice track', 'Save only the loop (%s–%s)?\nChoose No to save the whole song.'
                                     % (fmt(self.loop_a), fmt(self.loop_b)), QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                return
            use_loop = r == QMessageBox.Yes
        name = '%s - %d%%%s%s' % (self.song['title'] or 'Song', round(sp * 100),
                                  (' %+gst' % round(semis, 2)) if semis else '', ' loop' if use_loop else '')
        name = ''.join('_' if c in '\\/:*?"<>|' else c for c in name)
        start = os.path.join(self.settings.value('exportdir', os.path.expanduser('~')), name + '.mp3')
        path, _ = QFileDialog.getSaveFileName(self, 'Save practice track', start,
                                              'MP3 (*.mp3);;WAV, full quality (*.wav);;M4A (*.m4a);;FLAC (*.flac)')
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += '.mp3'
        self.settings.setValue('exportdir', os.path.dirname(path))
        a, b = (self.loop_a, self.loop_b) if use_loop else (0.0, self.player.duration)
        dlg = QProgressDialog('Rendering at %d%%…' % round(sp * 100), 'Cancel', 0, 100, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        cancel = {'v': False}
        dlg.canceled.connect(lambda: cancel.__setitem__('v', True))
        src = self.player.src
        stems, gains, use = dict(src.stems), dict(src.gains), src.use_stems
        sr, main = self.player.sr, self.main_audio
        bus = Bus(self)
        bus.progress.connect(lambda f: dlg.setValue(int(f * 100)))

        def finished(p, err):
            dlg.close()
            if err:
                QMessageBox.warning(self, 'Could not save', err)
            elif p:
                self.status('Saved ' + p)
                reveal(p)

        bus.exported.connect(finished)

        def work():
            try:
                out = render_offline(main, stems, gains, use, sr, sp, semis, a, b,
                                     progress=lambda f: bus.progress.emit(f * 0.95), cancelled=lambda: cancel['v'])
                if out is None:
                    bus.exported.emit('', '')
                    return
                audio.export(path, out, sr)
                bus.exported.emit(path, '')
            except Exception as e:
                bus.exported.emit('', str(e))

        self._export_bus = bus
        threading.Thread(target=work, daemon=True).start()

    # ---------- shutdown ----------
    def closeEvent(self, e):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('splitter', self.vsplit.saveState())
        if self.stem_proc:
            self.stem_proc.kill()
        self.player.close()
        super().closeEvent(e)


def main():
    QApplication.setApplicationName(APP)
    QApplication.setOrganizationName(APP)
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create('Fusion'))
    pal = QPalette()
    for role, col in ((QPalette.Window, BG), (QPalette.Base, '#121110'), (QPalette.AlternateBase, '#181615'),
                      (QPalette.Text, INK), (QPalette.WindowText, INK), (QPalette.Button, '#2a2624'),
                      (QPalette.ButtonText, INK), (QPalette.Highlight, ACC), (QPalette.HighlightedText, '#ffffff'),
                      (QPalette.ToolTipBase, PANEL), (QPalette.ToolTipText, INK), (QPalette.PlaceholderText, '#7d756a')):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
    try:
        w = MainWindow()
    except Exception as e:
        QMessageBox.critical(None, APP, 'Tempo could not start:\n\n%s\n\nTry running the installer again.' % e)
        raise
    w.show()
    sys.exit(app.exec())

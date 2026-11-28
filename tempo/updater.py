"""Check GitHub for a newer Tempo, install it and restart.

* Stand-alone app, quick update: when the new version was built with the same libraries
  (same "runtime" fingerprint), only Tempo's own code is downloaded (Tempo-code.zip, a few
  hundred KB) into the data folder; run_tempo.py uses it from the next start.
* Stand-alone app, full update: otherwise the whole app is downloaded, and a small script
  waits for Tempo to quit, replaces the app and starts the new one.
* Python install: Tempo-source.zip is copied over the program folder; packages are only
  reinstalled when requirements.txt changed.
"""
import json
import os
import platform
import re
import shutil
import ssl
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

from . import __version__

REPO = 'ZystemProd/Tempo'
RELEASES = 'https://github.com/%s/releases' % REPO
FROZEN = bool(getattr(sys, 'frozen', False))
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url, accept='application/octet-stream', timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'Tempo/' + __version__, 'Accept': accept})
    return urllib.request.urlopen(req, timeout=timeout, context=_ctx())


def version_tuple(s):
    nums = [int(x) for x in re.findall(r'\d+', str(s))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(tag):
    return version_tuple(tag) > version_tuple(__version__)


def latest_release():
    try:
        with _open('https://api.github.com/repos/%s/releases/latest' % REPO, 'application/vnd.github+json') as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError('No published version was found. The GitHub repository must be public '
                               'and have at least one release.')
        raise


def _asset(rel, name):
    for a in rel.get('assets', []):
        if a.get('name') == name:
            return a.get('browser_download_url')
    return None


def data_dir():
    if os.environ.get('TEMPO_DATA_DIR'):
        return os.environ['TEMPO_DATA_DIR']
    if sys.platform == 'win32':
        return os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'Tempo', 'Tempo')
    if sys.platform == 'darwin':
        return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Tempo', 'Tempo')
    return os.path.join(os.path.expanduser('~'), '.local', 'share', 'Tempo', 'Tempo')


def runtime():
    """Fingerprint of the built-in libraries of this stand-alone app (None for the Python version)."""
    if not FROZEN:
        return None
    try:
        with open(os.path.join(getattr(sys, '_MEIPASS', ''), 'tempo_runtime.txt')) as f:
            return f.read().strip()
    except OSError:
        return None


def plan(rel):
    """'source', 'code' (quick, code only) or 'full' (whole app)."""
    if not FROZEN:
        return 'source'
    url = _asset(rel, 'Tempo-update.json')
    mine = runtime()
    if url and mine and _asset(rel, 'Tempo-code.zip'):
        try:
            with _open(url) as r:
                info = json.loads(r.read().decode('utf-8'))
            if info.get('runtime') == mine:
                return 'code'
        except Exception:
            pass
    return 'full'


def size_of(rel, kind):
    name = {'code': 'Tempo-code.zip', 'source': 'Tempo-source.zip', 'full': app_asset_name()}[kind]
    for a in rel.get('assets', []):
        if a.get('name') == name:
            return a.get('size') or 0
    return 0


def install_code_update(rel, progress=None):
    ver = rel.get('tag_name', '').lstrip('v')
    base = os.path.join(data_dir(), 'code')
    os.makedirs(base, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='tempo-code-', dir=base)
    try:
        zp = os.path.join(tmp, 'code.zip')
        _download(_asset(rel, 'Tempo-code.zip'), zp, progress)
        out = os.path.join(tmp, 'x')
        with zipfile.ZipFile(zp) as z:
            z.extractall(out)
        if not os.path.isfile(os.path.join(out, 'tempo', '__init__.py')):
            raise RuntimeError('The downloaded update looks incomplete.')
        dest = os.path.join(base, ver)
        shutil.rmtree(dest, ignore_errors=True)
        os.replace(out, dest)
        with open(os.path.join(base, 'active.json.tmp'), 'w') as f:
            json.dump({'version': ver, 'runtime': runtime()}, f)
        os.replace(os.path.join(base, 'active.json.tmp'), os.path.join(base, 'active.json'))
        running = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        for name in os.listdir(base):  # tidy up older code updates
            path = os.path.join(base, name)
            if os.path.isdir(path) and name not in (ver, running) and not name.startswith('tempo-code-'):
                shutil.rmtree(path, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _app_location():
    """The installed app: the Tempo.app bundle on Mac, the folder with Tempo.exe on Windows."""
    exe = os.path.abspath(sys.executable)
    if sys.platform == 'darwin':
        p = exe
        while p and not p.endswith('.app'):
            p = os.path.dirname(p)
            if p in ('/', ''):
                return None
        return p
    return os.path.dirname(exe)


def prepare_full_update(rel, progress=None):
    """Download and unpack the new app, and write the script that swaps it in after Tempo quits.
    Returns the command to start once the window has closed."""
    app = _app_location()
    if not app or not os.access(os.path.dirname(app), os.W_OK):
        raise RuntimeError('Tempo can\'t replace itself in this folder. Download the new version from ' + RELEASES)
    url = _asset(rel, app_asset_name())
    if not url:
        raise RuntimeError('This release has no %s yet. Try again in a few minutes.' % app_asset_name())
    tmp = tempfile.mkdtemp(prefix='tempo-update-')
    zp = os.path.join(tmp, 'app.zip')
    _download(url, zp, (lambda f: progress(f * 0.9)) if progress else None)
    new = os.path.join(tmp, 'new')
    os.makedirs(new)
    if sys.platform == 'darwin':
        subprocess.run(['ditto', '-x', '-k', zp, new], check=True)
        src = os.path.join(new, 'Tempo.app')
        script = os.path.join(tmp, 'swap.sh')
        with open(script, 'w') as f:
            f.write('#!/bin/sh\n'
                    'while kill -0 %d 2>/dev/null; do sleep 0.5; done\n'
                    'rm -rf "%s.old" && mv "%s" "%s.old" && ditto "%s" "%s" && rm -rf "%s.old"\n'
                    'xattr -dr com.apple.quarantine "%s" 2>/dev/null\n'
                    'open "%s"\n'
                    'rm -rf "%s"\n' % (os.getpid(), app, app, app, src, app, app, app, app, tmp))
        cmd = ['/bin/sh', script]
    else:
        with zipfile.ZipFile(zp) as z:
            z.extractall(new)
        src = os.path.join(new, 'Tempo')
        script = os.path.join(tmp, 'swap.bat')
        with open(script, 'w') as f:
            f.write('@echo off\r\n'
                    ':wait\r\n'
                    'tasklist /FI "PID eq %d" 2>NUL | find "%d" >NUL && (timeout /t 1 /nobreak >NUL & goto wait)\r\n'
                    'robocopy "%s" "%s" /MIR /R:5 /W:1 /XF tempo-log.txt >NUL\r\n'
                    'start "" "%s"\r\n'
                    'rmdir /s /q "%s"\r\n' % (os.getpid(), os.getpid(), src, app,
                                                 os.path.join(app, 'Tempo.exe'), tmp))
        cmd = ['cmd', '/c', script]
    if not os.path.exists(src):
        raise RuntimeError('The downloaded app looks incomplete.')
    if progress:
        progress(1.0)
    return cmd


def launch_detached(cmd):
    if sys.platform == 'win32':
        subprocess.Popen(cmd, creationflags=0x00000008 | 0x00000200 | 0x08000000)
    else:
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _mac_intel():
    return sys.platform == 'darwin' and platform.machine() == 'x86_64'


def app_asset_name():
    if sys.platform == 'win32':
        return 'Tempo-Windows.zip'
    return 'Tempo-Mac-Intel.zip' if _mac_intel() else 'Tempo-Mac.zip'


def _download(url, dest, progress=None):
    with _open(url, timeout=60) as r, open(dest, 'wb') as f:
        total = int(r.headers.get('Content-Length') or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)


def install_source_update(rel, progress=None):
    url = _asset(rel, 'Tempo-source.zip') or rel.get('zipball_url')
    if not url:
        raise RuntimeError('The release has no Tempo-source.zip.')
    tmp = tempfile.mkdtemp(prefix='tempo-update-')
    try:
        zp = os.path.join(tmp, 'update.zip')
        _download(url, zp, (lambda f: progress(f * 0.6)) if progress else None)
        out = os.path.join(tmp, 'x')
        with zipfile.ZipFile(zp) as z:
            z.extractall(out)
        root = None
        for dp, dirs, files in os.walk(out):
            if 'run_tempo.py' in files and os.path.isdir(os.path.join(dp, 'tempo')):
                root = dp
                break
        if not root:
            raise RuntimeError('The downloaded update looks incomplete.')
        req = os.path.join(APP_DIR, 'requirements.txt')
        try:
            with open(req, encoding='utf-8') as f:
                old_req = f.read()
        except OSError:
            old_req = None
        skip = {'.venv', '.git', '__pycache__', '.github'}
        for dp, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in skip]
            rel_dir = os.path.relpath(dp, root)
            target_dir = os.path.normpath(os.path.join(APP_DIR, rel_dir))
            os.makedirs(target_dir, exist_ok=True)
            for f in files:
                dst = os.path.join(target_dir, f)
                shutil.copy2(os.path.join(dp, f), dst)
                if f.endswith('.command'):
                    os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if progress:
            progress(0.7)
        with open(req, encoding='utf-8') as f:
            if f.read() == old_req:  # same packages as before: nothing to install
                if progress:
                    progress(1.0)
                return
        py = sys.executable
        extra = ['-c', os.path.join(APP_DIR, 'constraints-mac-intel.txt')] if _mac_intel() else []
        r = subprocess.run([py, '-m', 'pip', 'install', '-q', '-r', req] + extra, capture_output=True,
                           creationflags=_NO_WINDOW)
        if r.returncode != 0:
            raise RuntimeError('Updating packages failed:\n' + r.stderr.decode('utf-8', 'replace')[-800:])
        if progress:
            progress(0.9)
        subprocess.run([py, '-m', 'pip', 'install', '-q', 'pylibrb'], capture_output=True, creationflags=_NO_WINDOW)
        if progress:
            progress(1.0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def download_app_update(rel, progress=None):
    name = app_asset_name()
    url = _asset(rel, name)
    if not url:
        raise RuntimeError('This release has no %s yet. Try again later, or get it from %s' % (name, RELEASES))
    dl = os.path.join(os.path.expanduser('~'), 'Downloads')
    os.makedirs(dl, exist_ok=True)
    dest = os.path.join(dl, name.replace('.zip', '-%s.zip' % rel.get('tag_name', 'new')))
    _download(url, dest, progress)
    return dest


def restart():
    """Start a fresh copy of Tempo. Returns True if started."""
    if FROZEN:
        if sys.platform == 'darwin' and _app_location():
            launch_detached(['/bin/sh', '-c', 'sleep 1; open -n "%s"' % _app_location()])
        else:
            launch_detached([sys.executable])
        return True
    args = [sys.executable, os.path.join(APP_DIR, 'run_tempo.py')]
    if sys.platform == 'win32':
        subprocess.Popen(args, cwd=APP_DIR, creationflags=0x00000008 | 0x00000200)
    else:
        subprocess.Popen(args, cwd=APP_DIR, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

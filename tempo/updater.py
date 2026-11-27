"""Check GitHub for a newer Tempo and install it.

* Python install (run with the install scripts): downloads Tempo-source.zip from the
  latest release, copies it over the program folder (keeping .venv and your library,
  which lives elsewhere), updates packages, then restarts.
* Stand-alone app (built by GitHub Actions): downloads the new app to Downloads.
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
        py = sys.executable
        req = os.path.join(APP_DIR, 'requirements.txt')
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
    """Start a fresh copy of Tempo (Python install only). Returns True if started."""
    if FROZEN:
        return False
    args = [sys.executable, os.path.join(APP_DIR, 'run_tempo.py')]
    if sys.platform == 'win32':
        subprocess.Popen(args, cwd=APP_DIR, creationflags=0x00000008 | 0x00000200)
    else:
        subprocess.Popen(args, cwd=APP_DIR, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

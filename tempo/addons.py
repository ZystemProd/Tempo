"""The optional instrument-splitting add-on.

* Stand-alone app: downloads Tempo-Splitter-<platform>.zip from the GitHub release that
  matches this version and unpacks it into Tempo's data folder.
* Python version: installs Demucs into Tempo's own Python environment with pip.
"""
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile

from . import __version__, updater

_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0
FROZEN = updater.FROZEN
SIZE_HINT = 'about 200–300 MB'


def _mac_intel():
    return sys.platform == 'darwin' and platform.machine() == 'x86_64'


def asset_name():
    if sys.platform == 'win32':
        return 'Tempo-Splitter-Windows.zip'
    return 'Tempo-Splitter-Mac-Intel.zip' if _mac_intel() else 'Tempo-Splitter-Mac.zip'


def _frozen_dir(data_dir):
    return os.path.join(data_dir, 'splitter')


def _frozen_exe(data_dir):
    name = 'TempoSplitter.exe' if sys.platform == 'win32' else 'TempoSplitter'
    return os.path.join(_frozen_dir(data_dir), 'TempoSplitter', name)


def installed(data_dir):
    if FROZEN:
        return os.path.isfile(_frozen_exe(data_dir))
    return importlib.util.find_spec('demucs') is not None


def command(data_dir, args):
    """(program, arguments) that run a separation with the worker arguments `args`."""
    if FROZEN:
        return _frozen_exe(data_dir), list(args)
    return sys.executable, [os.path.join(updater.APP_DIR, 'run_tempo.py'), '--stems-worker'] + list(args)


def _release():
    """The release matching this version (so the add-on fits the app), else the latest."""
    import json
    try:
        with updater._open('https://api.github.com/repos/%s/releases/tags/v%s' % (updater.REPO, __version__),
                           'application/vnd.github+json') as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception:
        return updater.latest_release()


def install(data_dir, progress=None):
    """Download and set up the add-on. progress(fraction, text). Raises on failure."""
    if FROZEN:
        _install_frozen(data_dir, progress)
    else:
        _install_pip(progress)


def _install_frozen(data_dir, progress):
    rel = _release()
    name = asset_name()
    url = updater._asset(rel, name)
    if not url:
        raise RuntimeError('The add-on (%s) is not available for this version yet. Try again in a while.' % name)
    tmp = tempfile.mkdtemp(prefix='tempo-addon-')
    try:
        zp = os.path.join(tmp, name)
        if progress:
            progress(0.0, 'Downloading the instrument splitter…')
        updater._download(url, zp, (lambda f: progress(f * 0.85, 'Downloading the instrument splitter…')) if progress else None)
        if progress:
            progress(0.88, 'Unpacking…')
        dest = _frozen_dir(data_dir)
        new = dest + '.new'
        shutil.rmtree(new, ignore_errors=True)
        os.makedirs(new)
        if sys.platform == 'darwin':  # ditto keeps permissions and symlinks
            subprocess.run(['ditto', '-x', '-k', zp, new], check=True)
        else:
            with zipfile.ZipFile(zp) as z:
                z.extractall(new)
        if not os.path.isdir(os.path.join(new, 'TempoSplitter')):
            raise RuntimeError('The downloaded add-on looks incomplete.')
        shutil.rmtree(dest, ignore_errors=True)
        os.replace(new, dest)
        exe = _frozen_exe(data_dir)
        if sys.platform != 'win32':
            os.chmod(exe, 0o755)
        if sys.platform == 'darwin':
            try:
                subprocess.run(['xattr', '-dr', 'com.apple.quarantine', dest], capture_output=True)
            except OSError:
                pass
        if progress:
            progress(1.0, 'Done')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _install_pip(progress):
    if progress:
        progress(0.05, 'Installing the separation engine (this can take several minutes)…')
    args = [sys.executable, '-m', 'pip', 'install', '-r', os.path.join(updater.APP_DIR, 'requirements-splitter.txt')]
    if _mac_intel():
        args += ['-c', os.path.join(updater.APP_DIR, 'constraints-mac-intel.txt')]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         creationflags=_NO_WINDOW)
    tail = []
    steps = 0
    for line in p.stdout:
        line = line.strip()
        tail = (tail + [line])[-15:]
        if line.startswith(('Collecting', 'Downloading', 'Installing')):
            steps += 1
            if progress:
                progress(min(0.95, 0.05 + steps * 0.02), line[:90])
    if p.wait() != 0:
        raise RuntimeError('Installing the separation engine failed:\n' + '\n'.join(tail))
    importlib.invalidate_caches()
    if progress:
        progress(1.0, 'Done')


def remove(data_dir):
    if FROZEN:
        shutil.rmtree(_frozen_dir(data_dir), ignore_errors=True)

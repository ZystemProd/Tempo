"""Start Tempo. Errors are written to tempo-log.txt.

`--stems-worker ...` runs instrument separation instead of the window (used by Tempo itself).
`--print-version FILE` writes the version that would run, then exits (used by the build checks).

In the stand-alone app, a small code update downloaded by the updater (data folder/code/<version>)
is used instead of the built-in code when it is newer and made for the same built-in libraries.
"""
import importlib.machinery
import json
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _data_dir():
    if os.environ.get('TEMPO_DATA_DIR'):
        return os.environ['TEMPO_DATA_DIR']
    if sys.platform == 'win32':
        return os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'Tempo', 'Tempo')
    if sys.platform == 'darwin':
        return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Tempo', 'Tempo')
    return os.path.join(os.path.expanduser('~'), '.local', 'share', 'Tempo', 'Tempo')


def _vt(v):
    return tuple(int(x) for x in re.findall(r'\d+', str(v))[:3])


class _CodeUpdate:
    """Import finder that loads the 'tempo' package from a downloaded code update."""

    def __init__(self, root):
        self.root = root

    def find_spec(self, name, path=None, target=None):
        if name == 'tempo':
            return importlib.machinery.PathFinder.find_spec(name, [self.root])
        if name.startswith('tempo.'):
            return importlib.machinery.PathFinder.find_spec(name, [os.path.join(self.root, 'tempo')])
        return None


def _use_code_update():
    if not getattr(sys, 'frozen', False):
        return
    try:
        base = getattr(sys, '_MEIPASS', HERE)
        with open(os.path.join(base, 'tempo_runtime.txt')) as f:
            runtime = f.read().strip()
        with open(os.path.join(base, 'tempo_version.txt')) as f:
            bundled = f.read().strip()
        with open(os.path.join(_data_dir(), 'code', 'active.json')) as f:
            active = json.load(f)
        root = os.path.join(_data_dir(), 'code', active['version'])
        if (active.get('runtime') == runtime and _vt(active['version']) > _vt(bundled)
                and os.path.isfile(os.path.join(root, 'tempo', '__init__.py'))):
            sys.meta_path.insert(0, _CodeUpdate(root))
    except Exception:
        pass  # no (usable) code update: run the built-in code


_use_code_update()

if len(sys.argv) > 2 and sys.argv[1] == '--print-version':
    import tempo
    with open(sys.argv[2], 'w') as f:
        f.write('%s %s' % (tempo.__version__, tempo.__file__))
    sys.exit(0)

if len(sys.argv) > 1 and sys.argv[1] == '--stems-worker':
    from tempo.stems_worker import run
    sys.exit(run(sys.argv[2:]))

if sys.stderr is None or sys.stdout is None:  # pythonw / the stand-alone app have no console
    LOG_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else HERE
    try:
        log = open(os.path.join(LOG_DIR, 'tempo-log.txt'), 'a', encoding='utf-8')
    except OSError:
        log = open(os.path.join(os.path.expanduser('~'), 'tempo-log.txt'), 'a', encoding='utf-8')
    sys.stdout = sys.stderr = log

try:
    from tempo.app import main
except Exception:
    traceback.print_exc()
    raise
main()

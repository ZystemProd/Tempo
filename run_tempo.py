"""Start Tempo. Errors are written to tempo-log.txt next to this file."""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
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

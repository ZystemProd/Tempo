"""Entry point of the TempoSplitter add-on (instrument separation), built separately from the app.

    TempoSplitter <song file> <output folder> <model> <progress file>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tempo.stems_worker import run  # noqa: E402

if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))

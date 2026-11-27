#!/bin/bash
cd "$(dirname "$0")"
echo ""
echo " Installing Tempo. This takes a few minutes the first time."
echo ""
PY=""
for c in python3.13 python3.12 python3.14 \
         /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
         /opt/homebrew/bin/python3.13 /usr/local/bin/python3.13 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if (3,12)<=sys.version_info[:2]<=(3,14) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo " Python 3.13 is needed first."
  echo " 1. On the page that opens, download the Python 3.13 macOS installer and run it."
  echo " 2. Then double-click this file again."
  open "https://www.python.org/downloads/macos/"
  read -p " Press Enter to close."
  exit 1
fi
echo " Using $PY"
"$PY" -m venv .venv || { echo " Could not create Tempo's Python environment."; read -p " Press Enter to close."; exit 1; }
.venv/bin/python -m pip install --upgrade pip
EXTRA=""
if [ "$(.venv/bin/python -c 'import platform; print(platform.machine())')" = "x86_64" ]; then
  EXTRA="-c constraints-mac-intel.txt"
fi
.venv/bin/python -m pip install -r requirements.txt $EXTRA || { echo; echo " Installing failed. Check your internet connection and try again."; read -p " Press Enter to close."; exit 1; }
.venv/bin/python -m pip install pylibrb $EXTRA || echo " Rubber Band could not be installed. Tempo will use its built-in engine."
echo ""
.venv/bin/python -c "from tempo.stretch import rubberband_available as ok, engine_problem as why; print(' Studio engine (Rubber Band R3):', 'ready' if ok() else 'not available (' + why() + ')')"
chmod +x ./*.command 2>/dev/null
xattr -dr com.apple.quarantine . 2>/dev/null
echo ""
echo " Done! Start Tempo with \"Start Tempo (Mac).command\"."
read -p " Press Enter to close."

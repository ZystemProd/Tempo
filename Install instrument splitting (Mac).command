#!/bin/bash
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Please run \"Install Tempo (Mac).command\" first."
  read -p "Press Enter to close."
  exit 1
fi
echo ""
echo " Installing instrument splitting (Demucs). This downloads about 1-2 GB."
echo ""
.venv/bin/python -m pip install demucs certifi || { echo; echo " Installing failed. Check your internet connection and try again."; read -p " Press Enter to close."; exit 1; }
echo ""
echo " Done! Open a song in Tempo and click \"Split into instruments\"."
read -p " Press Enter to close."

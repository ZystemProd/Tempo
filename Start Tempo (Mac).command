#!/bin/bash
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Please run \"Install Tempo (Mac).command\" first."
  read -p "Press Enter to close."
  exit 1
fi
nohup .venv/bin/python run_tempo.py >> tempo-log.txt 2>&1 &
echo "Tempo is starting. You can close this window."

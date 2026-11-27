@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Please run "Install Tempo (Windows).bat" first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" run_tempo.py

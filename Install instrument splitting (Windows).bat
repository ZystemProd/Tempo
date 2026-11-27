@echo off
cd /d "%~dp0"
title Install instrument splitting
if not exist ".venv\Scripts\python.exe" (
  echo Please run "Install Tempo (Windows).bat" first.
  pause
  exit /b 1
)
echo.
echo  Installing instrument splitting (Demucs). This downloads about 1-2 GB.
echo.
".venv\Scripts\python.exe" -m pip install demucs certifi
if errorlevel 1 ( echo. & echo  Installing failed. Check your internet connection and try again. & pause & exit /b 1 )
echo.
echo  Done! Open a song in Tempo and click "Split into instruments".
echo  If you have an NVIDIA graphics card, splitting can be made much faster - see README.txt.
pause

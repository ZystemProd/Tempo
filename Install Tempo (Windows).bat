@echo off
setlocal
cd /d "%~dp0"
title Install Tempo
echo.
echo  Installing Tempo, including instrument splitting.
echo  The first time this downloads about 1-2 GB and takes 5-15 minutes.
echo.
set "PY="
for %%V in (3.13 3.12 3.14) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,12)<=sys.version_info[:2]<=(3,14) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo  Python 3.13 is needed first.
  echo  1. On the page that opens, download Python 3.13 for Windows.
  echo  2. In the installer, tick "Add python.exe to PATH", then click Install Now.
  echo  3. Run this file again.
  start "" "https://www.python.org/downloads/windows/"
  pause
  exit /b 1
)
echo  Using %PY%
%PY% -m venv .venv
if errorlevel 1 ( echo  Could not create Tempo's Python environment. & pause & exit /b 1 )
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo. & echo  Installing failed. Check your internet connection and try again. & pause & exit /b 1 )
".venv\Scripts\python.exe" -m pip install pylibrb
if errorlevel 1 echo  Rubber Band could not be installed. Tempo will use its built-in engine.
echo.
".venv\Scripts\python.exe" -c "from tempo.stretch import rubberband_available as ok, engine_problem as why; print(' Studio engine (Rubber Band R3):', 'ready' if ok() else 'not available (' + why() + ')')"
echo.
echo  Done! Start Tempo with "Start Tempo (Windows).bat".
pause

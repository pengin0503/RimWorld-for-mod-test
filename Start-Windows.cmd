@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.12 or newer with Tcl/Tk is required.
  echo Install Python, then run this file again.
  pause
  exit /b 1
)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
if errorlevel 1 (
  echo Python 3.12 or newer is required.
  pause
  exit /b 1
)
py -3 tools\mod_preflight.py desktop
if errorlevel 1 pause

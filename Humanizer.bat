@echo off
rem Double-click to launch Humanizer as an app. No cd, no server juggling.
rem Runs from this file's folder regardless of where it's launched from.
cd /d "%~dp0"
python -m humanizer --app
if errorlevel 1 (
  echo.
  echo Could not start. Make sure Python is installed and on PATH.
  echo Try running:  python --version
  pause
)

@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
start "" ".venv\Scripts\pythonw.exe" simple_screen_recorder.py
exit /b
:fail
echo Install Python 3.11 or newer from python.org, then try again.
pause

@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
)

if not exist ".venv\Scripts\pip.exe" (
  echo Virtual environment is incomplete. Please recreate .venv.
  pause
  exit /b 1
)

".venv\Scripts\pip.exe" install -r requirements.txt
".venv\Scripts\python.exe" main.py

endlocal

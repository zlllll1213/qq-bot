@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo QQ Bot launcher for Windows
echo Project: %CD%
echo ========================================
echo.

set "PYTHON_CMD="

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  set "PYTHON_CMD=py -3"
) else (
  where python >nul 2>nul
  if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=python"
  )
)

if "%PYTHON_CMD%"=="" (
  echo [ERROR] Python was not found.
  echo Please install Python 3.10+ from https://www.python.org/downloads/
  echo During installation, check "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PYTHON_CMD% -m venv .venv
  if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
  )
)

if not exist ".venv\Scripts\pip.exe" (
  echo Virtual environment is incomplete. Please recreate .venv.
  pause
  exit /b 1
)

echo Installing dependencies...
".venv\Scripts\pip.exe" install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
  echo.
  echo [ERROR] Failed to install dependencies.
  echo Check your network connection, then run start.bat again.
  pause
  exit /b 1
)

echo.
echo Starting QQ Bot...
".venv\Scripts\python.exe" main.py
if %ERRORLEVEL% NEQ 0 (
  echo.
  echo [ERROR] QQ Bot exited with an error.
  pause
  exit /b 1
)

endlocal

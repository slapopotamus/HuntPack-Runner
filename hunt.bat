@echo off
REM Launcher: runs the HuntPack-Runner using the project's virtual environment
REM directly, so you never have to activate it. Works from any directory.
REM Usage:  hunt --pick 12-13 --start 24h   (same args as run_hunt.py)
setlocal
set "PYTHONUTF8=1"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
  echo [!] Virtual environment not found at "%~dp0.venv"
  echo     Run setup.bat once to create it.
  exit /b 1
)

REM A .venv only works on the machine that built it. If this folder was copied
REM or unzipped from somewhere else, its python is a dead stub - say so plainly
REM instead of letting it fail with a confusing path error.
"%VENV_PY%" -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo [!] The .venv in this folder was built on a different machine and cannot
  echo     run here. Run setup.bat - it will rebuild the environment for you.
  exit /b 1
)

"%VENV_PY%" "%~dp0run_hunt.py" %*
endlocal

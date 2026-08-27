@echo off
REM One-step setup for the HuntPack-Runner. Double-click this file, or run it
REM from a terminal. It creates the virtual environment, installs dependencies,
REM then asks for your API credentials and region and saves them.
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"

echo ============================================================
echo  HuntPack-Runner - setup
echo ============================================================
echo.

REM 1. Find a usable Python (3.10+). The "py" launcher is tried first because
REM    a bare "python" on Windows is often the Microsoft Store stub, which
REM    reports success but cannot actually run anything.
set "PY_CMD="
for %%C in ("py -3" "python" "python3") do (
  %%~C -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY_CMD=%%~C"
    goto :have_python
  )
)

echo [!] No working Python 3.10 or newer was found.
echo.
echo     Install Python from https://python.org/downloads and tick
echo     "Add python.exe to PATH" during the install, then run setup again.
echo.
echo     If you believe Python IS installed, open a new terminal and run:
echo         py -3 --version
echo         python --version
echo     A blank result, or a Microsoft Store window opening, means the
echo     "python" on your PATH is the Store placeholder rather than a real
echo     install - installing from python.org will replace it.
echo.
pause
exit /b 1

:have_python
for /f "tokens=*" %%V in ('%PY_CMD% -c "import sys; print(sys.version.split()[0])" 2^>nul') do set "PY_VER=%%V"
echo [*] Using Python %PY_VER% ^(%PY_CMD%^)

REM 2. Virtual environment.
REM    A .venv is tied to the machine and account that built it, so one that
REM    arrived inside a copied/zipped folder will NOT work here. Rather than
REM    trust that the folder exists, actually run its python and rebuild if
REM    that fails.
set "VENV_PY=.venv\Scripts\python.exe"
set "MAKE_VENV="

if exist "%VENV_PY%" (
  "%VENV_PY%" -c "import sys" >nul 2>&1
  if errorlevel 1 (
    echo [*] The existing .venv was built elsewhere and does not work on this
    echo     machine - rebuilding it from scratch.
    set "MAKE_VENV=1"
  ) else (
    echo [*] Virtual environment already exists - reusing it.
  )
) else (
  set "MAKE_VENV=1"
)

if defined MAKE_VENV (
  if exist ".venv" rmdir /s /q ".venv"
  echo [*] Creating virtual environment ^(.venv^) ...
  %PY_CMD% -m venv .venv
  if errorlevel 1 (
    echo [!] Failed to create the virtual environment. The message above says why.
    pause
    exit /b 1
  )
  "%VENV_PY%" -c "import sys" >nul 2>&1
  if errorlevel 1 (
    echo [!] The new virtual environment is not runnable. Try deleting the
    echo     .venv folder by hand and running setup again.
    pause
    exit /b 1
  )
)

REM 3. Dependencies (prefer the hash-pinned lockfile when present).
echo [*] Installing dependencies ^(FalconPy + helpers^) ...
"%VENV_PY%" -m pip install --quiet --upgrade pip

set "DEPS_OK="
if exist "requirements.lock" (
  "%VENV_PY%" -m pip install --quiet --require-hashes -r requirements.lock
  if not errorlevel 1 set "DEPS_OK=1"
  if not defined DEPS_OK (
    echo [*] The pinned lockfile did not apply to this Python version -
    echo     falling back to requirements.txt ...
  )
)

if not defined DEPS_OK (
  "%VENV_PY%" -m pip install -r requirements.txt
  if not errorlevel 1 set "DEPS_OK=1"
)

if not defined DEPS_OK (
  echo.
  echo [!] Dependency installation failed. The pip output above shows the reason.
  echo     Common causes: no internet access, or a corporate proxy / TLS
  echo     inspection appliance blocking pypi.org.
  pause
  exit /b 1
)

"%VENV_PY%" -c "import falconpy, requests, yaml, bs4, dotenv, defusedxml" >nul 2>&1
if errorlevel 1 (
  echo [!] Dependencies installed but could not be imported. Delete the .venv
  echo     folder and run setup again.
  pause
  exit /b 1
)
echo [*] Dependencies installed.
echo.

REM 4. Interactive credentials + region
"%VENV_PY%" configure.py
if errorlevel 1 (
  echo.
  echo [!] Configuration was cancelled. Re-run setup.bat any time.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  Setup complete. From now on, just use the "hunt" launcher:
echo.
echo     hunt --list-remote
echo     hunt --latest 1 --start 24h
echo.
echo  ^(No need to activate anything - hunt uses the venv for you.^)
echo ============================================================
echo.
pause
endlocal

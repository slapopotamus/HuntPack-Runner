@echo off
REM Double-click this to open a ready-to-type HuntPack + CQL-Hub prompt.
REM The virtual environment is activated and the folder is set for you, so you
REM can just type commands like:  hunt --list-remote
cd /d "%~dp0"
set "PYTHONUTF8=1"

if not exist ".venv\Scripts\activate.bat" (
  echo.
  echo [!] Not set up yet. Run setup.bat first, then open this again.
  echo.
  pause
  exit /b 1
)

REM Put this folder on PATH so 'hunt' works even if you change directory.
set "PATH=%~dp0;%PATH%"
call ".venv\Scripts\activate.bat"

cls
echo ================================================================
echo    HuntPack-Runner - ready to use
echo ================================================================
echo.
echo    Type a command and press Enter.
echo.
echo    -- HUNTPACK library  (HTML packs, newest-first) --------------
echo      hunt --list-remote                    Browse HuntPacks
echo      hunt --latest 2 --start 24h           Run the 2 newest packs
echo      hunt --pick 9-10                      Run HuntPacks #9 and #10
echo      hunt -f huntpacks\SomePack.html       Run a local .html pack
echo.
echo    -- CQL-HUB library  (~150 YAML detections, A-Z) -------------
echo      hunt --source cqlhub --list-remote    Browse CQL-Hub
echo      hunt --source cqlhub --pick 5-10      Run detections #5 to 10
echo      hunt --source cqlhub --pick 5-10 -i   Review/approve each first
echo      hunt -f cqlhub\SomeQuery.yml          Run a local .yml query
echo.
echo    -- WORKS WITH EITHER  (add to any command above) ------------
echo      --list                                Preview queries, don't run
echo      --dry-run                             Print the CQL, don't run
echo      -i                                    Approve each query first
echo      -q 1-4                                Run only queries 1 to 4
echo      --start 24h                           Time window (60m/24h/7d/30d)
echo      --limit 20000                         Raise the 200-row cap
echo      hunt -h                               Full list of options
echo      hunt --tldr                           FULL cheat sheet (expanded)
echo.
echo    -- RESULTS ^& SETUP ------------------------------------------
echo      python review.py --open               Open the latest report
echo      python configure.py                   Change your keys or region
echo.
echo    Type  exit  to close this window.
echo ================================================================
echo.

cmd /k

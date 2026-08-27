# Launcher: runs the HuntPack-Runner using the project's virtual environment
# directly, so you never have to activate it. Works from any directory.
# Usage:  .\hunt.ps1 --pick 12-13 --start 24h   (same args as run_hunt.py)
$env:PYTHONUTF8 = "1"
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "[!] Virtual environment not found at $PSScriptRoot\.venv"
    Write-Host "    Run .\setup.ps1 once to create it."
    exit 1
}

# A .venv only works on the machine that built it. If this folder was copied or
# unzipped from somewhere else, its python is a dead stub - say so plainly
# instead of letting it fail with a confusing path error.
& $venvPy -c "import sys" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] The .venv in this folder was built on a different machine and cannot"
    Write-Host "    run here. Run .\setup.ps1 - it will rebuild the environment for you."
    exit 1
}

& $venvPy (Join-Path $PSScriptRoot "run_hunt.py") @args

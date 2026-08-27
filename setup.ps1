# One-step setup for the HuntPack-Runner (PowerShell).
# Run:  .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"

Write-Host "============================================================"
Write-Host " HuntPack-Runner - setup"
Write-Host "============================================================`n"

# 1. Find a usable Python (3.10+). The "py" launcher is tried first because a
#    bare "python" on Windows is often the Microsoft Store stub, which reports
#    success but cannot actually run anything.
$pyCmd = $null
foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
    $exe = $candidate[0]
    $pre = @($candidate | Select-Object -Skip 1)
    try {
        & $exe @pre -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" *> $null
        if ($LASTEXITCODE -eq 0) { $pyCmd = $candidate; break }
    } catch { }
}

if (-not $pyCmd) {
    Write-Host "[!] No working Python 3.10 or newer was found.`n"
    Write-Host "    Install Python from https://python.org/downloads and tick"
    Write-Host "    'Add python.exe to PATH' during the install, then run setup again.`n"
    Write-Host "    If you believe Python IS installed, open a new terminal and run:"
    Write-Host "        py -3 --version"
    Write-Host "        python --version"
    Write-Host "    A blank result, or a Microsoft Store window opening, means the"
    Write-Host "    'python' on your PATH is the Store placeholder rather than a real"
    Write-Host "    install - installing from python.org will replace it."
    exit 1
}

$pyExe = $pyCmd[0]
$pyArgs = @($pyCmd | Select-Object -Skip 1)
$pyVer = (& $pyExe @pyArgs -c "import sys; print(sys.version.split()[0])")
Write-Host "[*] Using Python $pyVer ($($pyCmd -join ' '))"

# 2. Virtual environment.
#    A .venv is tied to the machine and account that built it, so one that
#    arrived inside a copied/zipped folder will NOT work here. Rather than trust
#    that the folder exists, actually run its python and rebuild if that fails.
$venvPy = ".\.venv\Scripts\python.exe"
$makeVenv = $true

if (Test-Path $venvPy) {
    & $venvPy -c "import sys" *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[*] Virtual environment already exists - reusing it."
        $makeVenv = $false
    } else {
        Write-Host "[*] The existing .venv was built elsewhere and does not work on this"
        Write-Host "    machine - rebuilding it from scratch."
    }
}

if ($makeVenv) {
    if (Test-Path ".venv") { Remove-Item -Recurse -Force ".venv" }
    Write-Host "[*] Creating virtual environment (.venv) ..."
    & $pyExe @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] Failed to create the virtual environment."
        exit 1
    }
}

# 3. Dependencies (prefer the hash-pinned lockfile when present).
Write-Host "[*] Installing dependencies (FalconPy + helpers) ..."
& $venvPy -m pip install --quiet --upgrade pip

$depsOk = $false
if (Test-Path "requirements.lock") {
    & $venvPy -m pip install --quiet --require-hashes -r requirements.lock
    $depsOk = ($LASTEXITCODE -eq 0)
    if (-not $depsOk) {
        Write-Host "[*] The pinned lockfile did not apply to this Python version -"
        Write-Host "    falling back to requirements.txt ..."
    }
}
if (-not $depsOk) {
    & $venvPy -m pip install -r requirements.txt
    $depsOk = ($LASTEXITCODE -eq 0)
}
if (-not $depsOk) {
    Write-Host "`n[!] Dependency installation failed. The pip output above shows the reason."
    Write-Host "    Common causes: no internet access, or a corporate proxy / TLS"
    Write-Host "    inspection appliance blocking pypi.org."
    exit 1
}
Write-Host "[*] Dependencies installed.`n"

& $venvPy configure.py

Write-Host "`n============================================================"
Write-Host " Setup complete. Use the launcher from now on:"
Write-Host "     .\hunt.ps1 --list-remote"
Write-Host "     .\hunt.ps1 --latest 1 --start 24h"
Write-Host "============================================================"

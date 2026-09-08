# Windows / Python 3.12 / package acceptance sequence

This is the exact acceptance sequence for a Windows operator. It must run on
a clean Windows machine with the user's separately managed MinerU installation;
Linux execution cannot substitute for it. Use a test database, never the user
production database.

The sequence intentionally uses placeholders rather than embedding a company,
well, filename, coordinate, or row number.

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path 'C:\path\to\Drill-master').Path
$TestRoot = Join-Path $env:TEMP 'DrillMaster-acceptance'
$DbPath = Join-Path $TestRoot 'acceptance.db'
$Xlsx = 'C:\path\to\real\DDR.xlsx'
$Pdf = 'C:\path\to\real\DDR.pdf'
$MinerU = 'C:\path\to\managed\mineru.exe'
New-Item -ItemType Directory -Force $TestRoot | Out-Null
Set-Location $Repo

# Exact runtime gate: Python 3.12 must be the interpreter executing every step.
py -3.12 --version
$Venv = Join-Path $TestRoot 'venv312'
py -3.12 -m venv $Venv
$Python = Join-Path $Venv 'Scripts\python.exe'
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements-lock.txt -r requirements-build.txt
& $Python -c "import sys; assert sys.version_info[:2] == (3, 12); print(sys.executable)"

# Never touch production state. The app writes only to this test data directory.
$env:DRILLMASTER_ENV = 'test'
$env:DRILLMASTER_DATA_DIR = (Join-Path $TestRoot 'user-data')
$env:DRILLMASTER_DB_PATH = $DbPath
$env:DRILLMASTER_AI_IMPORT = '0'
$env:DRILLMASTER_TEST_DDR_XLSX = $Xlsx
$env:DRILLMASTER_TEST_DDR_PDF = $Pdf
$env:DRILLMASTER_MINERU_ENABLED = '1'
$env:DRILLMASTER_MINERU_EXECUTABLE = $MinerU
& $MinerU --version

# Source, real-workbook, PDF/IR, atomicity, AI-boundary, and package checks.
& $Python -m pytest -ra
& $Python -m pytest -q -m integration tests/test_ddr_acceptance.py
& $Python -m compileall -q core dialogs tabs tests
& $Python -m py_compile app.py run.py main_window.py verify_release.py
& $Python -m pip wheel . --no-deps --wheel-dir (Join-Path $TestRoot 'wheel')

# Build and statically/runtime-smoke the Windows portable bundle.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repo 'packaging\build_windows.ps1') -PortableOnly -Python 'py -3.12'
$Version = (& $Python -c "from core.version import __version__; print(__version__)").Trim()
$Bundle = Join-Path $Repo ("release\DrillMaster-{0}" -f $Version)
& $Python (Join-Path $Repo 'packaging\package_smoke.py') --bundle-dir $Bundle --run

# Record evidence without adding it to Git.
Get-Content (Join-Path $env:DRILLMASTER_DATA_DIR 'logs\*') -ErrorAction SilentlyContinue
Write-Host "Acceptance DB: $DbPath"
Write-Host "Bundle: $Bundle"
```

Required recorded evidence is the Python version/executable, MinerU executable
and `mineru --version`, generated command (`-p/-o/-b/-m`), output files/assets,
canonical values with source units, all ReviewItems, DB counts, and the package
smoke result. A missing path is a blocked acceptance, not a synthetic pass.

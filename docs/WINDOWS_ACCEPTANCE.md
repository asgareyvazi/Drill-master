# Windows / Python 3.12 / package acceptance sequence

> **Current evidence — 2026-09-27: [Mission 33 semantic audit](../M33_SEMANTIC_AUDIT.md).** Inventory **8934** occurrences adjudicated from the current source: **3712 verified-correct**, **2264 intentional-by-design**, **51 defect-fixed**, **49 removed-with-evidence**, **17 external-acceptance-only**, **2837 under-review** and **4 evidence-incomplete** (the last two stop release certification for repository-verifiable items). This tree is **NOT RELEASE-CERTIFIABLE** — see [M33_RELEASE_CERTIFICATION.md](../M33_RELEASE_CERTIFICATION.md). Earlier counts, SHAs and acceptance statements anywhere below are historical or unverified, not current certification.

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
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }
$Venv = Join-Path $TestRoot 'venv312'
py -3.12 -m venv $Venv
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }
$Python = Join-Path $Venv 'Scripts\python.exe'
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }
& $Python -m pip install -r requirements-lock.txt -r requirements-build.txt pytest==9.1.1 ruff==0.16.6 build==1.6.1
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }
& $Python -c "import sys; assert sys.version_info[:2] == (3, 12); print(sys.executable)"
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }

# Never touch production state. The app writes only to this test data directory.
$env:DRILLMASTER_ENV = 'test'
$env:DRILLMASTER_DATA_DIR = (Join-Path $TestRoot 'user-data')
$env:DRILLMASTER_DB_PATH = $DbPath
$env:DRILLMASTER_AI_IMPORT = '0'
$env:DRILLMASTER_TEST_DDR_XLSX = $Xlsx
$env:DRILLMASTER_TEST_DDR_PDF = $Pdf
$env:MINERU_INTEGRATION_INPUT = $Pdf
$env:DRILLMASTER_MINERU_ENABLED = '1'
$env:DRILLMASTER_MINERU_EXECUTABLE = $MinerU
& $MinerU --version
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }

# Source, real-workbook, PDF/IR, atomicity, AI-boundary, and package checks.
& $Python -m pytest -ra
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }
& $Python -m pytest -q -m integration tests/test_ddr_acceptance.py
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }
& $Python -m compileall -q core dialogs tabs tests
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }
& $Python -m py_compile app.py run.py main_window.py verify_release.py
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }
& $Python -m pip wheel . --no-deps --wheel-dir (Join-Path $TestRoot 'wheel')
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }

# Build and statically/runtime-smoke the Windows portable bundle.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repo 'packaging\build_windows.ps1') -PortableOnly -Python 'py -3.12'
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }
$Version = (& $Python -c "from core.version import __version__; print(__version__)").Trim()
$Bundle = Join-Path $Repo ("release\DrillMaster-{0}" -f $Version)
& $Python (Join-Path $Repo 'packaging\package_smoke.py') --bundle-dir $Bundle --run
if ($LASTEXITCODE -ne 0) { throw "Acceptance command failed; stop and preserve evidence" }

# Record evidence without adding it to Git.
Get-Content (Join-Path $env:DRILLMASTER_DATA_DIR 'logs\*') -ErrorAction SilentlyContinue
Write-Host "Acceptance DB: $DbPath"
Write-Host "Bundle: $Bundle"
```

Required recorded evidence is the Python version/executable, MinerU executable
and `mineru --version`, generated command (`-p/-o/-b/-m`), output files/assets,
canonical values with source units, all ReviewItems, DB counts, and the package
smoke result. A missing path is a blocked acceptance, not a synthetic pass.

## Separate mandatory installer/operator gate — not covered above

The `-PortableOnly` procedure does not test an installer. On a clean Windows
machine also run the build **without** `-PortableOnly`, install the resulting
Setup EXE, first-launch the installed application without Python, complete
production bootstrap with test-only unique credentials, verify resources/import
and reports, back up and restore a disposable database, upgrade over a prior
installation, and uninstall while confirming user data is retained. Record
SHA256SUMS, exact source SHA, Python version, exit codes, screenshots and DB
integrity checks. No step is a PASS before that evidence exists.

`test_real_windows_bundle_smoke_when_provided` checks bundle structure only;
`package_smoke.py --run` executes the real EXE. Neither replaces interactive
first launch, import/export or installer/upgrade acceptance. Real MinerU input
is separately gated by `MINERU_INTEGRATION_INPUT`.

Current Linux audit: **BLOCKED BY ENVIRONMENT** for all real Windows steps.

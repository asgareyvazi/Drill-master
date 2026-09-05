# DrillMaster Windows deployment and release runbook

This repository builds a Windows x64 one-folder application with PyInstaller
and an Inno Setup installer. The end-user installation does not require
Python, pip, Git, the repository, or developer tools.

## Build prerequisites

On a Windows build machine install:

- Python 3.11 x64
- Inno Setup 6, with `ISCC.exe` on `PATH`
- Access to the pinned wheels in `requirements-lock.txt`

The build script creates an isolated `.windows-build-venv` and installs the
pinned runtime plus the pinned PyInstaller toolchain from:

```text
requirements-lock.txt
requirements-build.txt
```

Do not install optional AI/document packages for the core build.

## Reproducible build

From the repository root in PowerShell:

```powershell
.\packaging\build_windows.ps1
```

The script:

1. Reads the authoritative version from `core/version.py`.
2. Creates the ignored Windows build virtual environment.
3. Installs the runtime and build locks.
4. Runs `packaging/DrillMaster.spec`.
5. Produces a PyInstaller one-folder bundle.
6. Executes `DrillMaster.exe --package-smoke` against a temporary data root.
7. Runs Inno Setup using `packaging/DrillMaster.iss`.
8. Writes SHA-256 hashes.

Expected output:

```text
release\DrillMaster-1.0.0\DrillMaster.exe
release\DrillMaster-1.0.0-Setup.exe
release\SHA256SUMS.txt
```

For a portable bundle without Inno Setup:

```powershell
.\packaging\build_windows.ps1 -PortableOnly
python packaging\package_smoke.py --bundle-dir release\DrillMaster-1.0.0 --run
```

`DrillMaster.spec` explicitly includes the application modules, Qt runtime,
SQLAlchemy, bcrypt, numpy, pandas, openpyxl, matplotlib, pyqtgraph, PyMuPDF,
engineering modules, import modules, export modules, dialogs, tabs, and JSON
mapping templates. It excludes tests and optional Ollama/Qwen/MinerU/Camelot/
OCR/welleng/torque-drag/gekko packages. Qt's Windows platform plugin is
verified by `package_smoke.py`.

There is no repository icon. The build deliberately does not create a fake
icon. The executable still receives product name, file version, product
version, and file description metadata. Add a legitimate `.ico` later by
setting the `icon` field in the spec and the installer icon fields.

## Install and first run

Run `DrillMaster-1.0.0-Setup.exe` as a normal Windows installation. The
installer:

- installs application files under `{autopf}\DrillMaster`;
- creates a Start Menu shortcut and optional desktop shortcut;
- upgrades application files in place;
- does not place SQLite data under Program Files;
- does not delete user data during uninstall.

On a clean machine the first launch creates required directories and opens the
secure first-run bootstrap dialog. The operator creates unique passwords for
Administrator, Engineer, and Viewer. The application holds plaintext values
only during that process and stores salted bcrypt hashes in the database. It
creates no demo company, project, well, or development account.

If the first-run dialog is cancelled or database initialization fails, the
application exits without silently proceeding. The protected rotating log can
be used for diagnostics.

Unattended enterprise bootstrap can supply the existing environment variables
`DRILLMASTER_ENV=production`, `DRILLMASTER_ADMIN_PASSWORD`,
`DRILLMASTER_USER_PASSWORD`, and `DRILLMASTER_VIEWER_PASSWORD` through a
restricted secret mechanism. Do not put them in the installer, executable,
source tree, or a committed `.env` file.

## Application data

The existing single runtime path mechanism is `core/runtime_config.py`:

| Data | Default Windows location |
| --- | --- |
| SQLite database | `%LOCALAPPDATA%\DrillMaster\drillmaster.db` |
| Logs | `%LOCALAPPDATA%\DrillMaster\logs\drillmaster.log` |
| Automatic backups | `%LOCALAPPDATA%\DrillMaster\backups` |
| AI settings | `%LOCALAPPDATA%\DrillMaster\config\ai_settings.json` |
| Mapping memory | `%LOCALAPPDATA%\DrillMaster\config\mapping_memory.json` |
| Standards overrides | `%LOCALAPPDATA%\DrillMaster\config\operational_standards.json` |

`DRILLMASTER_DATA_DIR` can redirect all mutable state. The individual
`DRILLMASTER_DB_PATH`, `DRILLMASTER_LOG_DIR`, and `DRILLMASTER_BACKUP_DIR`
overrides remain supported. Relative overrides resolve below the data root.
The executable directory and Program Files remain read-only application files.

## Upgrade and data preservation

Before upgrading:

1. Close DrillMaster.
2. Use the Backup action or copy/verify an external SQLite backup.
3. Install the newer setup executable over the existing installation.
4. Launch and verify login, schema version, company/project/well data, and a
   new backup.

The installer replaces only files below `{app}`. It does not delete or replace
`%LOCALAPPDATA%\DrillMaster`. On startup, additive migrations are applied and
recorded in `schema_version`; a migration failure stops startup rather than
allowing a partial schema to run.

To uninstall, use Windows Apps/Programs. Installed application files and
shortcuts are removed; database, logs, backups, mapping memory, AI settings,
and standards overrides remain for possible reinstall or manual retention.

## Optional Ollama, Qwen, and MinerU

The core package works without all optional AI/document components.

```powershell
$env:DRILLMASTER_AI_IMPORT = "1"
$env:DRILLMASTER_AI_MODEL = "qwen2.5:3b"
$env:DRILLMASTER_OLLAMA_URL = "http://127.0.0.1:11434"
```

Install Ollama and download a selected Qwen model separately, under the
operator's licensing and data-transfer policy. No Ollama executable, Qwen
weight, cloud credential, MinerU/magic-pdf package, or third-party binary is
bundled. The capability reporter detects disabled/unavailable/model-missing
states without network access unless an explicit probe is requested. Missing
optional components never prevent core startup.

## Clean-machine acceptance procedure

The following is the manual Windows acceptance checklist. It must be run on a
Windows x64 machine without Python, Git, the repository, or a developer
environment; results must be recorded with the installer hash.

- [ ] install `DrillMaster-1.0.0-Setup.exe`
- [ ] application launches from the Start Menu shortcut
- [ ] required data directories and database are created outside Program Files
- [ ] secure first-run bootstrap creates production accounts
- [ ] login succeeds; no development fixture account is present
- [ ] company can be created
- [ ] project can be created
- [ ] well can be created
- [ ] existing UI loads
- [ ] engineering registry loads
- [ ] W12 and W13 paths load
- [ ] Excel import module loads
- [ ] export modules load
- [ ] log file is written
- [ ] database backup succeeds and opens separately
- [ ] application closes cleanly
- [ ] reopening preserves company/project/well data
- [ ] upgrade over that installation preserves data and applies migration
- [ ] uninstall removes application files but leaves user data

This Linux environment cannot execute a Windows PE executable or run Inno
Setup. The manual clean-machine, installer upgrade, and Windows Qt-plugin
checks are therefore **pending**, not claimed as passed. The repository does
contain a static packaging test and a frozen-bundle smoke command for Windows
CI/build operators.

## Release gate

Archive these outputs with the release artifact:

```powershell
python -m pytest -ra
python verify_release.py
python -m compileall -q core dialogs tabs tests
python -m py_compile app.py run.py main_window.py verify_release.py
python -m pip wheel . --no-deps --wheel-dir dist
git diff --check
Get-FileHash .\release\DrillMaster-1.0.0-Setup.exe -Algorithm SHA256
```

A green Python test suite is an automated pass only; it is not a Windows
clean-machine pass and does not certify the engineering limitations documented
in `README.md` and `PRODUCTION_READINESS.md`.

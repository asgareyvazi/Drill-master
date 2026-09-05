# DrillMaster deployment and release runbook

This runbook covers the supported local Windows or desktop deployment. It
assumes the operator owns the machine, SQLite file, backups, and any optional
Ollama models. DrillMaster is not a server or a licensing service.

## Install a wheel

From a clean checkout on the build machine:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip build wheel
python -m pip install -r requirements-lock.txt
python -m build --wheel
```

Copy the generated `dist\drillmaster-1.0.0-py3-none-any.whl` and
`requirements-lock.txt` to the target machine, then install:

```powershell
py -3.11 -m venv C:\DrillMaster\venv
C:\DrillMaster\venv\Scripts\python.exe -m pip install -r requirements-lock.txt
C:\DrillMaster\venv\Scripts\python.exe -m pip install .\drillmaster-1.0.0-py3-none-any.whl
C:\DrillMaster\venv\Scripts\drillmaster.exe
```

The wheel contains application code and JSON mapping/configuration templates.
It does not contain SQLite data, logs, backups, Ollama, Qwen, MinerU, or other
external binaries/models. Keep the virtual environment and the data directory
out of source control. A shortcut may target
`C:\DrillMaster\venv\Scripts\drillmaster.exe` with the operator's environment
variables configured by the machine/service-account policy.

## Production bootstrap

Set the environment to production before the first launch. Configure all
three bootstrap secrets using Windows environment policy, a wrapper script
with restricted ACLs, or the organization's secret manager; do not put them
in a committed `.env` file:

```powershell
$env:DRILLMASTER_ENV = "production"
$env:DRILLMASTER_ADMIN_PASSWORD = "<unique secret>"
$env:DRILLMASTER_USER_PASSWORD = "<unique secret>"
$env:DRILLMASTER_VIEWER_PASSWORD = "<unique secret>"
$env:DRILLMASTER_DATA_DIR = "C:\ProgramData\DrillMaster"
```

The first production start creates the three hashed bootstrap accounts but no
company, project, or well demo records. Change or retire bootstrap accounts
according to the organization's access procedure. Auto-login and development
fixture passwords are unavailable in production.

For a portable or test installation, set `DRILLMASTER_DATA_DIR` to an
explicit writable directory. `DRILLMASTER_DB_PATH`, `DRILLMASTER_LOG_DIR`, and
`DRILLMASTER_BACKUP_DIR` may override individual locations; relative overrides
are resolved below the data root. The application must have create/write
permission for the database, log, backup, and AI-settings parent directories.

## Operations

- Logs: `<data>\logs\drillmaster.log`, rotating at 10 MiB with five retained
  files. Logs contain diagnostics, not passwords; restrict access to operators.
- Database: `<data>\drillmaster.db` unless overridden.
- Automatic backups: `<data>\backups`, ten retained files. The UI also offers
  a user-selected verified backup destination.
- Recovery: stop DrillMaster, preserve the failed database, restore a verified
  backup, and start with the same path configuration. Confirm the schema and
  authenticate before resuming work. Perform a documented restore drill; the
  application does not provide cloud replication or backup encryption.
- Upgrade: take and verify a backup, install the new wheel, then start. Schema
  upgrades are additive and versioned in `schema_version`; a failed migration
  intentionally prevents normal startup.

## Optional AI and document processing

Local AI is opt-in only:

```powershell
$env:DRILLMASTER_AI_IMPORT = "1"
$env:DRILLMASTER_AI_MODEL = "qwen2.5:3b"
$env:DRILLMASTER_OLLAMA_URL = "http://127.0.0.1:11434"
```

Install and manage Ollama and the selected model separately. The application
checks `/api/tags` only after opt-in, uses a bounded timeout, and continues
without AI when Ollama or the model is unavailable. The optional capability
reporter checks MinerU package presence without importing it or making network
calls. It sends workbook mapping context only to the explicitly configured
local endpoint. Do not configure a
cloud-labelled model unless the organization's data-transfer and Ollama Cloud
review permits it. Qwen weights, MinerU, and third-party binaries are never
bundled by this project.

Camelot, OCR, `welleng`, `torque-drag`, and `gekko` are optional integrations.
Install them only after reviewing their licenses and validate their capability
status in the engineering registry. Their absence must not prevent startup.

## Release gate

A release candidate is distributable only when these commands pass on the
build environment and their output is archived:

```powershell
python -m pytest -ra
python verify_release.py
python -m compileall -q core dialogs tabs tests
python -m py_compile app.py run.py main_window.py verify_release.py
python -m pip wheel . --no-deps --wheel-dir dist
python -m ruff check .
git diff --check
```

Record the exact commit SHA, wheel filename/hash, Python version, dependency
lock used, pytest `collected/passed/skipped/failed/errors` counts, and the
result of a manual backup/restore drill. A green automated gate does not make
anti-collision, engineering standards, or operational data field-certified.

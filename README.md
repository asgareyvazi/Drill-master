# DrillMaster

DrillMaster is a Windows-oriented Qt desktop application for drilling
operations records, canonical report import, and deterministic engineering
calculations. The UI routes calculations through the canonical engineering
facade and `EngineeringResult`; it is not a replacement for field or
regulatory engineering review.

## Release-candidate status

The repository contains a reproducible PyInstaller one-folder build and an
Inno Setup installer definition. End users should install the generated
`DrillMaster-1.0.0-Setup.exe`; they should not need Python, pip, Git, source
code, or developer tools. See [DEPLOYMENT.md](DEPLOYMENT.md) for the exact
Windows build and clean-machine procedure.

The package does not bundle external AI models, licensed engineering packages,
field-certification data, or optional document-processing binaries.

## End-user installation

On a clean Windows x64 machine, run `DrillMaster-1.0.0-Setup.exe`. The
installer places the executable under Program Files and creates Start Menu and
optional desktop shortcuts. The SQLite database and all mutable settings stay
outside Program Files. Upgrades replace application files only; uninstall
removes installed application files but does not remove the user data
directory, database, logs, or backups.

At first run, DrillMaster opens a secure bootstrap dialog when no database
exists. Create unique passwords for the Administrator, Engineer, and Viewer
accounts. The plaintext passwords remain only in process memory while the
initial salted bcrypt hashes are created. No password is embedded in the
executable or written to an environment/configuration file by the application.
Production starts with no demo company, project, or well.

## Build prerequisites

Only the build machine needs these tools:

- Windows x64
- Python 3.11
- Internet or an internal package mirror for the pinned wheels
- Inno Setup 6 (`ISCC.exe`) for the installer; PyInstaller is installed by
  the build script

Build from a clean checkout in PowerShell:

```powershell
.\packaging\build_windows.ps1
```

The script creates an ignored `.windows-build-venv`, installs
`requirements-lock.txt` and `requirements-build.txt`, runs PyInstaller, runs
the frozen package smoke test, invokes Inno Setup, and writes:

```text
release\DrillMaster-1.0.0\DrillMaster.exe
release\DrillMaster-1.0.0-Setup.exe
release\SHA256SUMS.txt
```

To build and smoke-test only the portable one-folder directory when Inno Setup
is not available:

```powershell
.\packaging\build_windows.ps1 -PortableOnly
```

The build is authoritative from `core/version.py`; the PyInstaller executable
metadata and installer filename are generated as `1.0.0` from that value. No
icon is currently present in the repository, so the build intentionally uses
no fabricated placeholder icon. An icon can later be added to the spec and
installer without changing the data or upgrade architecture.

## Runtime paths and configuration

DrillMaster never needs write access to its executable or installation
directory. The central path configuration is in `core/runtime_config.py`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `DRILLMASTER_DATA_DIR` | Root for mutable user data | `%LOCALAPPDATA%\DrillMaster` on Windows |
| `DRILLMASTER_DB_PATH` | SQLite database; relative values are under the data root | `<data>\drillmaster.db` |
| `DRILLMASTER_LOG_DIR` | Rotating application logs | `<data>\logs` |
| `DRILLMASTER_BACKUP_DIR` | Automatic backups | `<data>\backups` |
| `DRILLMASTER_AI_SETTINGS_PATH` | Selected local-AI model settings | `<data>\config\ai_settings.json` |
| `DRILLMASTER_MAPPING_MEMORY_PATH` | User-confirmed mapping memory | `<data>\config\mapping_memory.json` |
| `DRILLMASTER_STANDARDS_PATH` | User operational-standard overrides | `<data>\config\operational_standards.json` |
| `DRILLMASTER_ENV` or `DRILLMASTER_ENVIRONMENT` | Explicit `production`, `development`, or `test` mode | Desktop app defaults to production |
| `DRILLMASTER_AUTO_LOGIN` | Development/test convenience only | disabled |

Production bootstrap passwords may be supplied by an enterprise deployment
secret mechanism for unattended initialization. The normal desktop first-run
flow does not persist them. Development fixture passwords are rejected in
production. Production requires bcrypt and stores passwords only as salted
bcrypt hashes; development-only fallback hashing must not be used for
production data. A local SQLite database is not an encrypted secrets store.

## Database, migrations, backup, and recovery

The default database is a per-user SQLite file. On first initialization the
schema is created and `schema_version` is recorded. Existing databases receive
only the additive, idempotent migrations in `DatabaseManager`; migration
errors fail startup rather than allowing a partially upgraded database to run.
The current schema version is `1`.

Use the in-application Backup action or configured automatic backup. The
backup uses SQLite's backup API, includes WAL state, and retains ten automatic
backups. Before an upgrade, create an external copy and verify that it opens in
a separate DrillMaster data directory. Restore by stopping the application,
preserving the failed database, replacing it with the verified backup, and
starting again. Backups are not encrypted by DrillMaster; protect their
filesystem and access permissions.

## Optional local AI and document processing

AI-assisted workbook mapping is **disabled by default**. Set
`DRILLMASTER_AI_IMPORT=1`, optionally set `DRILLMASTER_AI_MODEL`, and run an
Ollama service at `DRILLMASTER_OLLAMA_URL` (default
`http://127.0.0.1:11434`) to opt in. Capability checks are local, bounded by a
timeout, and return `disabled`, `ollama-unavailable`, or
`model-not-installed` without blocking deterministic imports. The
`core.optional_capabilities` detector reports Ollama, installed Qwen models,
and MinerU package presence without network access unless an explicit probe is
requested.

Qwen models are not bundled. Cloud-labelled models require the operator's own
Ollama access and data-transfer approval. MinerU, `magic-pdf`, Camelot, OCR,
`welleng`, `torque-drag`, and `gekko` are not in the core bundle. Optional
packages are listed in `requirements-optional.txt` and must be installed and
licensed separately.

## Engineering and import limitations

- Anti-Collision remains **PARTIAL / SCREENING** and must not be represented as
  a validated uncertainty or separation-standard implementation.
- Missing engineering inputs produce an explicit failure, unsupported, or
  `MISSING_INPUT` result; the application does not invent field values.
- Import results preserve source lineage and require review/confirmation before
  persistence. Company-specific mappings are JSON templates, not hidden Python
  logic.
- ISCWSA/API TR 5C3 compliance, field certification, pore-pressure prediction,
  laboratory slurry design, connection qualification, cost forecasting, and
  production surveillance are outside the evidence-backed scope of this
  release candidate.

## Development and release validation

The source checkout requires Python 3.10-3.13 and the dependencies in
`requirements.txt`. For a reproducible development environment:

```bash
python -m venv .venv
# Linux/macOS: . .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
python -m app
```

Run from the repository root:

```bash
python -m pytest -ra
python verify_release.py
python -m compileall -q core dialogs tabs tests
python -m py_compile app.py run.py main_window.py verify_release.py
python -m pip wheel . --no-deps --wheel-dir dist
git diff --check
```

`verify_release.py` performs a source compile check, dynamic pytest collection,
and the complete configured pytest suite. The Windows frozen package smoke
test is run by `packaging/build_windows.ps1`; it checks the executable, JSON
assets, Qt platform plugin, import paths, database initialization, schema, and
export/import module boundaries without enabling optional AI components.

# DrillMaster

> **Current release-status authority:** [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md). It separates repository verification from Windows, PDF/MinerU, production-database, and operator acceptance.



DrillMaster is a Windows-oriented Qt desktop application for drilling
operations records, canonical report import, and deterministic engineering
calculations. The UI routes calculations through the canonical engineering
facade and `EngineeringResult`; it is not a replacement for field or
regulatory engineering review.

## Release and acceptance scope

The repository contains PyInstaller one-folder and Inno Setup build definitions.
The Linux Source release gate verifies source, locked dependencies, tests, and a
wheel; it does **not** execute a Windows EXE or installer. Windows clean-machine,
upgrade/uninstall, real MinerU/PDF, production-database, and operator acceptance
remain unrun. Do not treat packaging definitions as acceptance evidence. The
single current status source is [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md);
see [DEPLOYMENT.md](DEPLOYMENT.md) for the intended Windows procedure.

The package does not bundle external AI models, licensed engineering packages,
field-certification data, or optional document-processing binaries.

## End-user installation

The intended clean-machine workflow is to run `DrillMaster-1.0.0-Setup.exe`.
The Inno Setup definition targets Program Files and Start Menu shortcuts while
keeping mutable user data outside the install tree; upgrade/uninstall retention
is defined by that packaging configuration. Clean-machine installation,
upgrade, and uninstall behavior have not yet been exercised on Windows and
remain external acceptance steps.

At first run, DrillMaster opens a secure bootstrap dialog when no database
exists and no bootstrap environment credentials are supplied. Create a unique
Administrator password; Engineer and Viewer accounts are optional. The plaintext passwords remain only in process memory while the
initial salted bcrypt hashes are created. No password is embedded in the
executable or written to an environment/configuration file by the application.
Production starts with no demo company, project, or well.

## Build prerequisites

Only the build machine needs these tools:

- Windows x64
- Python 3.12 x64 by default (`packaging/build_windows.ps1` accepts an explicit interpreter override)
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
| `DRILLMASTER_ENV` or `DRILLMASTER_ENVIRONMENT` | Explicit `production`, `development`, or `test` mode | Desktop, database library and reset CLI default to production |
| `DRILLMASTER_AUTO_LOGIN` | Development/test convenience only | disabled |

Production bootstrap passwords may be supplied by an enterprise deployment
secret mechanism for unattended initialization. The normal desktop first-run
flow does not persist them. Development fixture passwords are rejected in
production. Production requires bcrypt and stores passwords only as salted
bcrypt hashes; development-only fallback hashing must not be used for
production data. A local SQLite database is not an encrypted secrets store.

Only `DRILLMASTER_ADMIN_PASSWORD` is required for unattended production bootstrap.
Set `DRILLMASTER_USER_PASSWORD` / `DRILLMASTER_VIEWER_PASSWORD` only when those
accounts are wanted; unset optional settings rather than supplying empty strings.
Passwords require 12 characters minimum and 72 UTF-8 bytes maximum. Bootstrap
settings never overwrite existing users. No `.env` file is auto-loaded.

For a full reset, close every application instance, back up the configured DB,
and run `python reset_database.py` with secure bootstrap settings in that same
shell. Reset validates and builds a replacement before replacing the old file.
Missing/invalid credentials refuse reset before deletion. This erases all database
users and operational data, not external settings or backups. The settings dialog
provides offline instructions; clicking it does not perform a reset.
See [the credential lifecycle report](docs/audits/2026-09-08-ddr/PRODUCTION_CREDENTIAL_LIFECYCLE_FIX.md).

Local fixture use must explicitly select `DRILLMASTER_ENV=development` or `test`
and should use a separate `DRILLMASTER_DATA_DIR`. Unknown, empty, or conflicting
environment selectors are rejected; no filename/CWD-based mode inference is used.


## Database, migrations, backup, and recovery

The default database is a per-user SQLite file. On first initialization the
schema is created and `schema_version` is recorded. Existing databases receive
only the additive, idempotent migrations in `DatabaseManager`; migration
errors fail startup rather than allowing a partially upgraded database to run.
The current schema version is `4`. Future schema versions are rejected before startup or import; migrations are additive and verified before imports are enabled. The v3-to-v4 migration adds nullable `daily_reports.mw_pcf` for the DDR header remark MW (PCF) and deliberately does not backfill from `mud_reports.mw` or `mud_weight_in/out`; legacy header readings remain unknown (`NULL`). Mud-sample `MudReport.mw` is a distinct PCF-domain measurement. Imports require a resolvable explicit source unit and retain source/canonical unit lineage in the immutable DDR import audit.

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

## Import architecture and acceptance status

The supported import graph is exactly:

```text
Excel -> extractor -> common Import IR -> canonical mapping
      -> shared typed normalization -> explicit unit conversion
      -> validation -> ReviewItem preview -> atomic persistence
PDF/document/image -> external MinerU adapter -> same downstream path
```

`core/import_ir.py` is lossless and preserves source file/page/sheet/table,
row/column/cell, headers, section titles, source units when supplied,
coordinates, original/normalized values, extraction method, confidence,
validation state, and review state. `ExcelIntelligence` maps from that IR; it
does not reread the workbook as a competing extractor. MinerU remains an
external, separately managed installation: DrillMaster neither reinstalls it
nor merges its Python environment with the application runtime.

The canonical schema currently has 325 fields in 28 domains, 12 critical
fields, and 523 alias entries. Thirty-seven normalized aliases are ambiguous
without field context. Missing values/provenance remain NULL/unknown; low
confidence and ambiguity remain review items; no defaults or zeros are
invented. `ProfileImportEngine` direct DB writes and its Smart Template silent
fallback are disabled. CSV/PDF conversion helpers, WITSML placeholders,
legacy XLS, and the Smart Template manual UI are explicitly bounded legacy or
unsupported routes; they are not alternate automatic persistence architectures.

Real-document tests are environment-gated. The tracked OEOC workbook
acceptance is recorded PASS in the M36 W16 evidence; it is repository
source-corpus evidence, not a Windows/operator or production-database sign-off.
PDF and external MinerU runs remain NOT RUN. The CI matrix includes Python
3.11–3.13 on Linux; that does not constitute Windows/Python packaging
acceptance. Set `DRILLMASTER_TEST_DDR_XLSX` and `DRILLMASTER_TEST_DDR_PDF` to
exercise opt-in document tests. See `docs/WINDOWS_ACCEPTANCE.md` for the
unexecuted Windows acceptance sequence.

## Engineering and import limitations

- Anti-Collision is **PARTIAL / SCREENING**; it is not an ISCWSA uncertainty or
  separation-standard implementation.
- Casing is **PARTIAL** (not full API TR 5C3); Torque & Drag is **PARTIAL /
  SCREENING**. Production T&D and cement laboratory design are
  **NOT_IMPLEMENTED**.
- Engineering outputs retain explicit scope, warnings, and missing-input
  semantics; a partial/screening result is not field certification.
- Canonical import results preserve source lineage and keep unresolved review
  proposals separate from explicit operator decisions. Company mappings are
  JSON templates, not hidden Python policy.
- Field certification, pore-pressure prediction, connection qualification,
  cost forecasting, and production surveillance remain outside the
  evidence-backed scope.

## Development and release validation

Project metadata permits Python 3.10–3.13, but the locked Source release gate
is exercised on Python 3.11–3.13. Metadata allowance is not a support or
acceptance claim for Python 3.10. The canonical release status records the
last exact-SHA CI baseline and external acceptance boundaries.

For a locked development environment:

```bash
python -m venv .venv
# Linux/macOS: . .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
# Verification tools (not runtime dependencies):
python -m pip install pytest==9.1.1 ruff==0.16.6 build==1.6.1
python -m app
```

Run from the repository root:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -ra
python verify_release.py --expected-sha "$(git rev-parse HEAD)"
python -m compileall -q core dialogs tabs tests
python -m py_compile app.py run.py main_window.py verify_release.py
git diff --check
```

The Source release workflow runs against real Qt system libraries and validates
the exact GitHub source SHA, locked dependencies, full pytest suite, lint gates,
compilation, and wheel contents. A pass applies only when the run's `head_sha`
equals the commit being assessed. It does not certify Windows, a frozen EXE,
installer behavior, external MinerU/PDF, production data, or operator acceptance.
See [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) for the current
repository/external status boundary.

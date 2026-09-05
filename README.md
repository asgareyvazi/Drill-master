# DrillMaster

DrillMaster is a Qt desktop application for drilling operations records,
canonical report import, and deterministic engineering calculations. The UI
routes calculations through the canonical engineering facade and
`EngineeringResult`; it is not a replacement for field or regulatory
engineering review.

## Release-candidate status

This branch is being validated as a release candidate. The release gate is
`python verify_release.py`; it must be run on the target Python environment
before distribution. The application does not bundle external AI models,
licensed engineering packages, or field-certification data.

## Requirements and quick start

- Python 3.10, 3.11, 3.12, or 3.13
- A writable per-user data directory
- A desktop session for the Qt UI; database/import/engineering tests are
  headless
- Runtime packages in `requirements.txt`

For a reproducible install:

```bash
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-lock.txt
python -m app
```

An installed wheel exposes the same launcher as `drillmaster`. See
[DEPLOYMENT.md](DEPLOYMENT.md) for Windows and release-build instructions.

## Runtime paths and configuration

DrillMaster never needs write access to its source or installation directory.
The central path configuration is in `core/runtime_config.py`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `DRILLMASTER_DATA_DIR` | Root for mutable user data | OS user-data directory |
| `DRILLMASTER_DB_PATH` | SQLite database; relative values are under the data root | `<data>/drillmaster.db` |
| `DRILLMASTER_LOG_DIR` | Rotating application logs | `<data>/logs` |
| `DRILLMASTER_BACKUP_DIR` | Automatic backups | `<data>/backups` |
| `DRILLMASTER_AI_SETTINGS_PATH` | Selected local-AI model settings | `<data>/config/ai_settings.json` |
| `DRILLMASTER_MAPPING_MEMORY_PATH` | User-confirmed mapping memory | `<data>/config/mapping_memory.json` |
| `DRILLMASTER_STANDARDS_PATH` | User operational-standard overrides | `<data>/config/operational_standards.json` |
| `DRILLMASTER_ENV` or `DRILLMASTER_ENVIRONMENT` | `production`, `prod`, `test`, or development | `development` |
| `DRILLMASTER_ADMIN_PASSWORD` | Production bootstrap admin password | required in production on an empty database |
| `DRILLMASTER_USER_PASSWORD` | Production bootstrap engineer password | required in production on an empty database |
| `DRILLMASTER_VIEWER_PASSWORD` | Production bootstrap viewer password | required in production on an empty database |
| `DRILLMASTER_AUTO_LOGIN` | Development/test convenience only | disabled |

Production bootstrap passwords must be supplied through the deployment secret
mechanism, never committed to a file or printed in logs. Development fixture
passwords are rejected in production. Production requires bcrypt and stores passwords only as salted bcrypt hashes;
development-only fallback hashing must not be used for production data. Do not
treat a local SQLite database as an encrypted secrets store.

## Database, migrations, backup, and recovery

The default database is a per-user SQLite file. On first initialization the
schema is created and `schema_version` is recorded. Existing databases receive
only the additive, idempotent migrations in `DatabaseManager`; migration
errors fail startup rather than allowing a partially upgraded database to run.
The current schema version is `1`.

Use the in-application Backup action or the configured automatic backup. The
backup uses SQLite's backup API, includes WAL state, and retains ten automatic
backups. Before an upgrade, create an external copy and verify that a backup
opens in a separate DrillMaster data directory. Restore by stopping the
application, replacing the configured database with the verified backup, and
starting again. Backups are not encrypted by DrillMaster; protect their
filesystem and access permissions.

## Optional local AI

AI-assisted workbook mapping is **disabled by default**. Set
`DRILLMASTER_AI_IMPORT=1`, optionally set `DRILLMASTER_AI_MODEL`, and run an
Ollama service at `DRILLMASTER_OLLAMA_URL` (default
`http://127.0.0.1:11434`) to opt in. Capability checks are local, bounded by a
timeout, and return `disabled`, `ollama-unavailable`, or
`model-not-installed` without blocking deterministic imports. The
`core.optional_capabilities` detector reports Ollama, installed Qwen models,
and MinerU package presence without network access unless an explicit probe is
requested. AI proposals are
validated against the canonical field registry and are advisory; they never
save data or replace engineering formulas.

Qwen models are not bundled. Cloud-labelled models in the catalog require the
operator's own Ollama access and are not enabled by DrillMaster. MinerU is not
a required runtime and no MinerU binary/model is bundled. Optional PDF
extraction packages are listed separately in `requirements-optional.txt`.

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

## Validation and release commands

Run from the repository root:

```bash
python -m pytest -ra
python verify_release.py
python -m compileall -q core dialogs tabs tests
python -m py_compile app.py run.py main_window.py verify_release.py
python -m pip wheel . --no-deps --wheel-dir dist
python -m ruff check .
git diff --check
```

`verify_release.py` performs a compile check, dynamic pytest collection, and
the complete configured pytest suite. It rejects pytest failures and errors;
its output is the authoritative count for a release record.

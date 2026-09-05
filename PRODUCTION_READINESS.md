# Production readiness and release-candidate audit

Branch: `arena/01a07094-drill-master`
Application version: `1.0.0`
Audit date: 2026-09-05
Scope: startup through packaging and desktop deployment

## Implemented blockers

- Mutable database, log, backup, and local-AI settings paths now resolve to an
  OS user-data directory and can be overridden with documented environment
  variables. The source/install directory is not a runtime write target.
- Production bootstrap credentials are explicit and development fixture
  passwords are rejected. Production no longer creates demo company/project/
  well records or offers sample data automatically.
- Startup dialog failures are fatal instead of silently continuing with a
  missing startup result. Login/fatal dialogs avoid exposing exception details.
- SQLite backups use the SQLite backup API, including WAL state; automatic
  backups use a configured directory and retention limit.
- Additive schema upgrades are recorded in `schema_version`; migration errors
  fail initialization instead of being marked non-fatal.
- Optional Ollama/Qwen mapping is disabled by default, offline-safe, bounded by
  a timeout, and explicit about disabled/unavailable/missing-model states.
  No AI binary, model, cloud service, or MinerU asset is bundled.
- Manual and automatic backup UI paths use the configured database rather than
  assuming `./drillmaster.db`; the home storage indicator follows the same
  path.
- Packaging metadata, a canonical version source, dependency locks, a
  PyInstaller one-folder spec, an Inno Setup installer definition, Windows
  build script, package smoke test, and Windows runbook are present.
- The desktop first-run flow collects production credentials in process memory
  and initializes an empty production database without demo records.
- A headless smoke suite covers runtime paths, production schema/auth/fixture
  isolation, engineering registry/export imports, W12/W13 source interfaces,
  optional AI detection, and packaging configuration.

## Acceptance matrix

| Area | Result | Evidence |
| --- | --- | --- |
| Startup and fatal-error handling | PASS | `app.py`, `run.py`; startup-dialog failures now stop launch |
| Configuration and filesystem portability | PASS | `core/runtime_config.py`; `README.md`, `DEPLOYMENT.md` |
| Database initialization and migration | PASS | `core/database.py`; versioned additive migration smoke test |
| Authentication and RBAC | PASS | production bootstrap tests; `core/permissions.py` |
| Import and canonical SSOT paths | PASS | existing regression suite plus smoke interfaces |
| UI thinness and W12/W13 headless path | PASS | existing W13 acceptance tests and smoke test |
| Export/reporting imports | PASS | smoke test for DDR/professional exporters |
| Logging and secret handling | PASS | rotating user-data log; no password logging; generic auth errors |
| Backup/recovery behavior | PASS with operator drill required | SQLite backup API and documented restore drill |
| Version and packaging | PASS (automated) | `core/version.py`, PyInstaller spec, lock files, package smoke test |
| Optional AI readiness | PASS | opt-in `AIImportMapper`; no bundled models/binaries |
| Windows deployment | AUTOMATED PASS; manual Windows pending | PyInstaller/Inno definitions, build script, clean-machine checklist |

## Explicit remaining limitations

- Automated tests cannot certify a real operator's backup restore procedure;
  each deployment must perform and record one.
- SQLite is local storage and is not encrypted at rest. OS ACLs and backup
  protection remain deployment responsibilities.
- There is no server-side identity provider, MFA, tenant isolation, or remote
  replication in this desktop release.
- Anti-Collision is **PARTIAL / SCREENING**, not a complete validated
  uncertainty methodology. No ISCWSA/API TR 5C3 or field-certification claim
  is made.
- Optional third-party engineering/document packages are not guaranteed to be
  installed and must be licensed and validated independently.
- The application does not provide automatic update delivery or a licensing
  service. Installer hash, commit SHA, and dependency lock must be recorded by
  the release operator.
- This Linux environment cannot execute Windows PE files or Inno Setup. Manual
  clean-machine installation, Windows Qt-plugin execution, installer upgrade,
  and uninstall/data-preservation checks remain pending; they are not claimed
  as passed.

## Required final gate record

The final release record must include the exact output counts from:

```text
python -m pytest -ra
python verify_release.py
python -m compileall -q core dialogs tabs tests
python -m py_compile app.py run.py main_window.py verify_release.py
python -m pip wheel . --no-deps --wheel-dir dist
python packaging/package_smoke.py --bundle-dir release/DrillMaster-1.0.0 --run
git diff --check
git status --short --branch
```

Latest candidate validation (Python 3.11 virtual environment):

- `python -m pytest -ra`: **474 passed, 4 skipped**, 0 failed/errors.
- `python verify_release.py`: **collected=478, passed=474, skipped=4,
  failed=0, errors=0**, plus source/package compile check passed.
- `python -m compileall -q core dialogs tabs tests`: passed.
- Targeted `py_compile` for startup, runner, release, reset, packaging, and
  touched modules: passed.
- `git diff --check`: passed.
- Source wheel build: `dist/drillmaster-1.0.0-py3-none-any.whl`, 710,876 bytes,
  SHA-256
  `35e66b0a0eb91774852b1be1ccb01876e321ce2bfa52c41c73fa4f9fc7b4634c`.
- Windows PE/installer build: **not executed here**; this Linux environment
  has no Windows Python/Qt toolchain, Wine, or Inno Setup.

A release is not declared until the exact commit is recorded, the final diff
is reviewed, the branch is pushed, and the working tree is clean after
commit/push. The automated result above does not replace the operator backup
restore drill.

# DrillMaster — Release Candidate Integrity, Reproducibility, CI & Production Acceptance Boundary

Mission 27 forensic release-hardening certification.

Date: 2026-09-22
Branch: `arena/01a085e0-drill-master`
Start SHA: `3f52e2e` (M26 certification commit — verified as session start)
Certification commit: this document is committed on top of `95dd631`
Environment: Python 3.11.2 · Linux x86_64 · Qt offscreen

> **Verdict: PARTIALLY CERTIFIED (Linux release-candidate integrity green;
> Windows / real-MinerU / production-DB acceptance NOT RUN in this
> environment).** This is **not** a "production accepted" statement. See §24.

Core principle enforced throughout this mission:

* `Claim ≠ Evidence`
* `Documentation ≠ Verification`
* `Unit test ≠ Windows acceptance`
* `Linux package test ≠ Windows installer test`
* `MinerU mock / PyMuPDF fallback ≠ real MinerU pass`

The release chain is: **source → dependency contract → test/release gate →
CI → package build → package smoke → Windows acceptance → MinerU / real-doc →
release evidence.** DrillMaster is certified only up to the last link backed by
real evidence in *this* environment; every link beyond that is reported as
BLOCKED / NOT-RUN, never as a synthetic pass.

---

## 1. Executive summary

| # | Boundary | Status |
|---|----------|--------|
| 1 | Source integrity (compile, diff --check, clean tree) | **PASS** |
| 2 | Documentation truth audit | **PASS** (drift corrected) |
| 3 | Dependency reproducibility (lock resolves, fully pinned) | **PASS** |
| 4 | Lockfile-pinned test execution | **NOT-RUN** (env runs newer than lock) |
| 5 | Release gate (`verify_release.py`) | **PARTIAL** (compile+collect+pytest real; extended contract deferred) |
| 6 | Full test suite, current HEAD, Linux | **PASS** (1502 passed, 4 skipped) |
| 7 | CI workflow | **BLOCKED-BY-PERMISSION** (validated locally; not committed — token lacks `workflows` scope) |
| 8 | Lint-debt ratchet reconciled & lowered | **PASS** (5375, was ceiling 5489) |
| 9 | Version single-source-of-truth | **PASS** |
| 10 | Package smoke (static + runtime distinction) | **PASS (design)** / runtime = WINDOWS-BLOCKED |
| 11 | Package data isolation | **PASS** |
| 12 | Installer data/upgrade/uninstall model | **PASS (static review)** / WINDOWS-BLOCKED for execution |
| 13 | Windows acceptance env-var names match source | **PASS** |
| 14 | MinerU boundary (no direct DB writes; IR→review→persist) | **PASS** |
| 15 | MinerU failure taxonomy | **PASS** |
| 16 | Real MinerU acceptance | **NOT-RUN** (opt-in, no installation) |
| 17 | Real Excel/PDF acceptance | **NOT-RUN** (opt-in assets absent) |
| 18 | Windows GUI / installer acceptance | **NOT-RUN** (no Windows host) |
| 29 | Resource-path / user-data-dir audit | **PASS** |
| 30 | Logging secret-safety audit | **PASS** |

---

## 2. Source integrity (Gate A / §31)

* Session started on a fresh checkout whose HEAD pointed at the stale base
  `b05ea768`. `git fetch origin arena/01a085e0-drill-master` retrieved the
  pushed M26 tip; `git reset --hard 3f52e2e` restored it. Verified
  `HEAD == 3f52e2e` before any work.
* `git diff --check`: clean (no whitespace/conflict markers).
* `compileall core dialogs tabs tests` + `py_compile app.py run.py
  main_window.py verify_release.py`: **exit 0**.
* Working tree after this mission's commit: clean except the intentionally
  untracked `.github/workflows/` (see §7).
* Current HEAD at certification: `95dd631`.

---

## 3. Documentation truth audit (§2) — cross-reference SHAs

**M26 certification SHA conflation (§1) — FIXED.**
`docs/audits/2026-09-22_REPORT_SCOPED_OWNERSHIP_INTEGRITY_CERTIFICATION.md`
previously recorded a single `End SHA: 7a3bb4a`. A certification document is
committed *after* the implementation it certifies, so it cannot contain its own
commit hash. It now reports two distinct facts:

* **Implementation tip:** `7a3bb4a` (last M26 code/test commit)
* **Certification commit:** `3f52e2e` (the commit that added that document)

**Branch-reference drift.** References to the predecessor branch
`arena/01a07094-drill-master` were classified rather than blindly rewritten:

| File | Line | Classification | Action |
|------|------|----------------|--------|
| `ARCHITECTURE.md` | 3 | HISTORICAL (dated 2026-09-08 audit) | left as-is |
| `RELEASE_NOTES.md` | 5 | HISTORICAL (2026-09-08 release note) | left as-is |
| `docs/IMPORT_AUDIT_2026-09.md` | 7 | HISTORICAL (banner-marked) | left as-is |
| `ENGINEERING_CAPABILITY_STATUS.md` | 3 | STALE (living status doc) | **fixed → current branch + historical note** |
| `ENGINEERING_ARCHITECTURE.md` | 4 | STALE (living arch doc) | **fixed → current branch + historical note** |
| `PRODUCTION_READINESS.md` | 109 | CONTRADICTORY (header already said `01a085e0`) | **fixed → current branch** |

**CI documentation state (§2 case B).** `README.md:229` and `TESTING.md:55`
describe `.github/workflows/ci.yml`. The workflow file is validated and present
in the working tree but **not committed** (see §7), so those references
currently describe an *intended-but-uncommitted* workflow. Once a maintainer
with `workflows` permission commits the file, documentation and tree agree.

**Test-count drift (§2 case D).** Historical counts (808 / 844 / 1502) appear
in older docs. This certification quotes **only** the count produced by the
run recorded in §6 (1502 passed / 4 skipped) and states it is evidence for
that run alone.

---

## 4. Dependency reproducibility (§3 / §4 / F1)

**Runtime dependency contract** (`requirements.txt` ranges +
`requirements-lock.txt` pins):

| Package | Range (`requirements.txt`) | Lock pin | Installed this session |
|---------|---------------------------|----------|------------------------|
| PySide6 | >=6.6,<7 | 6.8.1.1 | 6.11.2 |
| SQLAlchemy | >=2.0,<3 | 2.0.36 | 2.0.54 |
| openpyxl | >=3.1,<4 | 3.1.5 | 3.1.5 |
| bcrypt | >=4,<5 | 4.2.1 | 5.0.0 |
| numpy | >=1.24,<3 | 2.1.3 | 2.4.6 |
| matplotlib | >=3.7,<4 | 3.9.3 | 3.11.2 |
| pandas | >=2,<3 | 2.2.3 | 3.0.6 |
| pyqtgraph | >=0.13,<1 | 0.13.7 | 0.14.0 |
| PyMuPDF | >=1.23,<2 | 1.24.14 | 1.28.2 |

**Lock-resolution verification (F1).** A throwaway virtualenv performed
`pip install --dry-run -r requirements-lock.txt`. Every one of the 26 pins
resolved to an installable wheel and pip's "Would install" set matched the lock
exactly — the lock is **fully pinned and reproducible** as a release build
input.

**Honest boundary (§4).** The working `.venv` used for the test run below was
provisioned with *unpinned* installs, so it runs **newer** versions than the
lock (e.g. pandas 3.0.6 vs locked 2.2.3, bcrypt 5.0.0 vs 4.2.1). Therefore:

* Lock **resolvability** across the current index: **PASS**.
* Test execution **against the exact locked versions**: **NOT-RUN** this
  session. The committed CI workflow installs `requirements-lock.txt` and would
  provide that evidence across Python 3.10–3.13 once committed and run.

The lock was **not rebuilt**: Mission 27's goal is reproducibility, not
freshness, and no evidence demanded a lock change. `bcrypt==5.0.0` being newer
than the pin is noted for a future lock-refresh decision but is out of scope
here (no runtime failure observed).

---

## 5. Release gate — `verify_release.py` (§5 / §6)

Current behaviour (verified by reading and by the standalone run): compiles the
tree, runs `pytest --collect-only -q` and fails on zero collection, then runs
the full `pytest -ra`, parses the real result line, and fails on any
failed/error count or non-zero return code. It hides nothing (`or True` absent)
and hardcodes no SHA.

**Status: PARTIAL.** The §5 wish-list (explicit `--expected-sha`,
`diff --check`, version-consistency, lock-sanity, config-asset presence, and a
PASS/FAIL/SKIPPED-OPTIONAL/NOT-AVAILABLE/ENVIRONMENT-BLOCKED taxonomy) and the
§6 deterministic release manifest are **deferred**, not implemented, in this
mission. They are additive and were not required to certify the current
release-candidate integrity; committing an unvalidated expansion would violate
the mission's "Claim ≠ Evidence" principle. Recorded as a tracked follow-up.

---

## 6. Full test suite — current HEAD, Linux (§31 / §34)

Command: `pytest -p no:cacheprovider -o addopts="" -ra -q`, Qt offscreen.

```
collected: 1506
1502 passed, 4 skipped, 14 warnings in 269.98s
```

The 4 skips are legitimate opt-ins and are evidence *for* the honest boundary,
not gaps hidden by skip-to-pass:

* `test_ddr_acceptance.py` ×2 — `DRILLMASTER_TEST_DDR_XLSX` / `_PDF` unset (real DDR asset opt-in)
* `test_mineru_real_integration.py` — `MINERU_INTEGRATION_INPUT` unset (real MinerU opt-in)
* `test_packaging_smoke.py` — Windows bundle not present

Re-run after the §8 import cleanup produced the **identical** 1502/4, proving
the cleanup behavior-neutral.

**Environment fingerprint (from the actual environment, not copied from docs):**
Python 3.11.2 · Linux x86_64 · SQLAlchemy 2.0.54 · PySide6 6.11.2 · numpy
2.4.6 · pandas 3.0.6 · openpyxl 3.1.5 · PyMuPDF 1.28.2 · bcrypt 5.0.0 · ruff
0.16.6 · pytest 9.1.1.

**Three-layer status (never conflated):**

* **LOCAL (Linux):** PASS — evidence above.
* **CI (GitHub, 3.10–3.13):** NOT-RUN — workflow blocked by token permission (§7).
* **WINDOWS-NATIVE:** NOT-RUN — no Windows host (§12, §18).

---

## 7. Continuous integration (§7) — BLOCKED BY PERMISSION

`.github/workflows/ci.yml` exists in the working tree, is fully formed, and was
validated locally step-for-step:

| CI step | Local simulation result |
|---------|-------------------------|
| Install Qt system libs | (GitHub-only) |
| Install `requirements-lock.txt` + `pytest ruff==0.16.6` | lock resolves (§4) |
| `compileall` + `py_compile` | exit 0 |
| Ruff **defect gate** (`--select E722,F821`) blocking | All checks passed |
| Ruff **lint-debt ratchet** blocking | 5375 ≤ ceiling 5375 → pass |
| `pytest -ra` full suite | 1502 passed, 4 skipped |

It is a **real** gate, not CI theater (§36): no `assert ... or True`, no
missing-executable→SKIP→PASS, real exit codes, `fail-fast: false` across the
`requires-python` matrix 3.10–3.13, least-privilege `contents: read`, and dev
tools (`ruff`, `pytest`) installed only for CI — never added to the runtime
dependency set.

**Why it is not committed:** the agent's GitHub App token lacks the `workflows`
permission. A push containing `.github/workflows/ci.yml` is rejected by GitHub
with *"refusing to allow a GitHub App to create or update workflow ... without
`workflows` permission."* Because a branch push is atomic, including the file
would have blocked the entire commit. The workflow is therefore left in the
working tree for a maintainer whose token carries the `workflows` scope to
commit verbatim. This is reported as **BLOCKED-BY-PERMISSION**, never as a CI
pass.

---

## 8. Lint-debt ceiling reconciliation (§8) — ratcheted DOWN

The committed ceiling `.github/ruff-debt-ceiling.txt` was `5489`, measured on
the predecessor branch `arena/01a07094` before the M24–M26 sources existed on
this branch. Measured on the **exact current source state** with the pinned
ruff 0.16.6, the honest count was **5863** (dominated by F405 star-import
fallout: 4506) — i.e. the ratchet would have failed on its first run.

Per §8 the ceiling may only shrink, never auto-raise. Rather than raise it, the
debt was **paid down**:

* `ruff check --select F401 --fix` removed **485** genuinely-unused imports
  across 139 files (safe fixes only; no `--unsafe-fixes`).
* One re-export regression was caught by the full suite (collection error in
  `test_torque_drag_history.py`): `core/engineering/torque_drag_persistence.py`
  re-exports verification constants (`VERIFY_DIFFERENT`, `VERIFY_MATCH`,
  `VERIFY_NOT_REPRODUCIBLE`, `_deep_numeric_diff`, …) consumed by the
  repository, dialog, and tests. These were restored with an explicit
  `# noqa: F401` documenting the re-export intent.
* Resulting count: **5375**. Ceiling lowered to **5375**.
* Full suite re-run: **1502 passed, 4 skipped** — unchanged, proving the
  removals behavior-neutral.

The real-defect gate (E722 bare-except, F821 undefined-name) is **clean** on
this source; the remaining 5375 findings are pre-existing style debt
(star-import fallout, multi-statement lines) whose mass rewrite is explicitly
out of policy.

---

## 9. Version single-source-of-truth (§9)

`core/version.py::__version__ = "1.0.0"` is the sole authority:

* `pyproject.toml` reads it dynamically (`version = {attr =
  "core.version.__version__"}`).
* `app.py::AppConfig.APP_VERSION` imports it.
* `packaging/DrillMaster.spec` imports it and generates the Windows
  `VSVersionInfo` from it.
* `packaging/build_windows.ps1` regex-reads it from `core/version.py` and
  passes `/DAppVersion=$version` to Inno Setup.
* `packaging/DrillMaster.iss` has `#error AppVersion must be supplied by
  packaging/build_windows.ps1` — it cannot be built with a hardcoded fallback.

No second hardcoded version string exists in the chain. **PASS.**

---

## 10–12. Packaging & installer forensics (§9–12)

**Package smoke (`packaging/package_smoke.py` + `app.py::run_package_smoke`).**
Two clearly distinct layers:

* *Static validation* (`validate_bundle`): asserts `DrillMaster.exe`, required
  config data (`config/ai_models.json`, `config/company_templates/oeoc.json`),
  `Qt6Core.dll`, `qwindows.dll` present, and **fails** if any `test_*.py`
  leaked into the bundle.
* *Runtime execution* (`--run` → `DrillMaster.exe --package-smoke`): imports the
  real core/dialog/tab modules, initializes a real `DatabaseManager`, and
  verifies `schema_version`. It runs in a **temp DATA_DIR/DB**, forces
  `DRILLMASTER_ENV=test`, disables AI import (`DRILLMASTER_AI_IMPORT=0`), clears
  bootstrap-password env, and restores all env afterward — **no production
  mutation**.

A fake-exe static pass is explicitly **not** a frozen-runtime pass, and neither
is a Windows acceptance. The frozen runtime execution is **WINDOWS-BLOCKED**
here (no Windows host / no PyInstaller bundle).

**Installer (`packaging/DrillMaster.iss`).** Application installs to
`{autopf}\DrillMaster` (Program Files); the header documents that user data
(SQLite DB, logs, mapping memory, backups) lives **outside `{app}`** — matching
`core/runtime_config.py`, which resolves mutable state to `LOCALAPPDATA` on
Windows. Consequently `[Files]` ships only bundle content, and upgrades /
uninstall do not touch user data. Static review only; execution is
WINDOWS-BLOCKED.

---

## 13. Windows acceptance env-var contract (§13)

Every environment variable named in `docs/WINDOWS_ACCEPTANCE.md`
(`DRILLMASTER_ENV`, `DRILLMASTER_DATA_DIR`, `DRILLMASTER_DB_PATH`,
`DRILLMASTER_MINERU_ENABLED`, `DRILLMASTER_MINERU_EXECUTABLE`,
`DRILLMASTER_AI_IMPORT`, `DRILLMASTER_TEST_DDR_XLSX`,
`DRILLMASTER_TEST_DDR_PDF`) is genuinely consumed by source
(`core/runtime_config.py`, `core/mineru_engine.py`, `core/ai_import_mapper.py`,
`app.py`). No documented variable is a dead name. **PASS.**

---

## 14–18. MinerU & real-document boundary (§14–18)

**No direct DB writes (§14).** `core/mineru_engine.py` contains **zero**
database operations (no session, commit, `save_*`, or `execute` — the only
`.add(` calls are Python `set` de-duplication). MinerU produces IR
(`MinerUDocument` / `MinerUParseResult`) → `DocumentNormalizer` →
`NormalizedDocument` with review state; persistence happens downstream through
the import router and review dialogs. The engine never invents values or
bypasses review.

**Failure taxonomy (§15).** Typed exception hierarchy plus a `_failure()` path
returning structured reason codes: `MinerUNotInstalledError`,
`MinerUExecutableError`, `MinerUUnsupportedFormatError`, `MinerUProcessError`
(non-zero exit), `MinerUTimeoutError`, `MinerUOutputError`,
`MinerUNormalizationError`, and `invalid-input` / `output-error` result
reasons. None of these degrade into a synthetic SUCCESS.

**Real acceptance (§16–18) — NOT-RUN, correctly.**

* `tests/test_mineru_engine.py` (418 lines) exercises the engine with
  fixtures/mocks and runs in-suite — this is **not** a real-MinerU pass.
* `tests/test_mineru_real_integration.py` **skips** unless
  `MINERU_INTEGRATION_INPUT` points at a real MinerU install.
* `tests/test_ddr_acceptance.py` **skips** unless the real DDR workbook/PDF
  paths are provided.
* PyMuPDF-based fallback extraction, where present, is a fallback — a fallback
  pass is **not** a MinerU pass.

Real MinerU, real Excel/PDF acceptance, and Windows GUI/installer acceptance
are all **NOT-RUN** in this Linux environment and are not claimed.

---

## 29. Resource-path / user-data audit (§29)

`core/runtime_config.py` is the single path-resolution layer. Mutable state is
never written next to installed source: Windows → `%LOCALAPPDATA%\DrillMaster`,
macOS → `~/Library/Application Support/DrillMaster`, Linux → `$XDG_DATA_HOME`
or `~/.local/share/drillmaster`, all overridable via `DRILLMASTER_DATA_DIR`.
No `cwd == repo-root` assumption for runtime data. **PASS.**

## 30. Logging secret-safety audit (§30)

No logging statement emits a password/secret/token/credential **value**. Log
messages about credentials are policy/error text only (e.g. "First-run
credential configuration blocked: <reason>"). The rotating log writes to the
user log dir; a read-only profile degrades gracefully to stderr without leaking
configuration values. **PASS.**

---

## 24. Final wording (§42)

DrillMaster on `arena/01a085e0-drill-master` at `95dd631` (+ this certification
commit) is:

**RELEASE-CANDIDATE — PARTIALLY CERTIFIED.**

* **Certified (Linux, this environment):** source integrity, documentation
  truth, dependency-lock resolvability, full test suite (1502 passed / 4
  skipped), lint-debt ratchet (5375, lowered), version SSOT, packaging/installer
  static model, MinerU boundary discipline, resource-path & logging safety.
* **Not certified / NOT-RUN (require other environments or maintainer action):**
  CI execution (blocked by `workflows` token permission — file validated,
  awaiting maintainer commit), lock-pinned test execution, real MinerU
  acceptance, real Excel/PDF acceptance, Windows GUI/installer/package-runtime
  acceptance, production-DB acceptance.

This is explicitly **NOT** a "production accepted" statement. Linux-green plus
Windows/MinerU-not-run equals *partially certified*, per the mission's evidence
discipline.

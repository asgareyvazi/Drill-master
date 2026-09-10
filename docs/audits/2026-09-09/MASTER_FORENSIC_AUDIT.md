# DrillMaster — Master Forensic Audit (2026-09-09)

Independent forensic re-inspection of `asgareyvazi/Drill-master` at the start of this
engineering session. **Nothing in this document is copied from prior reports; every
claim below was re-verified against the current working tree with the commands shown.**

> **2026-09-10 re-audit:** this session's output was independently re-verified in
> `../2026-09-10_FORENSIC_REAUDIT.md`. Baseline and P0 fixes reproduced; two
> corrections issued there: the schematic auto-generate path still fabricates data
> (the no-fabrication evidence cited below was misattributed to a trajectory test),
> and the inventory ledger violates zero≠missing in its live path.

---

## 1. Git / environment facts

| Item | Value | Evidence |
| --- | --- | --- |
| Branch | `arena/01a085e0-drill-master` | `git branch --show-current` |
| HEAD | `b05ea768398184bdaa299eeae413edf1622137b1` "Add dirty save boundaries and protect legacy BHA maps" | `git rev-parse HEAD` |
| Working tree | clean at session start | `git status --short` (empty) |
| History | shallow clone, 2 grafted commits (`02053eb` upload → `b05ea76`) | `git log --all`, `.git/shallow` |
| Claimed commit `aa6fca728075df933c44bc0ea3f063715483397b1` | **DOES NOT EXIST** | `git cat-file -t aa6fca7…` → `fatal: Not a valid object name` |
| Prior claim "817 passed, 6 skipped" | **NOT REPRODUCIBLE** in this environment (see baseline below) | full pytest run |

Consequence: the implementation described by the previous Arena execution is not
present here. It must not be assumed, referenced, or "restored from memory".

### Host capabilities (this sandbox)

* Python 3.11.2; project venv at `.venv` built from `requirements-lock.txt`
  (PySide6 6.8.1.1, SQLAlchemy 2.0.36, pandas 2.2.3, …) + `pytest 9.1.1`, `ruff`.
* `apt`/Debian mirrors and conda hosts are **not reachable**; GitHub and PyPI are.
* System `libGL.so.1`, `libEGL.so.1`, `libxkbcommon.so.0`, `libdbus-1.so.3` were
  **missing**, so `import PySide6.QtWidgets` failed with `ImportError: libGL.so.1`.
  Minimal no-op stub libraries (return 0/NULL = "capability absent") were generated
  from the exact undefined-symbol sets of the installed Qt binaries, with ELF symbol
  versions (`V_0.5.0` for xkbcommon, `LIBDBUS_1_3` for dbus). With
  `LD_LIBRARY_PATH=/home/user/qt-libs QT_QPA_PLATFORM=offscreen` the full offscreen
  Qt stack works: widgets, raster rendering (`QWidget.grab()`), font metrics, QtSvg,
  QtPrintSupport, QtDBus. Script: `tools/qt_headless_env.sh`.
  These stubs are an **environment shim for this sandbox only** — CI runners with a
  normal `libgl1` package must not use them. Anything that genuinely requires OpenGL
  would not work here and must be reported as an environment limitation.

---

## 2. Real baseline (2026-09-09)

Commands (venv `python` = `.venv/bin/python`):

```
python -m compileall -q core dialogs tabs tests        # PASS
python -m py_compile app.py run.py main_window.py verify_release.py   # PASS
ruff check core dialogs tabs tests                     # FAIL — 5550 findings (see §5)
QT_QPA_PLATFORM=offscreen LD_LIBRARY_PATH=/home/user/qt-libs \
  python -m pytest -ra                                 # see counts
```

### pytest baseline (single process, default ordering)

```
Collected: 792
Passed:    779
Failed:      7
Errors:      0
Skipped:     6
XFailed:     0
XPassed:     0
Duration:  ~180 s
```

Note: `pyproject.toml` sets `addopts = "-q"`; passing an extra `-q` on the command
line silences the final count line (pytest treats it as `-qq`). Baseline captured
without the extra `-q`.

### The 7 baseline failures — root causes (each reproduced and explained)

1. `tests/test_import_repairs.py::…test_missing_nozzle_number_reaches_db_as_null_without_crashing`
   — stale test double: `CaptureDB.save_drilling_parameters(self, payload)` does not
   accept the `session` keyword that production `DatabaseManager.save_drilling_parameters(
   data, session=None)` (`core/database.py:4191`) now passes.
2. – 7. Six tests in `tests/test_real_oeoc_golden.py`
   (`test_db_stores_2400_row`, `test_mud_chemistry_persists`,
   `test_report_header_volumes_map_to_mud`, `test_bit_run_fields_map`,
   `test_forecast_persists`, `test_do_import_creates_well_and_report`):
   `TypeError: object.__new__(ExcelImportDialog) is not safe, use
   ExcelImportDialog.__new__()`.

   **Full pollution chain (proven with a `sys.meta_path` import tracer):**
   `tests/test_import_repairs.py` imports `dialogs.excel_import_dialog` directly;
   once real PySide6 is importable (it is, with the sandbox shims), real
   `PySide6.QtWidgets` enters `sys.modules` permanently. Later,
   `tests/test_real_oeoc_golden.py::_QtStubs` only installs its fake PySide6 modules
   "if not already imported", so `ExcelImportDialog` is then built on **real Qt**
   classes; `object.__new__()` on a shiboken type raises `TypeError`.
   The whole file passes in isolation (36 passed) because the fakes are installed
   when PySide6 is absent. `tests/test_import_architecture.py:193` uses the same
   unsafe pattern and only survives because it runs alphabetically before the
   polluting import.

   **Conclusion:** these golden tests have never run against real Qt in any recorded
   run; the "passing" numbers from earlier environments were produced with Qt fakes.

### The 6 baseline skips

* 2 × `test_ddr_acceptance` — opt-in env vars `DRILLMASTER_TEST_DDR_XLSX/PDF` not set
  (legitimate opt-in design).
* 1 × `test_mineru_real_integration` — `MINERU_INTEGRATION_INPUT` not set (legitimate).
* 1 × `test_packaging_smoke` — Windows bundle absent (legitimate).
* **2 × `test_release.py:30/144` — "No display — PySide6 requires libGL" — NOT
  legitimate.** The skip keys off the `DISPLAY` environment variable, not off actual
  Qt capability. Proof of harm: the skipped test
  `test_all_core_modules_importable` contains
  `from core.validators import validate_rows`, which fails with
  `ImportError: cannot import name 'validate_rows' from 'core.validators'`
  — a real import defect permanently hidden by the DISPLAY skip in every recorded
  headless run. `core.hierarchy_operations` (also imported by that test) is the only
  module in its import list that genuinely needs Qt; all others import headless.

---

## 3. P0 findings from the independent Cloud audit — re-verification

| # | Claim | Verdict | Evidence |
| --- | --- | --- | --- |
| 1 | Undefined `CodeResolver` in `core/profile_import_engine.py` | **CONFIRMED (real bug)** | `ruff --select F821` → `core/profile_import_engine.py:800: Undefined name 'CodeResolver'`. The only import is function-local inside a *different* method (line 597, `_configure_workbook_code_catalog`). At line 800 (`_extract_time_logs` path) the `NameError` is swallowed by `except Exception: contractor = ""` — NPT contractor data is silently lost. `CodeResolver` (with `guess_contractor`) exists in `dialogs/smart_template_dialog.py:1330/1492`. |
| 2 | Wrong `ImportValidator` import in `tests/test_release.py` | **PARTIALLY CONFIRMED** | `tests/test_release.py:41/130` import `core.import_quality.ImportValidator` — that class exists and the call signature matches. The *real* defect in the same test is line 40: `from core.validators import validate_rows` — no such name exists in `core.validators` (ImportError). |
| 3 | `object.__new__(ExcelImportDialog)` unsafe | **CONFIRMED** | 7 sites fail under real Qt (see §2); 1 further latent site at `tests/test_import_architecture.py:193`. |
| 4 | DISPLAY-based skipping hides real failures | **CONFIRMED with proof** | See §2 — the hidden `validate_rows` ImportError. |
| 5 | ~40 bare `except:` | **CONFIRMED: exactly 40** | `ruff check --select E722 core dialogs tabs main_window.py app.py` → 40 (14 in `core/`, 9 in `dialogs/`, 17 in `tabs/`). Full list captured; triage in SCOPE_MATRIX. |
| 6 | Two incompatible `ImportValidator` classes | **CONFIRMED** | `core/validators.py:538` ("Legacy wrapper … delegates to import_quality module" — **the docstring is false, it does not delegate**) vs `core/import_quality.py:671` (authoritative; used by `core/ddr_import_service.py:14` and `dialogs/excel_import_dialog.py:36`). Incompatible signatures: `(rows, required_fields=())` vs `(rows, record_type="", sheet="Import")`. |
| 7 | `core/repositories/` disconnected | **CONFIRMED** | 7 repository modules + `base.py` exist; no production module imports them (only `tests/test_import_architecture.py` exercises a `memory_manager` fixture). Verified by grep across `core/ dialogs/ tabs/ main_window.py app.py`. |
| 8 | Very large files | **CONFIRMED** | `wc -l`: `core/database.py` 8575, `tabs/w13_Engineering_Calculator.py` 4275, `main_window.py` 2975 (also flagged by `test_file_sizes_reasonable` warning). |
| 9 | Many wildcard Qt imports | **CONFIRMED** | `ruff --select F403` → 92 files/sites; F405 (undefined names from star imports) 4382. |
| 10 | No CI workflow | **CONFIRMED** | no `.github/` directory in the tree. |
| 11 | Manually recorded test counts in docs | **CONFIRMED** | e.g. `TESTING.md`/`PRODUCTION_READINESS.md` cite counts; they do not match the 792/779/7/6 reality. |

---

## 4. Actual domain model (as built)

Source of truth: `core/database.py` (schema version **2**; `DatabaseManager.schema_version`;
`schema_version` table consulted by `_raw_schema_version`, migrations in
`_migrate_*` methods — see `git grep _migrate` for the inventory).

Hierarchy actually persisted:

```
Company → Project → Well → Section → DailyReport
```

* **There is no `Wellbore` table.** "Wellbore" exists only as a UI/service concept
  (e.g. `tabs/w3b_wellbore_schematic_tab.py`, `core/wellbore_schematic_engine.py`,
  `WellboreSchematic` rows keyed by `well_id`). Answer to the §10 question:
  **B — abstraction, not a persistent domain entity.**
* `Well` (line 166): identity = `id` + `name` + unique `code`; `rig_name`,
  `report_no`, supervisors, etc. are denormalised report-header snapshot fields on
  the well row. A rig is an attribute, not identity — consistent with the
  well-centric goal at the *persistence* level.
* `Section` (237): `well_id` FK; `DailyReport` (258): `well_id` FK + **nullable**
  `section_id` FK — DDRs may exist without a section; no DB-level constraint that
  `report.section.well_id == report.well_id`.
* Longitudinal runs are stored **per-report as JSON**:
  `BHAReport.bha_data_json` (721), `BitReport.bit_records_json` (702),
  `DownholeEquipment.equipment_data_json` (739), `TripSheetEntry`,
  `WellboreSchematic.layers_json/elements_json` (554, per well with nullable
  `report_id`). This is the "report_id + JSON" pattern the architecture goal
  warns about; R19 protection for legacy multi-configuration BHA JSON lives in
  `core/legacy_bha.py` and `tests/test_r18_r19_save_preservation.py` (passing).
* Inventory: `BulkMaterials` (871) daily rows (initial/received/used/current),
  `FuelWaterInventory` (831); ledger math (Opening + Received + Adjusted − Used −
  Returned; Opening(day+1)=Closing(day)) in `core/mud_ledger.py` — service-level,
  not a transaction table.
* Cost: `CostRecord` (1675): `planned_cost` / `actual_cost` / `variance`, `afe_number`,
  `cost_type`, `status` — Actual/AFE/Variance present; no explicit Estimate/Forecast
  column (forecast text lives on `DailyReport.forecast`).
* Planning: `PlannedActivity` (1432), `WellPlan` (1473) — PLAN side exists;
  `core/actual_vs_plan.py` compares against FACT.
* KPI: **no canonical KPI service.** Formulas are computed independently in
  `core/operations_intelligence.py` (avg_rop, npt_percent …), `tabs/w12_Analysis.py`
  (`calculate_kpis`, SQL aggregates at line 1211+), and `tabs/home_tab.py`
  (project progress). Details in `KPI_MATRIX.md`.
* `SelectionManager` (`core/selection_manager.py`): Qt-signals singleton tracking
  well → section → report. Parent-change correctly clears stale children
  (`select_well` clears section+report; `select_section` clears report).
  **Gap:** no ownership validation — `select_section()` will happily accept a
  section from a different well than the currently selected well.
* Import stack: `dialogs/excel_import_dialog.py` (`ExcelImportDialog(QDialog,
  DDRImportService)`) → `core/ddr_import_service.py` (atomic `_do_import`, staged
  persistence with rollback, `save_outcome` public statuses) → `core/import_quality.py`
  (authoritative `ImportValidator`, `TimeLogValidator`, duplicates, review items) →
  `core/profile_import_engine.py` (workbook profile extraction) →
  `core/excel_intelligence.py` / `core/universal_import.py` / `import_router.py`.
  Provenance: `core/lineage.py`, `ReportRevision` snapshots, `header_snapshot` JSON.

---

## 5. Structural quality snapshot (ruff, project config)

```
F405 4382 | F401 458 | E702 327 | E701 146 | F403 92 | E722 40 | F841 40
E741 22 | F541 17 | F811 10 | E712 10 | E703 2 | F402 1 | F601 1 | E711 1 | F821 1
```

The single F821 is the CodeResolver bug (§3.1). The E722×40 list is fully enumerated
in `SCOPE_MATRIX.md` §B. F403/F405 are dominated by `from PySide6.QtWidgets import *`
patterns; conversion is opportunistic, not a one-shot rewrite.

---

## 6. What this session changes (Phase plan reference)

Per the master handoff §37, this session executes in order:

* **Phase 0** — this document + `SCOPE_MATRIX.md` + `KPI_MATRIX.md` +
  `PRODUCTION_ACCEPTANCE.md` (all evidence-based).
* **Phase 1** — the confirmed P0s: CodeResolver NameError, ImportValidator
  duality + phantom import, `object.__new__` test construction, DISPLAY-based
  skipping, stale test double. Each fix carries a regression test.
* **Phase 2+** — see SCOPE_MATRIX for per-area status; domain work beyond Phase 1
  is scheduled, tested and reported honestly (PASS / BLOCKED / NOT VERIFIED /
  OUT OF SCOPE), never claimed without evidence.

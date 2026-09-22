# Mission 26 — Report-Scoped Ownership, Snapshot Integrity & Cross-Scope Contamination Hardening

Date: 2026-09-22
Branch: `arena/01a085e0-drill-master`
Start SHA: `8e176fa` (M25 tip — verified)
End SHA: `7a3bb4a`
Parent of start: `0527e95` (M24)
Environment: Python 3.11.2 · SQLAlchemy 2.0.54 · openpyxl · PySide6 6.11.2 · Qt offscreen · Linux x86_64

This is a **forensic hardening / production-safety mission**, not a feature
sprint. Core principle enforced throughout:

> If you cannot prove from canonical data that a record belongs to this report /
> section / wellbore, do not attribute it. Do not confuse Unknown with Zero,
> Ambiguous with the first row, or Whole-Well with the selected bore.

---

## A. Repository identity

| | |
|---|---|
| Branch | `arena/01a085e0-drill-master` |
| Start SHA | `8e176fa` |
| End SHA | `7a3bb4a` |
| Parent | `0527e95` (M24) |
| Dirty files at start | none tracked (working tree already matched M25 content) |
| Untracked at start | `.github/` only |
| Remote relation | pushed to `origin/arena/01a085e0-drill-master` |

**Gate A** — fresh shallow clone landed HEAD at the base pointer `b05ea768`
(1-commit local history); the authoritative remote tip was `8e176fa` (M25).
Reconciled with `git fetch origin arena/01a085e0-drill-master` +
`git reset --hard 8e176fa`. `.venv` and `/home/user/qt-libs` (both
snapshot-excluded) rebuilt this session.

### CI status (evidence-based)

- `.github/ruff-debt-ceiling.txt` **IS** committed in HEAD.
- `.github/workflows/ci.yml` is **untracked / NOT PRESENT IN THE COMMITTED
  TREE** (`git ls-tree -r HEAD .github/workflows` is empty). Per the mission
  rule it was neither staged nor deleted.
- **CI NOT VERIFIED** — no committed workflow, and the runner is not exercised
  here.

---

## B. Mission 25 verification (from source + git, not the Arena report)

All six reported M25 commits are present in HEAD: `74e1246`, `dd34ad9`,
`302c253`, `bba9324`, `2949d5b`, `8e176fa`. Verified in source:

| Claim | Verified in source | Test kind |
|---|---|---|
| W12 `get_today_data` legacy fallback gated on report unambiguity | YES (`tabs/w12_Analysis.py`) | REAL DB + method bound to lightweight stub (Qt-free) |
| Import→selection carries bore (`_targeted_refresh`→`select_full_context`) | YES (`main_window.py`) | pure-logic + subprocess Qt UI smoke |
| `get_or_create_wellbore` identity reconciliation | YES (`core/database.py`) | REAL DB |
| Report-engine whole-well scope metadata | YES (`core/report_engine.py`) | REAL DB, HTML/Excel byte assertions |
| Whole-well UI labels (W10/W11/W16) | YES | subprocess Qt smoke |

Test-double note (§1-F): the W12 analytics tests bind the **real** production
methods (`get_today_data`, `get_npt_data`, `_scope_reports_query`, …) onto a
lightweight non-Qt carrier against a **real in-memory DatabaseManager**. This is
REAL-production-method + REAL-database, not a stub of the logic — but it is NOT a
full-MainWindow end-to-end path. The MainWindow signal path is covered
separately by subprocess Qt smoke tests.

---

## C. Ownership inventory (derived from source, 49 models)

Every mapped model carrying a scope key, with nullability
(`!` = NOT NULL, `N` = nullable). Semantic role assigned from the caller graph
and FK targets; `report_id` on 30 models is an FK onto `daily_reports.id`.

| Model | well_id | wellbore_id | section_id | report_id | Semantic role | Expected scope |
|---|---|---|---|---|---|---|
| Well | — | — | — | — | WELL_LEVEL_ENTITY | well |
| Wellbore | ! | — | — | — | WELLBORE_ENTITY | bore |
| Section | ! | N | — | — | SECTION_ENTITY | section (bore via wellbore_id) |
| DailyReport | ! | N | N | — | REPORT_ENTITY | report (bore via wellbore_id/section) |
| DrillingParameters | ! | — | — | N | REPORT_SNAPSHOT | report; bore via report chain |
| MudReport | ! | — | — | N | REPORT_SNAPSHOT | report |
| CementReport | ! | N | — | N | REPORT_SNAPSHOT | report/section |
| CasingReport | ! | N | — | N | REPORT_SNAPSHOT | report/section |
| WellboreSchematic | ! | — | — | N | REPORT_SNAPSHOT | report |
| TripSheetEntry | ! | N | — | N | REPORT_SNAPSHOT | report |
| SurveyPoint | ! | N | — | N | REPORT_SNAPSHOT / LONGITUDINAL | report |
| TrajectoryCalculation | ! | N | — | N | DERIVED_RESULT | report |
| TrajectoryPlot | — | — | — | N | DERIVED_RESULT | report |
| BitReport | ! | — | — | N | REPORT_SNAPSHOT | report; bore via report |
| BHAReport | ! | — | — | N | REPORT_SNAPSHOT | report; bore via report |
| DownholeEquipment | ! | — | — | N | REPORT_SNAPSHOT | report |
| FormationReport | ! | — | — | N | REPORT_SNAPSHOT | report |
| LogisticsPersonnel | ! | N | N | N | REPORT_SNAPSHOT | report |
| ServiceCompanyPOB | ! | N | N | N | REPORT_SNAPSHOT | report |
| FuelWaterInventory | ! | N | N | N | REPORT_SNAPSHOT | report (per-report inventory) |
| BulkMaterials | ! | N | N | N | REPORT_SNAPSHOT | report |
| InventoryItem | ! | N | N | N | REPORT_SNAPSHOT | report |
| TransportLog | ! | N | N | N | REPORT_SNAPSHOT | report |
| TransportNotes | ! | N | N | N | REPORT_SNAPSHOT | report |
| SafetyReport | ! | N | N | N | REPORT_SNAPSHOT | report |
| BOPComponent | ! | — | — | N | REPORT_SNAPSHOT | report |
| WasteRecord | ! | — | — | N | REPORT_SNAPSHOT | report |
| ServiceCompany | ! | N | N | N | REPORT_SNAPSHOT | report |
| ServiceNote | ! | N | N | N | REPORT_SNAPSHOT | report |
| MaterialRequest | ! | N | N | N | REPORT_SNAPSHOT | report |
| EquipmentLog | ! | N | N | N | REPORT_SNAPSHOT | report |
| SevenDaysLookahead | ! | N | N | N | REPORT_SNAPSHOT | report |
| NPTReport | ! | N | N | N | REPORT_SNAPSHOT | report |
| TimeDepthData | ! | N | N | N | DERIVED/LONGITUDINAL | report |
| ROPAnalysis | ! | N | N | N | DERIVED_RESULT | report |
| ActivityCode | ! | — | — | — | MASTER_REFERENCE (per well) | well |
| CostRecord | ! | — | — | — | WELL_LEVEL_ENTITY | well (no bore column — by design) |
| WellPlan | ! | — | — | — | WELL_LEVEL_ENTITY | well |
| PlannedActivity | ! | N | — | — | WELL/SECTION plan | well/section |
| OperationalProcedure | ! | N | — | — | WELL/SECTION entity | well/section |
| TimeLog24H | — | — | — | N | REPORT_SNAPSHOT | report |
| TimeLogMorning | — | — | — | ! | REPORT_SNAPSHOT | report |
| ApprovalAction / ReportRevision | — | — | — | ! | AUDIT_RECORD | report |
| CasingCalc / CementCalc / MSECalc / MudVolCalc / TorqueDragCalc / WellControlKillSheetCalc | N | — | — | — | DERIVED_RESULT (engineering) | well |

The engineering calculation records (well_id nullable) and the master-reference
tables are **out of scope** for the report-coherence invariant (no `report_id`).

---

## D. Findings

### F1 — Report-scoped ownership guard covered only 3 of 30 report-linked models (HIGH)

- **File / function:** `core/database.py` · `_enforce_ownership_integrity` /
  `_REPORT_SCOPED_WELL_MODELS`.
- **Old behavior:** the `before_flush` guard ran
  `_check_report_scoped_well_ownership` for a hand-maintained tuple of exactly
  three models (`BHAReport`, `BitReport`, `DownholeEquipment`).
- **Why it is wrong:** the check is a pure NON-CONTRADICTION check — it fires
  only when `report_id` is set and rejects only when the record's `well_id`
  disagrees with that report's `well_id`; a NULL `report_id` always passes. This
  is valid for **every** model whose `report_id` is an FK onto
  `daily_reports.id` (there is no legitimate role in which a record in well A
  names well B's report). 27 identically-shaped peers were unprotected.
- **Evidence:** a `DrillingParameters` row with `well_id = A` and
  `report_id =` (a well-B report) **committed successfully**; likewise
  `MudReport`, `SafetyReport`, `FormationReport`, `WellboreSchematic`,
  `TripSheetEntry`.
- **Fix (minimal):** derive the guarded set from the schema
  (`_discover_report_scoped_well_models`: NOT-NULL `well_id` + nullable
  `report_id` FK → `daily_reports.id`), computed lazily on first flush so it
  cannot drift behind new models. 30 models now protected on every save path.
- **Test:** `tests/test_report_scoped_ownership_m26.py` (25) — full-shape
  coverage; cross-well rejected **and rolled back**; same-well accepted; NULL
  `report_id` (well-level) accepted — parametrized across 8 representative peers.
- **Residual risk:** low. The guard is non-contradiction only; it never
  fabricates ownership and never rejects a NULL. Models without a `report_id`
  FitK to `daily_reports` are intentionally excluded.

### F2 — W12 legacy well+date fallback nondeterministic on ambiguous child rows (MEDIUM)

- **File / function:** `tabs/w12_Analysis.py` · `get_today_data`.
- **Old behavior:** the fallback gated only on the DailyReport count being 1,
  then did a bare `.first()` on child rows by `(well_id, report_date)`.
- **Why it is wrong:** with one report but two legacy child rows sharing that
  well+date, `.first()` is nondeterministic and silently hides the other row.
- **Evidence:** two `DrillingParameters` legacy rows (ROP 15 and 99) returned
  15 while hiding 99.
- **Fix:** `_unique_legacy_row()` resolves a legacy row only when exactly one
  exists; zero or >1 → UNKNOWN (None).
- **Test:** `test_w12_scope_leakage_m25.py::test_today_data_ambiguous_legacy_child_rows_stay_unknown`.

### F3 — W12 NPT NULL duration collapsed to fabricated zero (MEDIUM)

- **File / function:** `tabs/w12_Analysis.py` · `get_npt_data`.
- **Old behavior:** `h = log.duration or 0` summed a NULL duration as 0.0 into
  the total and category map, displayed as `0.00`.
- **Why it is wrong:** UNKNOWN NPT length becomes an indistinguishable fabricated
  zero.
- **Fix:** three-state — NULL → UNKNOWN (excluded from total/categories,
  entry hours `None` rendered `—`, counted in new `unknown_npt_count`); stored
  0.0 stays real.
- **Test:** `test_w12_scope_leakage_m25.py::test_npt_null_duration_is_unknown_not_zero`
  (A=2.0, B=NULL, C=0.0 → total 2.0, unknown 1).

### F4 — OperationsIntelligence current_depth fabricated 0.0 when unknown (MEDIUM)

- **File / function:** `core/operations_intelligence.py` · `analyze_well`,
  `_analyze_scope`.
- **Old behavior:** `current_depth = max(depths, default=0.0)`.
- **Why it is wrong:** a scope with reports but no known `depth_2400` reported
  0.0 m — a false fact contradicting the method's own no-fabrication comment; it
  also gated `cost_per_meter`.
- **Fix:** `max(depths) if depths else None`; guard the cost divisor.
- **Test:** `test_operations_intelligence_regressions.py::test_current_depth_unknown_not_fabricated_zero`.

### F5 — W12 risk assessment fabricated max risk / constants from missing data (MEDIUM)

- **File / function:** `tabs/w12_Analysis.py` · `analyze_risk`.
- **Old behavior:** no safety report → `days_no_lti = 0` → Safety scored 8/10
  HIGH; flat `Equipment = 5`, `Weather = 4` presented as assessments.
- **Why it is wrong:** "no data" silently rendered as "worst case"; constants
  with no data source presented as measurements.
- **Fix:** extracted pure `_risk_scores()`; UNKNOWN inputs (no safety report /
  NULL days / unknown NPT / no data source for Equipment & Weather) → None =
  NOT ASSESSED, excluded from the chart and overall score. Rule thresholds for
  cases WITH data are unchanged (no engineering-formula change). Report now
  labelled "rule-based, not a measurement".
- **Test:** `tests/test_w12_risk_assessment_m26.py` (5).

### F6 — W12 whole-well analyses under-labelled (LOW, §13)

- **File:** `tabs/w12_Analysis.py` · `update_plan_variance`,
  `update_intelligence`.
- **Fix:** both are whole-well by design (keyed by `well_id`); added explicit
  `[Whole-Well]` labels so a bore selection can't make them read as bore-scoped.
  `analyze_cost` / `analyze_risk` already declared "Scope: Whole Well". No query
  change.

### F7 — Reproducibility: lockfile ≠ session environment (AUDIT ONLY, §31)

- `requirements-lock.txt` pins SQLAlchemy 2.0.36 / PySide6 6.8.1.1 / numpy
  2.1.3 / pandas 2.2.3; the sandbox rebuilds `.venv` at SQLAlchemy 2.0.54 /
  PySide6 6.11.2 / numpy 2.4.6 / Python 3.11.2.
- **Classification: ENVIRONMENT-ONLY / DOCUMENTATION-MISMATCH.** It did NOT
  cause any ownership-test failure (full suite green on the session env). Per
  §31 the lockfile was **not** rebuilt. Deferred.

### F8 — verify_release.py coverage (AUDIT ONLY, §32)

- **SUPPORTED:** compileall; pytest `--collect-only` count > 0; full pytest
  execution; failure/error/xpassed gating.
- **NOT SUPPORTED / DEFERRED:** `git diff --check`, exact-SHA assertion,
  dependency-lock verification, package smoke, CI status, environment manifest,
  Windows acceptance, MinerU acceptance.

---

## E. Changes (files + reason)

| File | Reason |
|---|---|
| `core/database.py` | F1: schema-derived report-scoped ownership guard (30 models) |
| `core/operations_intelligence.py` | F4: unknown current_depth → None, not 0.0 |
| `tabs/w12_Analysis.py` | F2 (ambiguous legacy fallback), F3 (NPT NULL), F5 (risk UNKNOWN), F6 (whole-well labels) |
| `tests/test_report_scoped_ownership_m26.py` | new — F1 adversarial coverage (25) |
| `tests/test_w12_risk_assessment_m26.py` | new — F5 (5) |
| `tests/test_w12_scope_leakage_m25.py` | F2, F3 regressions |
| `tests/test_w12_analytics_truth.py` | bind new `_unique_legacy_row` helper |
| `tests/test_operations_intelligence_regressions.py` | F4 regression |
| `tests/test_scope_attribution.py` | §19 two-bore/one-section NULL-NULL convergence |

Models intentionally **unchanged**: engineering calculation records
(`CasingCalculationRecord` etc.) and master-reference tables — no `report_id`,
out of scope. `CostRecord` keeps its well-level design (no bore column, §21/§52).
No schema migration. No engineering-formula change.

---

## F. Tests

| Category | Command | Result |
|---|---|---|
| Focused (M26 new/changed) | `pytest tests/test_report_scoped_ownership_m26.py tests/test_w12_risk_assessment_m26.py tests/test_w12_scope_leakage_m25.py tests/test_operations_intelligence_regressions.py tests/test_scope_attribution.py` | all pass |
| Ownership/import regression | `pytest tests/test_bha_bit_ownership_integrity.py tests/test_wellbore_ownership_integrity.py tests/test_integration.py tests/test_import_architecture.py tests/test_import_repairs.py tests/test_ddr_save_atomicity.py` | 64 passed |
| Golden/DDR/import | `pytest test_golden_ddr test_real_oeoc_golden test_ddr_forensic_regressions test_ddr_regression test_import_inventory_routing test_wellbore_discriminator_import test_p0_phase1_regressions` | 232 passed |
| **Full suite** | `pytest -p no:cacheprovider -o addopts="" -ra -q` | **1502 passed, 4 skipped** (264.79s) |
| Compile | `compileall core dialogs tabs tests packaging app.py main_window.py run.py verify_release.py` | exit 0 |

Skipped (4), all environment-gated, none are failures:
- `test_ddr_acceptance.py` ×2 — `DRILLMASTER_TEST_DDR_XLSX/PDF` not set (opt-in).
- `test_mineru_real_integration.py` — `MINERU_INTEGRATION_INPUT` not set →
  **MINERU NOT VERIFIED**.
- `test_packaging_smoke.py` — Windows bundle absent → **WINDOWS NOT VERIFIED**.

---

## G. Adversarial oracle results

| Scenario | Oracle | Result |
|---|---|---|
| cross-well child (record A → report B) | must reject | REJECTED + rolled back (30 models) |
| cross-bore isolation | Orig ROP 20 / ST ROP 60; Orig NPT 1h / ST NPT 4h | isolated (`test_w12_wellbore_scope`) |
| whole-well aggregate | 1h + 4h = 5h (independent sum) | 5.0 (`test_w12_wellbore_scope`, `test_report_scope_metadata_m25`) |
| same-date legacy child ambiguity | 2 rows (15, 99) → UNKNOWN | None, not 15 (F2) |
| NULL vs zero (NPT) | A=2.0, B=NULL, C=0.0 → total 2.0 | pass (F3) |
| NULL vs zero (depth) | 2 reports NULL depth → None | pass (F4) |
| section/report bore contradiction | report bore ≠ section bore | REJECTED (`test_report_wellbore_must_match_section`) |
| NULL chain | report bore NULL + section bore NULL | stays UNKNOWN, not Original (`test_legacy_null_wellbore_report_ok`) |
| import → selection | ST-1 report opens scoped to ST-1 | pass (`test_import_to_selection_*`) |
| scope-attribution 2-bore/1-section NULL/NULL | converges via section, no INVALID | pass (§19) |

---

## H. Dead / duplicate audit

- No duplicate `save_*` / `get_*` method names in `core/database.py`
  (`grep | uniq -d` empty).
- No `DEPRECATED` / abandoned scope-helper markers in `scope_attribution.py`
  or `w12_Analysis.py`.
- `resolve()` in `scope_attribution.py` = **USEFUL-BUT-UNWIRED / DEFERRED** —
  only `coverage()` (read-only) is wired into production (`core/data_quality.py`).
  Not auto-wired (§19). Classification: retain, DEFERRED.
- **No blind deletions.**

---

## I. Branch audit

| Branch | SHA | Classification |
|---|---|---|
| `arena/01a085e0-drill-master` | `7a3bb4a` | ACTIVE (this session) |
| `arena/01a0801f-drill-master` | `b05ea768` | STALE-BUT-UNIQUE (this session's base parent; other session) |
| `arena/01a056c5-drill-master` | `02dd3e14` | UNKNOWN (other session) |
| `arena/01a05747-drill-master` | `c7e7697f` | UNKNOWN (other session) |
| `arena/01a07094-drill-master` | `ad7ea0db` | UNKNOWN (other session) |
| `drill-Master` (default) | `02053eb` | UNKNOWN (upstream default) |

No branch deleted or modified — cannot prove merge/obsolescence for any.

---

## J. Documentation

- This certification (new).
- No README/TESTING/PRODUCTION doc claims were changed: their current test
  counts / environment claims could not be re-verified against a committed CI
  run, so per §30 they were left untouched rather than updated by guess.

---

## K. Deferred (intentionally untouched)

- `resolve()` auto-wiring / scope backfill — DEFERRED (§19).
- `requirements-lock.txt` rebuild — DEFERRED (§31, environment-only).
- `verify_release.py` extra gates (SHA/lock/CI/manifest/Windows/MinerU) —
  DEFERRED (§32).
- Engineering-formula audits — out of scope (§22); none found to cause an
  ownership/data-integrity defect.
- Large-file refactors (`database.py` 10189L, `w12_Analysis.py` 3217L) — carried
  debt, no BaseTab/broad refactor (§33).

---

## L. Final certification

**CERTIFIED FOR THIS MISSION**, with the following explicitly unverified areas
reported honestly (not equated with unit tests):

- CI NOT VERIFIED (no committed workflow).
- WINDOWS NOT VERIFIED (bundle absent).
- MINERU NOT VERIFIED (opt-in integration not run).

All ownership/scope gates (A–Q) pass: report-linked cross-well contradiction is
rejected on every save path across all 30 models; cross-bore contamination is
isolated; section/report contradiction is rejected; the legacy fallback is
deterministic or UNKNOWN; UNKNOWN vs zero and Whole-Well vs bore are preserved;
no fabricated engineering values; scope attribution stays deterministic with
`resolve()` unwired; full regression run (1502 passed / 4 skipped).

# M171–M200 – DrillMaster product integration, data completion, workflow consolidation and final qualification

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED**

| Item | Value |
|---|---|
| Repository / branch | `asgareyvazi/Drill-master` / `arena/72010272-drill-master` (the only branch written) |
| Mission base | `43b1115b` (M141–M170 report), recovered by fetch + CAS after a sandbox reset |
| Code commits | `54fba747e2b0c7924db77c2d13aedfc4321db544` (M173–M176); `6731be514362afba43bab3a4a17e129d6597d4a0` (M177–M198); **final code `7c2da89b0683d0ad7efde9e37ca87de8e1ff81f7`** |
| Report commit | the commit that adds this file, the direct child of `7c2da89` (§V) |
| Protected branches | `drill-Master` = `e3fa42a3257e` and every other `arena/*` head unchanged; no tags; no force-push |

Every statement below names the code, the test, the commit or the CI run that supports it. "NOT RUN", "OPEN" and
"OWNER-GATED" mean exactly that.

---

## A. Git baseline (M171)

- `git fetch --unshallow`, then `ls-remote` at the start:
  - our branch = `43b1115`;
  - `drill-Master` = `e3fa42a`. That is PR #4, which holds only a confidential DDR PDF. It was not opened, and the
    file is not on this branch.
  - other `arena/*` heads: `02dd3e1`, `c7e7697`, `ad7ea0d`, `b05ea76`, `c28bbef`, `7f0186e`, `4336ea3`.
  - 0 tags, 1 worktree, 0 stashes.
- No newer commit existed on our branch, so nothing had to be incorporated. Nothing was reset to a historical SHA.
- **Sandbox resets.** Two resets happened during the mission. Each was recovered without discarding work:
  1. `git fetch`;
  2. `git update-ref refs/heads/arena/72010272-drill-master <remote> <stale>` (compare-and-swap);
  3. `git read-tree HEAD`;
  4. `git branch --set-upstream-to`.

  The work tree, persisted by the platform, was then intact. The Qt runtime libraries were rebuilt from source
  tarballs (libglvnd, libxkbcommon, dbus, expat, byacc, plus a GLX stub). Nothing was installed into the product.

## B. Phase status

| Phase | Status | Evidence |
|---|---|---|
| M171 baseline | DONE | §A |
| M172 live register | DONE | §B.1 |
| M173 scalar correction from the queue | DONE | `core/review_scalar_correction.py`, `tests/test_m173_scalar_correction.py`, `54fba74` |
| M174 header aliases | DONE | `core/ddr_header_aliases.py`, `tests/test_m174_header_aliases.py`, `54fba74` |
| M175 well identity | DONE | `core/ddr_well_identity.py`, `dialogs/well_identity_dialog.py`, `tests/test_m175_well_identity.py`, `54fba74` |
| M176 route parity | DONE (synthetic); real-document acceptance **NOT RUN** | `docs/engineering/M176_DDR_ROUTE_PARITY.md`, `tests/test_m176_route_parity.py` |
| M177–M180 legacy plot | DONE: tab retired, data kept | `docs/engineering/M177_LEGACY_TRAJECTORY_PLOT.md`, `core/trajectory_views.py`, `tests/test_m178_trajectory_views.py`, `6731be5` |
| M181 sources | DONE: **no permitted source**, so the library is empty | `docs/engineering/M181_TUBULAR_SOURCES.md` |
| M182–M183 importer, population | DONE (importer); population blocked by source rights | `core/engineering/tubular_import.py`, `tests/test_m181_m183_tubular_import.py` |
| M184–M188 module integration | DONE | `core/engineering/reference_binding.py`, `tests/test_m184_m189_reference_integration.py` |
| M189 shared service, drift | DONE; **M165 COMPLETE** (real persistence tests) | §P |
| M190 tubular journey | DONE (20 steps) | `tests/test_m190_tubular_journey.py` |
| M191 W13 re-audit | DONE: unchanged 9 / 10 / 4 / 1 / 1 / 2 | §O |
| M192 consistency | DONE: inventory, no global change | `tools/quality/density_constant_inventory_m192.py`, `tests/test_m192_density_constants.py` |
| M193 50-source audit | DONE | §Q |
| M194 adoption | DONE: nothing adopted | §R |
| M195 D51, Windows annotation | Annotation **CLASSIFIED and FIXED**; D51 **OPEN** | §S |
| M196 owner packages | DONE: 19 packages × 9 fields | `docs/engineering/M196_OWNER_DECISION_PACKAGES.md` |
| M197 UX / success messages | DONE | `tools/quality/ux_success_audit_m197.py`, `tests/test_m197_ux_success_audit.py`, help §19 |
| M198 migration, backup, restore | DONE | `tests/test_m198_backup_restore_qualification.py` |
| M199 regression and qualification | DONE: CI green on all 4 jobs at `7c2da89`; coverage 71.21 % | §U |
| M200 review, push, report | DONE | §V |

### B.1 Live register (M172)

Every item has one state, with no unqualified PARTIAL.

| Item | State | Evidence / next step |
|---|---|---|
| D51 (CI hang at 900 s, `test_m132_trajectory_layers.py:199` frame) | **OPEN** | No recurrence and no new frame in this mission (§S). No timeout raised, no retry |
| M151 review workspace, deferred scalars | **RESOLVED** by M173 | edit from the persisted queue (§C) |
| M152 route parity / MinerU free-text headers | **RESOLVED (synthetic)** by M174 / M176; real documents **NOT RUN** | §D, §F |
| M156 legacy Trajectory Plot | **RESOLVED** by M177–M180 | §G |
| M158 pipe data | **BLOCKED (source rights)** | §I; owner package P18 |
| M159 / M165 module snapshots | **RESOLVED** by M184–M189 | §K–§P |
| M161 external audit / 50 sources | **RESOLVED** by M193 | §Q |
| DDR well-identity mismatch | **RESOLVED** by M175 | §E |
| Windows crash-dump annotation (`c20f5cd`) = **D62** | **RESOLVED**: classified as a harness excerpt, and the cause is fixed | §S; matrix row D62 |
| Raw-SQL mutability of published tubular sets = **D61** (found in the M189 review) | **RESOLVED** (`6731be5`) | §P; matrix row D61 |
| D6 MSE lineage | **PARTIAL – legacy rows only**: new saves carry lineage (M104); legacy rows need the audited M123 repair, row by row | unchanged |
| D11 datum / CRS | **OWNER-GATED** (P10): vertical datum done; CRS not implemented by scope | `SURVEY_REFERENCE_SCOPE.md` |
| D13 licence disclosure | **RESOLVED for disclosure**; distribution decisions are OWNER-GATED (P1, P2) | `dependency_audit.json` (`6731be5`: 0 findings) |
| D17 coverage numerator ±2 | **PROCESS** (CI measurement noise, documented M105) | unchanged |
| D46 load-test hang | **RESOLVED with residual** (M122 isolation); residual tracked under D51 | unchanged |
| OCR / MinerU gates | **OWNER-GATED** (P4, P5) | nothing bundled |
| 7.48 vs 7.48052 | **OWNER-GATED** (P8); inventoried | §O |
| Currency | **OWNER-GATED** (P9); mixing refused | M130 tests |
| Security (encryption, HMAC, ACL, idle lock) | **OWNER-GATED** (P13–P15) | `core/security_posture.py` |
| Windows and field acceptance | **NOT RUN** (P17) | a green Windows CI run is not interactive acceptance |
| Release / signing | **NOT DONE** (P16) | UNSIGNED |
| **D63**: one segfault (exit 139) in a local trajectory-regression run | **OBSERVED, NOT REPRODUCED** | Later local runs of the same files completed; no core dump was kept. It is not claimed fixed (no retry logic added) |
| New: `AddPipeDialog.PIPE_DB` and w3b preset OD/ID values have no provenance | **OPEN (observation)** | Recorded in `M184_M189_REFERENCE_INTEGRATION.md`; library values carry provenance, presets do not |
| New: pre-existing E701 lint in `tools/real_user_acceptance.py` and F541 in `packaging/junit_report.py` | **OPEN (outside the lint scope `core dialogs tabs tests`)** | not touched |

## C. M151 → M173: scalar values from the review queue

- **Code:** `core/review_scalar_correction.py` (contract `ddr-scalar-correction-v1`) and
  `dialogs/import_review_dialog.py` (`54fba74`).
- **What the dialog shows:** the original and normalized value, type, units and destination, before anything is
  written.
- **Validation:** the canonical validator applies. It rejects bool, NaN, ±inf, overflow and bad unit conversions.
- **Saving:**
  - An explicit confirmation is required.
  - The decision and the canonical update are written in one transaction, with the audit records
    `ddr_review_correction` / `ddr_review_reopened` (reviewer, time, old / new value, reason).
  - Optimistic concurrency applies, and items of a foreign well or report are refused.
  - On failure the item stays unresolved, and no record or zero is created.
- **Test:** `tests/test_m173_scalar_correction.py` runs Edit → Validate → Preview → Confirm → Save → Reopen →
  Audit with real Qt and a real database.

## D. M152 / MinerU → M174 header aliases

- **Code:** `core/ddr_header_aliases.py` (`ddr-header-aliases-v1`).
- **How headers are matched:**
  - Description-type headers (Activity / Description / Operation / Details, EN / FA) map through per-profile
    aliases only. There is no broad fuzzy matching.
  - The result is MAPPED, AMBIGUOUS (which needs an operator decision) or NO_MATCH.
  - The original header and its coordinates are kept.
- **Versions:** profile rules version 2; version-1 profiles stay readable.
- **Test:** `tests/test_m174_header_aliases.py`.
- MinerU itself stays an optional external tool (P4).

## E. Well identity (M175)

- **Code:** `core/ddr_well_identity.py` (`ddr-well-identity-v1`) and `dialogs/well_identity_dialog.py`.
- **Behaviour:**
  - The selected well and the workbook's well are shown side by side with their evidence.
  - An explicit, audited decision is required: `IMPORT_INTO_SELECTED_WELL` / `IMPORT_INTO_SOURCE_WELL` /
    `CREATE_SOURCE_WELL`, the last only by an explicit user choice.
  - The decision is revalidated before persistence.
  - Multiple identities, or no selected well, are refused. Nothing is silently rerouted, and no well is ever
    auto-created.
- **Golden:** `SYNW-101` → UNKNOWN_SOURCE_WELL.
- **Tests:** `tests/test_m175_well_identity.py`, and step 4 of `tests/test_m169_end_to_end_journey.py`.

## F. DDR routes (M176)

- **Matrix:** `docs/engineering/M176_DDR_ROUTE_PARITY.md` covers XLSX profile, generic Excel, smart template,
  native PDF, MinerU and fallback, each against morning / 24 h, multi-page, multi-table, mixed headers and a
  missing time anchor.
- **Provenance:** `ddr-source-provenance-v1` records sha256, page, sheet, row, cell and versions (pipeline 2,
  profile rules 2, header rules 1). It records only the profile that was actually applied.
- **Limitation:** generic Excel is a documented LIMITATION.
- **Real-document acceptance: NOT RUN.** The standing rule not to open the confidential `08-DDR … .xlsx`
  workbook was not reversed, so the M176 allowance for an isolated copy was not used.
- **Test:** `tests/test_m176_route_parity.py`.

## G. Legacy Trajectory Plot migration (M177–M180)

**Inventory** (`docs/engineering/M177_LEGACY_TRAJECTORY_PLOT.md`):
- The legacy save was report-only and unnamed, with no audit, and a saved row was never reopened.
- The CSV export had a hard-coded `Z = 0` and no units.
- `TrajectoryCalculationManager` had no caller.

**Port** (`core/trajectory_views.py`, `tabs/trajectory_saved_views_panel.py`, model `TrajectoryViewRevision`):
- Views are named and bound to the well / wellbore / survey revision.
- They are insert-only revisions: CREATE / REVISE / CLONE / ARCHIVE / RESTORE, with optimistic concurrency
  (`StaleViewError`) and a reason for archive / restore.
- Every action is audited as `trajectory_view_<action>`.
- Compare pairs stations by MD within 1e-6 m, with no interpolation.
- Export writes units and provenance. A missing value is exported empty or null, never 0.
- Unit checks: 800 m = 2624.671916 ft; 3°/30 m = 3.048°/100 ft.

**Retirement:**
- The W6 "Trajectory Plot" sub-tab and the unused manager class were removed.
- `trajectory_plots` / `trajectory_calculations`, `core/trajectory_plot` and `plot_series` are kept.
- Old rows are listed read-only per well (`tv.legacy_plots`).

**Tests:**
- `tests/test_m178_trajectory_views.py`, run on fresh and upgraded databases.
- The first run of the 61-mutant catalogue left survivors; tests were added until every M178 mutant was killed
  (`tools/quality/mutation_m171_m200.py`, `M178-*`; §U).

## H. Canonical viewer

- W6 › Well Trajectory Viewer is the single trajectory UI, and saved views are its sub-tab
  (`tabs/trajectory_viewer.py`; `tests/test_trajectory_3d.py` tab list).
- No duplicate user-facing workflow remains.
- User help: `docs/engineering/DRILLMASTER_USER_WORKFLOWS.md` §18.

## I. Tubular sources and licensing (M181)

`docs/engineering/M181_TUBULAR_SOURCES.md` evaluates seven source groups. All were rejected as data:

| Source | Why rejected |
|---|---|
| DOE GDR "Supercritical Drilling Materials" `casing_v2.csv` (CC BY 4.0) | per-well casing histories with nominal OD only |
| openwashdata (CC BY 4.0) | water-well boreholes |
| Open-Source-Drilling-Community `DrillString` (MIT) | a schema, with no rows |
| OSDU reference values | names only |
| vendor data books and spec sheets | proprietary or API reprints |

- No API 5DP / 5CT / RP 7G / TR 5C3 or ISO 11960 / 11961 / 10400 tables were used.
- No raw file was downloaded into the repository.

## J. Data population (M182–M183)

**Library state:** empty. No permitted data exists, so nothing was populated. Tests use synthetic `SYN-*` items.

**Importer** (`core/engineering/tubular_import.py`, `tubular-import-v1`; `dialogs/tubular_import_dialog.py`;
template `docs/engineering/tubular_import_template.csv`):
- **Headers:** only canonical headers are accepted. No unit is converted, and blank cells stay unavailable.
- **Invalid rows:** formula, boolean, non-finite and ≤ 0 values make a row INVALID.
- **Provenance:** API / ISO citations block the file, and manufacturer data needs a licence. Each row records the
  file SHA-256 and its source row.
- **Row states:** NEW / ALREADY_PRESENT / DUPLICATE_IN_FILE / CONFLICT (never overwritten) / INVALID.
- **Apply:**
  - Needs a confirmation, a reason and explicit consent for a partial import.
  - The SHA, the DRAFT state and staleness are re-checked.
  - The audit record `tubular_reference_import` is written in the same transaction.
- **Limits:** 20 MB and 5000 rows. The documented row limit is tested without monkeypatching.
- **Raw file:** never stored.

**Owner source-request package:** M181 doc §4 and P18.

## K. Architecture (M184)

- **Code:** `core/well_architecture.py`, `core/wellbore_schematic_engine.CasingData.tubular_reference` and
  `tabs/w3b_wellbore_schematic_tab.py` (**Library…** under the casing table).
- **Applying an item:**
  - The item fills OD, ID, weight and grade.
  - An item without OD is refused.
  - An unavailable ID stays unknown and is never derived.
- **Freezing a revision:**
  - The binding is frozen with the revision only while the values hold.
  - Revisions without a binding keep their component SHA-256 (a test confirms no key is added).
  - `casing_inputs` / `load_casing_from_architecture` carry the binding into Casing Strength.
- **Limitation:** the schematic JSON file save does not carry bindings. This is documented.
- **Tests:** `test_architecture_revision_pins_the_snapshot_and_an_edit_drops_it` and
  `test_w3b_library_pick_is_frozen_reloaded_and_reaches_casing_strength`.

## L. Volumes (M185)

- **Code:** the `AddPipeDialog` **Library…** button (`dialogs/engineering_dialogs.py`). Unavailable values are
  cleared, never kept stale.
- **Case data:** the `extra:pipes` case input stores the binding.
- **Method:** the result is identical with and without the library pick. String volume golden: ID² / 1029.4 × L.
- **Test:** `test_volumes_case_stores_the_snapshot_keeps_the_golden_and_reports_drift_on_reopen`.

## M. Hydraulics (M186)

- **Code:** each row keeps its binding in column 0 (`_hy_row_binding`). Editing a bound cell drops the binding.
- **Method:** total loss and ECD are identical with and without the pick. Method version: "M126
  circulating-system hydraulics v1".
- **Tests:** `test_hydraulics_rows_carry_the_binding_and_drop_it_when_a_cell_is_edited` and
  `test_hydraulics_results_are_identical_with_and_without_the_binding`.

## N. Weight / T&D (M187)

- **Golden:** the weight-card closed form is unchanged. Air weight = ppf × L(ft); BF = 1 − (MW / 7.48) / 65.5.
- **Boundaries:** the M127 boundaries are unchanged (soft-string Johancsik; no pinned survey means T&D is
  UNKNOWN).
- **Test:** `test_weight_case_with_a_library_component_matches_the_weight_card_golden`.

## O. Casing / Cement (M188), W13 re-audit (M191) and consistency (M192)

**Casing Strength:**
- **Filling:** **Library…** (`load_casing_from_library`) uses origin kind `reference`
  (`core/calculator_contracts.CASING_ORIGINS`).
  - OD, ID and weight come from the library.
  - The wall comes from the library, or is DERIVED as (OD − ID)/2 and labelled so.
  - Yield is always `unknown` until the user enters it, and is then recorded as `user`.
- **Boundaries:** unchanged (TR 5C3 pipe-body subset; "Not calculated: yield strength unknown").
- **Tests:**
  - `test_casing_from_the_library_keeps_yield_unknown_and_records_the_snapshot`;
  - `test_casing_wall_missing_from_the_library_is_derived_and_labelled`;
  - `test_casing_item_without_an_id_leaves_id_and_wall_unknown`.

**Cement:**
- Cement Volume, Balanced Plug and Buoyancy are scalar WORKSHEETs and have no library button.
- Architecture cement worksheets cite the frozen revision, which carries the binding.

**M191 W13 leaves:**
- The 27 leaves are unchanged: 9 CONTRACT / 10 SCREENING / 4 WORKSHEET / 1 TRAINING AID / 1 REFERENCE-ONLY /
  2 NOT_SUPPORTED (`core/calculator_contracts.LEAF_CLASSES`; `tests/test_m125_w13_classification.py`).
- Kill Sheet stays **TRAINING AID**. The library button in its pipe dialog changes neither its class nor the
  NOT_SUPPORTED case capture.
- Anti-Collision has no W13 case and stays labelled **SCREENING – NO ISCWSA UNCERTAINTY – NO SEPARATION FACTOR –
  NOT APPROVED**.
- No method version changed. M126 / M127 / M133 goldens: see the regression in §U.

**M192 constants:**
- `tools/quality/density_constant_inventory_m192.py` finds 17 × `7.48`, 14 × `7.48052` and 2 × `7.4805` in
  11 files (`docs/mission-reports/m171-m200-evidence/density_constants_m192.json`).
- The difference is 0.007 % (75 pcf = 10.0267 against 10.0260 ppg).
- No global change was made (P8).
- `tests/test_m192_density_constants.py` fails on any silent change.

## P. M165 snapshots → M189 shared reference service

**Service:** `core/engineering/reference_binding.py` (`tubular-binding-v1`).
- A binding is `{contract, snapshot, fields, unavailable}`.
- The snapshot is the immutable M157 snapshot, and a damaged snapshot is refused (`verify_snapshot`).

**Drift states**, computed from stored snapshots only. Nothing is re-read into a case or recalculated:

| State | Meaning |
|---|---|
| MATCH | unchanged; newer published versions are reported as "NOT applied" |
| DIFFERENT | fingerprint changed, set no longer published, or item missing |
| NOT_REPRODUCIBLE | the set version is not in this database |
| UNREADABLE | the snapshot fails its fingerprint, or the check failed |

**On case reopen:** `tabs/calculation_cases_panel.reference_report` puts the summary on the status line. A failing
check is shown as UNREADABLE, never MATCH (tested).

**Storage guards (new):** `core/storage_guards._tubular_guards`, `trg_tubular_*`.
- A PUBLISHED set and its items cannot be updated, deleted or extended by any SQL writer.
- Drafts stay editable.
- Anyone who can write the file can still drop the triggers. This is documented in `security_posture.NON_CLAIMS`
  (P13).

**M165 COMPLETE.** These real persistence tests support it:
- `test_snapshots_survive_closing_and_reopening_the_database_file`;
- `test_drift_states_match_different_not_reproducible_and_unreadable` (real second database);
- `test_a_published_set_is_immutable_at_the_storage_layer_and_drafts_stay_editable`;
- `tests/test_m198_backup_restore_qualification.py` (backup → change → restore, snapshots verified);
- step 18 of `tests/test_m190_tubular_journey.py`.

## Q. 50-source audit (M193)

- **Recovered:** the M52 list is `docs/engineering/OPEN_SOURCE_ADOPTION_REGISTER.md` (50 repositories, each with a
  recorded SHA, licence and classification).
- **Re-audit:** `tools/quality/oss_reaudit_m193.py` read each repository through the authenticated GitHub REST API
  (read-only; nothing cloned, installed or run). Evidence:
  `docs/mission-reports/m171-m200-evidence/oss_reaudit_m193.json`.
- **Result:** 46 UNCHANGED, 3 NEW COMMITS, 1 ARCHIVED, 0 licence changes, 0 gone:

| # | Repository | Recorded SHA → current SHA | Licence | Outcome |
|---|---|---|---|---|
| 11 | Himageo2006/mud-engineer-pro | `e244ce1e2e` → `e1c25144be` | none detected (unchanged) | INSPIRE ONLY unchanged |
| 33 | B0yko/wellbrief | `100cb4a871` → `8dd3b8d8ca` | Apache-2.0 (unchanged) | INSPIRE ONLY unchanged |
| 41 | ldocallaghan/BoreTHM | `1756c0bb8a` → `30664bf0e2` | Apache-2.0 (unchanged) | INSPIRE ONLY unchanged |
| 48 | api-evangelist/national-oilwell-varco | `1ed5ab7f97` (archived) | none detected | REJECT unchanged |

- The tool never changes a classification by itself.
- **Tests:** `tests/test_m193_oss_reaudit.py` (parser, verdict rules, NOT CHECKED on failure, evidence covering
  all 50).

## R. Adoption (M194)

**Nothing adopted.**
- No repository in §Q or in the M181 search is a qualified, licence-clean drop-in for an unmet need.
- The candidates are permissive:
  - welleng (Apache-2.0) is gated on ISCWSA model-table licensing and benchmarks (P19);
  - wellbrief and BoreTHM (Apache-2.0) are ideas only.
- No dependency was added (`dependency_audit.json`: 26 locked, 0 findings), and nothing uses cloud, GPU or API
  keys.

## S. D51 and the Windows annotation (M195)

**Windows "fatal crash dump" annotation on `c20f5cd`** (Windows job 130135216636):
- **Classification:** an excerpt of harness output, not an interpreter crash.
- **Evidence:**
  - The annotation API shows the marker matched at line 1813 of `windows-regressions.log`.
  - That line is a test-start breadcrumb of the parametrized test
    `test_a_logged_fatal_error_decides_whether_an_exit_code_is_a_native_death[Fatal Python error: Aborted-3-True]`.
  - The run ended with ordinary assertion failures (index plan, stale `dependency_audit.json`).
- **Reproduced deterministically:** the pre-fix `crash_excerpt` reports "marker at line 3" on the synthetic log of
  that shape.
- **Fix** (`packaging/junit_report.py`):
  - `CRASH_MARKERS` now requires faulthandler's own banner form: `Fatal Python error: `,
    `Windows fatal exception: `, or `Current thread 0x…`.
  - `is_crash_marker` ignores text after the breadcrumb token. Progress dots before a real banner still count.
- **Tests** (`tests/test_junit_report.py`):
  - `test_a_banner_quoted_in_a_test_id_is_not_a_crash_dump`;
  - 12 parametrized marker cases;
  - `test_a_real_dump_after_a_breadcrumb_that_quotes_a_banner_is_still_found`.
- **Mutants:** 4 `M195-*`.

**D51: OPEN.**
- No hang occurred in this mission's CI runs (§U), and no new stack frame was captured.
- No timeout was raised and no retry was added.

## T. Owner decisions (M196)

`docs/engineering/M196_OWNER_DECISION_PACKAGES.md` holds 19 packages with 9 fields each (Decision, Current
behaviour, Evidence, Licence / legal facts, Options, Consequences, Engineering view, Until decided, Owner must
provide):

| | | | |
|---|---|---|---|
| P1 PyMuPDF | P2 Qt LGPL | P3 pwptemp / torque_drag | P4 MinerU |
| P5 OCR | P6 qtribbon | P7 AI / GPU | P8 7.48 |
| P9 currency | P10 datum / CRS | P11 Kill Sheet | P12 method approvals |
| P13 encryption / HMAC / DPAPI / SQLCipher | P14 ACL | P15 idle lock | P16 signing |
| P17 Windows / field acceptance | P18 tubular data source | P19 ISCWSA / welleng | |

No decision is recorded.

## U. Quality and CI (M197–M199)

**M197:**
- `tools/quality/ux_success_audit_m197.py` scanned every exception handler in `tabs/`, `dialogs/` and
  `main_window.py` for success wording. It found 9 matches; each was reviewed as truthful, and 0 are unreviewed.
- The new flows say NOT SAVED / NOT IMPORTED / NOT PUBLISHED / NOT CREATED / NOT USED on failure.
- Help: `DRILLMASTER_USER_WORKFLOWS.md` §18 (saved views), §19 (tubular library) and §20 (what NOT SAVED / NOT
  UPDATED means, and the audit tool).
- Review fix: the saved-views export buttons were connected to lambdas over the panel. They now use bound methods
  (`_export_csv` / `_export_json`), following the M132 no-closure rule, and the JSON button path is exercised in
  `tests/test_m178_trajectory_views.py`.

**M198:** `tests/test_m198_backup_restore_qualification.py`:
- A v5 database without the M157 / M178 tables is upgraded, gains the tables and the `trg_tubular_*` /
  `trg_trajectory_view_*` guards, and keeps its rows.
- BackupService → later changes → RestoreService (with a safety copy) brings back exactly the snapshot.
- Views, sets and case snapshots verify after the restore, and the published set is still guarded.

**Mutation** (`tools/quality/mutation_m171_m200.py`):

| Run | Result |
|---|---|
| 61-mutant catalogue (M173–M180) | 3 survivors on the first run (§G); killed after the new tests |
| 91-mutant catalogue | **91 / 91 KILLED, 0 survived, 0 equivalent, 0 invalid, complete** (1571 s) |
| 3 storage-guard mutants plus 2 re-checks | 5 / 5 killed (`docs/mission-reports/m171-m200-evidence/mutation_m189_guards_partial.json`) |
| 9 new audit-tool mutants (M192 pattern, M193 licence / error / archived / moved, M197 prefix / anchor / handler scope) | 9 / 9 killed (`mutation_m192_m193_m197_partial.json`) |
| **Final full catalogue, code tree of `7c2da89`** | **103 / 103 KILLED, 0 survived, 0 equivalent, 0 invalid, `complete: true`**, 1318 s; baseline 294 passed over 12 test files (`docs/mission-reports/m171-m200-evidence/mutation_m171_m200_full.json`) |
| Stale anchor in a prior catalogue | `SEC-audit-guards-not-installed` (m121_m140) was INVALID after M189 extended `_TABLE_OF`. Its anchor was moved (same mutation) and the mutant was KILLED (`mutation_m121_m140_sec_guard_anchor_partial.json`). All 1002 anchors of the 15 catalogues are now unique |

- The 91-mutant run's JSON was lost in the second sandbox reset; only the summary line is recorded here.
- One audit-tool mutant draft (`SUCCESS.match` → `SUCCESS.search`) was **equivalent**, because the pattern is
  anchored by `^`. It survived, was not counted, and was replaced by a non-equivalent one
  (`M197-success-anywhere`, killed).
- A test was added for each new mutant class (`tests/test_m197_ux_success_audit.py`: a reviewed file does not hide
  a different claim; failure wording is not a claim).

**Prior mutation suites re-run on the final code tree:**

| Catalogue | Result | Evidence |
|---|---|---|
| `mutation_m141_m170.py` | 28 / 28 KILLED, complete, 147 s | `docs/mission-reports/m171-m200-evidence/mutation_m141_m170_rerun.json` |
| `mutation_m121_m140.py` | 330 mutants: 329 KILLED, 1 declared EQUIVALENT (unchanged from M140), 0 survived, 0 invalid, complete, 2017 s | `docs/mission-reports/m171-m200-evidence/mutation_m121_m140_rerun.json` |
| m46 … m101_m120 (541 mutants in 13 catalogues) | **NOT RE-RUN** in this mission; every anchor is still unique, so none is INVALID | where M171–M200 changed files they target (e.g. `core/storage_guards.py`, the W13 tab), the m121_m140 re-run and the 103-mutant catalogue re-cover the changed logic. That does not replace re-running them |

**Regression and coverage.** The 4 opt-in skips are not passes.

| Run | Result |
|---|---|
| Local full suite (Python 3.11.2, offscreen; `6731be5` tree plus the in-progress doc / test edits) | 5346 passed, **1 failed** (D64), 4 skipped; 1932 s |
| CI `6731be5` | Source run 43590107366: 3.11 ❌ 132432836322, 3.12 ❌ 132432836097, 3.13 ❌ 132432836317. Each was collected 5351, passed 5346, failed 1 (D64, the same test), skipped 4. Windows run 43590107472 ✅ 132432836498. **Not evidence of a green tree**; it found D64 |
| **CI `7c2da89` (final code)** | **Source run 43594072371: 3.11 ✅ 132444740307, 3.12 ✅ 132444740518, 3.13 ✅ 132444740507; Windows run 43594072333 ✅ 132444740069.** The Windows manifest names `sha=7c2da89b0683…`; the installer is UNSIGNED; the M52 lifecycle stress passed 5 / 5 with 0 new dumps |
| Coverage (CI 3.12 on `7c2da89`) | **71.21 %** branch + line over 280 tracked files (76206 / 107012), against the 70.46 % baseline. No scope change |
| Real MainWindow journeys | `tests/test_m190_tubular_journey.py` (20 steps; real MainWindow, real file database, source file unchanged) and `tests/test_m169_end_to_end_journey.py`. Both pass inside the green CI suites above |

- The per-job pass counts for `7c2da89` are not shown, because the job logs are not readable through this token
  (HTTP 403).
- The release gate fails a job on any failed test, so "success" means 0 failed.


**Gates on the final tree (`7c2da89`):**
- ruff on `core dialogs tabs tests`: 0 findings (ceiling 0).
- E722 / F821: 0.
- Exception scan within the ceiling. Marked `# silent-ok` handlers are explained, and none was added unexplained.
- `dependency_audit --check` clean after `--write`.
- `compileall` clean; `git diff --check` clean.
- `tools/privacy/privacy_check.py`: 1498 files, 0 findings.
- `constant_inventory.py --check` passes after the D64 refresh.

**CI:**

| Commit | Runs | Result |
|---|---|---|
| `54fba74` | Source 43582339540 (3.11 ✅ 132409535466, 3.12 ✅ 132409535716, 3.13 ✅ 132409535758); Windows 43582339557 ✅ 132409535675 | **SUCCESS**, all 4 jobs |
| `6731be5` | Source 43590107366 (3.11 / 3.12 / 3.13 ❌, D64); Windows 43590107472 ✅ | **FAILURE** (1 test, fixed in `7c2da89`) |
| `7c2da89` | Source 43594072371 (3.11 ✅ 132444740307, 3.12 ✅ 132444740518, 3.13 ✅ 132444740507); Windows 43594072333 ✅ 132444740069 | **SUCCESS**, all 4 jobs |

## V. Final commits, remote, workspace

| Item | Value |
|---|---|
| Commits of this mission (fast-forward only) | `54fba747e2b0c7924db77c2d13aedfc4321db544` → `6731be514362afba43bab3a4a17e129d6597d4a0` → `7c2da89b0683d0ad7efde9e37ca87de8e1ff81f7` (final code) → report commit (child of `7c2da89`) |
| Branch | `arena/72010272-drill-master` only; no force-push, no history rewrite, no tags, no releases, no signing |
| Protected branches | not written; checked with `git ls-remote` at the end (report commit message / reply) |
| Evidence directory | `docs/mission-reports/m171-m200-evidence/`: density constants, OSS re-audit, 5 mutation JSONs |
| Workspace | no database, model, temporary file or raw document committed; the confidential `08-DDR` workbook and the `drill-Master` PDF were never opened |

### Independent review (M200)

The review re-read every new flow against the standing rules. It found and fixed four issues:
1. D64, the stale constant inventory;
2. the stale anchor in the prior mutation catalogue;
3. the lambda slots;
4. two documentation defects in M196: the ISCWSA package was missing (now P19), and P12 named P15 for signing
   where it should be P16.

It also confirmed:
- No API / ISO table values were added.
- No value is invented. Yield is never inferred, and a missing value is never 0.
- No well is auto-created or silently rerouted.
- No real-document acceptance is claimed.
- D51 stays OPEN, and D63 is open as observed.

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED**

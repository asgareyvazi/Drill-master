# M61–M69 DrillMaster engineering product completion report

Release status: **UNSIGNED and NOT RELEASE-APPROVED.** Nothing here is Windows desktop, field or production acceptance. Status terms: PASS / FAIL / PARTIAL / OWNER REVIEW REQUIRED / BLOCKED / NOT IMPLEMENTED / NOT RUN.

## 1. Identity

| Item | Value |
|---|---|
| Branch | `arena/72010272-drill-master` (only branch used) |
| Baseline code | `44f124bf1ab2d5c573b9875f19e0ff82ce5915cb` |
| Baseline report | `5ca936f164b9c5e537c62f517abb5c3a89936d8a` |
| M61 code (pushed first) | `47803c607db6c3f0a2a8c704398dee03f0786a75` |
| Final code tip | `d3a64f380fa4eb1483ad69c47abcfdb7fb2f1e3b` |
| Report commit | the commit that adds this file (docs only; its SHA and CI are given in the final reply, not here, because a file cannot contain its own commit SHA) |

### Workspace recovery at start (non-destructive)

The sandbox started on a stale shallow HEAD `4336ea3` while the remote was at `5ca936f`, with a dirty worktree. A temporary index (`read-tree 5ca936f` + `add -A` + `diff --cached`) proved the worktree byte-identical to `5ca936f`. Recovery: `git fetch --unshallow origin`, compare-and-swap `git update-ref refs/heads/arena/72010272-drill-master 5ca936f… 4336ea3…`, `git read-tree HEAD`. No reset, stash, clean or force operation was used.

## 2. Commits (code first, docs separate)

| SHA | Commit |
|---|---|
| `ba16b66` | test(m50): type-based heap scan immune to dead weakproxies |
| `47803c6` | feat(m61): apply profile date formats, table rules, continuation, threshold; batch queue |
| `47a415e` | feat(m62): versioned plan revisions, arc target distance, safeguards, plots |
| `2ff0b19` | feat(m63): immutable named calculation cases in W13 |
| `ae49c7e` | feat(m67): unified calculation history and report center |
| `d5cf3d5` | fix(m61): preview colours and counts follow the profile threshold |
| `dd6d5c6` | fix(m62): plan library only with a full database manager |
| `d3a64f3` | test(m61-m67): mutation set; repoint two m55 snippets |

`ba16b66` fixes a latent order dependence: `test_m50_trajectory_3d_disposal.py` scanned `gc.get_objects()` with `isinstance`, which raises `ReferenceError` on the dead `weakref.proxy` objects PyMuPDF leaves after table extraction, so the test failed only when PDF-table tests ran earlier in the same process. The scan now uses `issubclass(type(o), shiboken6.Shiboken.Object)`, the same pattern as `tests/test_model_registry.py`. No assertion was removed: a weak proxy is never a Qt wrapper, so the set of objects the test checks is unchanged.

## 3. Phase results

| Phase | Result | Summary |
|---|---|---|
| M61 DDR | PARTIAL | Profile date formats, table rules (stop/skip rows/skip tables), continuation and confidence threshold now change the import; batch queue with distinct states, remove/retry/cancel and in-batch duplicates. Gaps: XLSX/PDF-native extraction still on the GUI thread; no profile suggestion; header/column-specific table rules not implemented; OCR engine owner-gated |
| M62 Directional | PARTIAL | Persistent immutable plan revisions (new/save/open/revise/clone/archive/compare/export), continuous arc target distance, numerical safeguards, Inc/Azi/DLS/TVD-vs-MD plots. Gaps: no target solver, no build/turn-rate constraints, no survey revision table, 3D targets/offsets not drawn |
| M63 Workbench | PARTIAL | Named immutable cases for any W13 calculator: save, reopen, compare with current, re-run as child case, text search over labels. Gaps: no per-calculator method versions (labelled), finder/unit work not extended |
| M64 Engines | PARTIAL (unchanged engines) | No engine changed; their saved runs gained unified history and recalculate-and-verify (M67) |
| M65 Well architecture | NOT IMPLEMENTED | Schematic from records, links and revisions not built |
| M66 Operational analysis | PARTIAL (pre-existing W12/W16) | Not extended |
| M67 History / Report Center | PARTIAL | Unified history over 9 sources, filters, compare, recalculate-and-verify with separate storage, HTML/PDF reports, CSV export, new **Calc History** tab. Gap: full `SelectionManager` audit not done |
| M68 Specialist modules | NOT IMPLEMENTED | No defensible sourced method added; OWNER REVIEW REQUIRED before any |
| M69 Integration | PARTIAL | Navigation additions; dashboard unchanged (English/LTR dark); offline; workflows A–F not separately scripted |

## 4. Features and runtime behaviour

### M61 (`core/mineru_engine.py`, `core/ddr_import_queue.py`, `dialogs/excel_import_dialog.py`, `dialogs/ddr_profile_dialog.py`, `core/import_adapters/pdf_*`)

* **Dates.** `DocumentNormalizer._profile_value` applies the profile's ordered `date_formats` to date-typed canonical fields. One calendar date → accepted with `conversion_rule = date_format <fmt> (profile <key> v<n>)`. Formats that agree are not ambiguous. Two different dates → value empty plus a review item listing every reading; no match → review item quoting the original string. Without a profile the canonical parser is unchanged.
* **Table rules.** `stop_markers` (the marker row and all later rows of that table), `skip_rows_containing`, and the new `skip_tables_containing`. Each ignored row/table becomes a review warning with `rule`, `profile_rules_version`, value and `source` (page/row/table). The profile editor now edits all three rule lists; previously saving a profile rebuilt `table_rules` from stop markers only, which would have dropped other rules.
* **Continuation.** `parse_pdf_native_fallback(continuation=…)` → `extract_tables` → `generic_document_tables` / `join_continuations(join=…)` / `join_ruled_continuations`. Disabled: no page joins and no header-less carry-over; `row_pages` provenance remains.
* **Threshold.** `review_thresholds` / `review_counts`: accept-eligible ≥ threshold; review band [min(0.70, t), t); low below. The preview header shows the counts; bulk accept, review filter, bulk reject and row colours use the bands; values still in `needs_review` are never bulk-accepted. Without a profile the historical 95 %/70 % bands apply.
* **Metadata.** `NormalizedDocument.metadata()` carries `profile` (key, version, date formats, rules, continuation, threshold) and `profile_rules_version` (`PROFILE_RULES_VERSION = 1`). `NORMALIZATION_VERSION` in `core/search_normalization.py` is the document-search normaliser and was correctly **not** bumped; the DDR rules got their own version.
* **Batch queue.** `ImportQueue` (pure Python): add (SHA-256 in-batch duplicates → DUPLICATE without running), start/finish, remove (QUEUED/FAILED/CANCELLED/SKIPPED/DUPLICATE only; SAVED is kept), retry (FAILED/CANCELLED/SKIPPED), cancel (QUEUED → CANCELLED; the running file finishes its atomic save), counts, summary. Result mapping: `reimport` → DUPLICATE (previously counted as success), preview cancel → SKIPPED (previously counted as failed), ACCEPT → SAVED, REVIEW_REQUIRED → REVIEW_REQUIRED, else FAILED. The dialog shows a queue table (file, status, stage, profile, attempts, diagnostics) and the three buttons; every pipeline stage updates the row.
* **OCR.** The existing `ocr_status()` detection and "OCR unavailable: page(s) … have no text layer" diagnostic were reused; nothing was installed.

### M62 (`core/well_plan_designer.py` → `M62 plan designer v2`, `core/directional_plans.py`, `tabs/well_plan_designer_panel.py`)

* **Arc target distance.** `arc_point` evaluates the minimum-curvature arc between stations; `closest_on_path` samples each interval (32 points) and refines by golden section to 1e-9 of the interval; `evaluate_target` reports the continuous distance, MD and point, plus the closest station and its distance. The version bump is deliberate (method change); two M55 tests that pin the version literal were updated to the new literal.
* **Safeguards.** Non-finite segment, target, tie-in, step, DLS-limit or VS-azimuth values; antiparallel curves (dogleg ≥ 180° − 1e-6, undefined plane) → explicit errors, no stations.
* **Plans.** `DirectionalPlanRevision`: `plan_key` + `revision` unique, `parent_id`, `status` (draft/approved/archived), method, method version, inputs, results, note. `save_plan` refuses invalid plans. `revise_plan` adds the next revision and never edits the parent; `clone_plan` starts a new key; `set_status` cannot reactivate an archived revision; `compare_plans` reports input diffs and TD/TVD/max DLS/end N/E deltas; `export_plan_csv` writes a labelled CSV.
* **Panel.** Saved-plan combo with Open / Save as new / Save revision / Clone / Archive / Compare with open, following the Trajectory viewer's selected well. Opening a revision saved with an older designer redesigns it with the current one and says so; the stored revision is unchanged. The plan library is enabled only when the database manager supports sessions; a load failure is shown and logged, and never breaks the survey viewer (regression found by the full suite and fixed in `dd6d5c6`). The new **Plots** tab shows Inc/Azi/DLS/TVD vs MD.

### M63 (`core/calculation_cases.py`, `tabs/calculation_cases_panel.py`, W13)

* `CalculationCase` is insert-only (data-layer write policy `NOBODY`). The case bar under the finder captures the open calculator page generically: inputs are spin/combo/editable line edit/check/radio; results are bordered result labels, read-only line edits and read-only text panes, with form labels kept. Reopen navigates through the finder and restores inputs, reporting anything not restored. Compare with current; Re-run & save clicks the page's Calculate button (or relies on auto-calculation) and stores a child case. The panel refuses to store a case without results (and a re-run that produced none); the core refuses a case without inputs.

### M67 (`core/calculation_history.py`, `tabs/calculation_history_tab.py`, `main_window.py`)

* Read-only adapters for `torque_drag_calculations`, `casing_calculations`, `cement_calculations`, `mse_calculations`, `mud_volume_calculations`, `well_control_kill_sheet_calculations`, `trajectory_calculations`, `calculation_cases`, `directional_plan_revisions`. Models are resolved by table name; a missing model raises rather than silently dropping a source. (Found while building: the engine classes are named `…CalculationRecord`, so a class-name lookup would have skipped all six.)
* Filters (well, source, text, date range), flattened compare, CSV export.
* Recalculate & verify: engine snapshots use each engine's own `recalculate_from_snapshot` and the shared `classify_verification` (MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE, method-change flag); plans re-run the designer. `save_recalculation` stores a new `calculation_cases` row whose note names the original record, its version and the verification status. The original record is never written.
* Report Center: single-entry and comparison HTML (template v1) with source, record, method, version, created, scope, derived-from, inputs, results, well, generation time and the UNSIGNED / not-validated statement; PDF via `QTextDocument` + `QPdfWriter`.

## 5. Migrations and data safety

Two **additive** tables, created by the existing guarded migration path (missing model tables are created inside the migration transaction): `directional_plan_revisions`, `calculation_cases`. Both have `TABLE_POLICY` entries (plans: insert/write `can_edit_reports`, delete `can_delete_well`; cases: insert `can_edit_reports`, write `NOBODY`, delete `can_delete_well`) and `well_id` indexes in `INDEX_PLAN`. No existing table, column or record was changed. Old databases gain the two empty tables. `test_database_migration_acceptance.py`, `test_schema_indexes.py` and `test_data_layer_authorization.py` pass. The 2.675 rounding contract was not touched.

## 6. Method versions

| Method | Version |
|---|---|
| Plan designer | `M62 plan designer v2` (was `M55 plan designer v1`) |
| DDR profile rules | `PROFILE_RULES_VERSION = 1` (new) |
| Import queue | `QUEUE_VERSION = 1` |
| Calculation cases | `CASE_CAPTURE_VERSION = 1`; W13 label `W13 calculator (no per-method version); case capture v1` |
| History / report template | `HISTORY_VERSION = 1`, `REPORT_TEMPLATE_VERSION = 1` |

## 7. Reuse and licences

No external code was copied and no dependency was added. Reused in-repo: canonical `TrajectoryCalculator`, engine `recalculate_from_snapshot` modules, `classify_verification`, `ocr_status`, the import-audit fingerprint duplicate check, `CalculatorFinder` paths, pyqtgraph (existing core requirement). The adoption register is unchanged (no integration). PyMuPDF remains AGPL and visible (owner item).

## 8. Validation

| Gate | Result |
|---|---|
| Full suite, M61 tip `47803c6` | PASS — archive-snapshot run: 4058 passed, 4 skipped, 5 failed + 2 errors all `git ls-files failed` (the snapshot was not a git repository); those 7 plus the other 54 tests in their files then ran in a real clone at `47803c6`: 61 passed |
| Full suite, `ae49c7e` (fresh clone) | 4085 passed, 4 skipped, **2 failed** (`test_m44_ui::test_viewer_single_station_is_listed_but_not_drawn`, `test_trajectory_3d::test_single_station_is_not_drawn_in_3d`: plan library on a survey-only DB stub) → fixed in `dd6d5c6` with a regression test |
| Full suite, final code tip `d3a64f3` (fresh clone) | PASS — 4089 passed, 4 skipped, 0 failed (1067 s) |
| Test count | 4047 (M53–M60 tip) → 4093: +46 new (M61 23, M62 15, M63 4, M67 4); none removed or skipped |
| Expected skips | `test_ddr_acceptance.py:33` ×2, `test_mineru_real_integration.py:26`, `test_packaging_smoke.py:218` |
| Lint | PASS — 727 / ceiling 727 (`verify_release.verify_lint`) |
| Exception gate | PASS — rc 0 (`exception_scan.py --check`) |
| Privacy | PASS — 0 findings (1260 files at `d3a64f3`) |
| Mutation M61–M67 | PASS — 19/19 killed, 0 equivalent, 0 invalid (`docs/mission-reports/m61-m69-evidence/mutation_m61_m67.json`) |
| Mutation M53–M56 re-pointed | PASS — `WP-target-radius-ignored`, `TV-callback-reference-cycle` killed after their snippets were moved to the changed lines (same mutation) |
| Coverage | Floor 45.50 enforced by the CI 3.12 leg (PASS on `47803c6`); exact percentage NOT RUN locally |

Independent references: planar circular-build closed form (HD = R(1−cos θ), TVD = KOP + R sin θ, MD = KOP + Rθ; target at θ = 10.5°, between stations, is hit with distance < 1e-6 m while the station method misses by > 7 m); perpendicular offset from a vertical hold (exactly 7 m); M55 golden J-profile TD 1623.9032011 m through the history adapter; Teale MSE hand value 127 997.67 psi through the real MSE repository; W13 Quick Calc capacity ID²/1029.4 for ID 4.276 in.

Test labels: normaliser, queue, plan and history core tests are pure Python on temporary SQLite databases with synthetic data. Dialog, panel, W13 and history-tab tests run **offscreen Qt** on Linux with the real widgets; the import-dialog batch tests replace the preview with an auto-confirm stub and `_do_import` with a recorder (persistence atomicity is covered by the existing import-service tests). Not Windows desktop testing.

## 9. CI (exact full-SHA equality)

| SHA | Workflow | Run | Result |
|---|---|---|---|
| `47803c607db6c3f0a2a8c704398dee03f0786a75` | Source release gate | 41297308994 | success (3.11, 3.12 coverage leg, 3.13) |
| `47803c607db6c3f0a2a8c704398dee03f0786a75` | Windows release validation | 41297309034 | success |
| `d3a64f380fa4eb1483ad69c47abcfdb7fb2f1e3b` | Source release gate | 41300131298 | success (3.11, 3.12 coverage leg, 3.13) |
| `d3a64f380fa4eb1483ad69c47abcfdb7fb2f1e3b` | Windows release validation | 41300131280 | success |

URLs: `https://github.com/asgareyvazi/Drill-master/actions/runs/<run id>`. Windows CI is not desktop acceptance.

## 10. Limitations

* DDR heavy extraction (XLSX, PDF-native fallback, validation) still runs on the GUI thread with event processing; only MinerU parsing is in a worker. Cancel takes effect between files.
* Profile suggestion, header/identify/column table rules: NOT IMPLEMENTED.
* Plan designer: no target solver or rate constraints; plans store designer inputs, not a tie-in to a survey revision.
* W13 cases capture what the page shows; calculators have no per-method version; restoration depends on widget order on the page (a UI change to a calculator page can make an old case partly unrestorable, which is reported).
* History: trajectory records and W13 cases have no recalculation adapter (stated in the UI). Snapshot-engine recalculation uses the current method only; the original method version cannot be re-executed, and a method change is flagged.
* M64/M65/M66/M68 not extended; M69 workflows A–F not separately scripted.

## 11. Owner gates (unchanged, none closed)

History purge, force-push, money migration; PyMuPDF AGPL; OCR engines/model weights; GPL/LGPL/CC-NC code (pwptemp, torque_drag); welleng ISCWSA; release, tag, signing; Windows desktop, field and production acceptance; destructive real-database changes; branch protection; Ollama/models/cloud LLM/datasets/ML/GPU; well-control acceptance; any M68 specialist method.

## 12. Acceptance matrix

| Requirement | Status |
|---|---|
| Every stored profile field affects import (dates, table rules, continuation, threshold) | PASS |
| Ambiguous/unmatched dates → review with original string | PASS |
| Each ignored row has a reason and source | PASS |
| Threshold drives eligibility, review state, counts | PASS |
| Batch queue states, remove, retry, cancel, duplicates, summary | PASS |
| Worker thread for all heavy import work | PARTIAL |
| OCR adapter shows "OCR unavailable" | PASS (detection only; engine owner-gated) |
| Persistent versioned plans; revisions never overwritten | PASS |
| Continuous target distance on the arc | PASS |
| Numerical safeguards with explicit errors | PASS |
| DLS/inc/az/TVD vs MD plots | PASS |
| Target solving / rate constraints | NOT IMPLEMENTED |
| W13 named immutable cases, reopen, compare, re-run as new case | PASS |
| Unified calculation history, filters, compare | PASS |
| Recalculation stored separately; originals untouched | PASS |
| Report Center HTML/PDF with method, version, scope, UNSIGNED | PASS |
| Additive, old-DB-compatible migrations | PASS |
| No SF without uncertainty; anti-collision SCREENING | PASS (unchanged) |
| M65 schematic from records | NOT IMPLEMENTED |
| M68 specialist modules | NOT IMPLEMENTED / OWNER REVIEW REQUIRED |
| Windows desktop acceptance | OWNER REVIEW REQUIRED |
| Release readiness | NOT RELEASE-APPROVED (UNSIGNED) |

## 13. Final git evidence

Captured after the report commit was pushed; reproduced in the final reply (a file cannot contain the state after its own commit).

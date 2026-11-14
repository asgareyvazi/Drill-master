# M177–M180: legacy "Trajectory Plot" tab, forensic inventory and migration

Status: **RETIRED** (UI) in M180. The data is **KEPT**, and old rows can be read through a read-only adapter.
UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.

## 1. Inventory of the legacy tab (as of `43b1115`)

`tabs/w6_Trajectory_Widget.py` at `43b1115`: `TrajectoryPlotTab` (lines 547–720) and `TrajectoryCalculationManager` (723–742). `TrajectoryWidget.init_ui` added the sub-tab "Trajectory Plot" (line 800).

| Function | Legacy behaviour | Defect / gap |
|---|---|---|
| Plot | `core.survey_records.plot_series` of **one report's** stations; 2D plan and side views (pyqtgraph) and a Matplotlib 3D axes (`core.trajectory_plot.draw_trajectory_3d`) | Per-report frame only. The stored derived columns of different reports are not one coordinate frame (see `core/well_trajectory.py` docstring) |
| Save | `db.save_trajectory_plot({report_id, plot_type: '2d_plan', title: 'Trajectory Plot <timestamp>', plot_data: json(self.plots), image_data: None})` | No name input; bound only to a daily report, with no well, wellbore or survey revision. `plot_type` is always `'2d_plan'`. No audit record. Returned False silently when no DB |
| Load | `load_plots()` → `plot_trajectory()`. It replotted the **current** surveys | A saved row was never reopened. The saved snapshot was write-only |
| Clear | cleared the axes and `self.plots` | — |
| Export CSV | columns `Type,Index,X,Y,Z`; rows `2D_Plan,i,east,north,0` and `2D_Side,i,hd,tvd,0` | **`Z` is the constant 0** (a zero standing in for a missing value). No units anywhere. No well / report / provenance header |
| Export JSON | `json.dump(self.plots)` | No units, no provenance |
| `TrajectoryCalculationManager.create_calculation` | inserted an empty `trajectory_calculations` row (no parameters / results) | Instantiated only at `w6:766`; **no caller**. D27 (M108) already records it as the only and unused caller |

### Consumers found (`git grep` at `43b1115`)

| Consumer | Kind | Action |
|---|---|---|
| `TrajectoryWidget.update_tabs` / `save_data` / `SurveyDataTab.save_data` (`plot_tab.load_for_report`, `load_plots`) | internal refresh of the sibling tab | removed with the tab |
| `tools/screenshots/capture_m44.py` "pre-M44" branch | captures *before* screenshots when it runs on a pre-M44 checkout (`else` of `viewer is not None`) | unchanged; it never runs on this code |
| `core.trajectory_plot.draw_trajectory_3d`, `core.survey_records.plot_series` | used by `tools/certify_ddr*.py`, `tools/real_user_acceptance.py`, `tests/test_ddr_followup_lifecycle.py`, `tests/test_ddr_forensic_regressions.py` | **kept**; they are independent of the tab |
| `DatabaseManager.save_trajectory_plot` / `load_trajectory_plots`, model `TrajectoryPlot` (`trajectory_plots`) | data layer | **kept** (old DBs and the read-only adapter) |
| `TrajectoryCalculation` (`trajectory_calculations`) | also used by `core/trajectory_compare.py` (M52) and `core/calculation_history.py` | **kept**; only the unused manager class was removed |
| tests | none referenced `TrajectoryPlotTab` / `TrajectoryCalculationManager` / `plot_tab` | — |

## 2. Canonical replacement: Well Trajectory Viewer → "Saved views" (M178)

Code: `core/trajectory_views.py` (`trajectory-view-v1`), `tabs/trajectory_saved_views_panel.py`, `TrajectoryViewerTab.show_saved_view` / `view_settings` (`tabs/trajectory_viewer.py`).
Storage: `trajectory_view_revisions` (model `TrajectoryViewRevision`, `core/database.py`), created additively on old databases by the generic missing-table step.

| Requirement | Implementation | Evidence (`tests/test_m178_trajectory_views.py`) |
|---|---|---|
| Named | name required, whitespace-normalised, ≤ 200 chars, unique (case-insensitive) among ACTIVE views of the well | `test_invalid_views_are_refused…`, `test_foreign_wellbore_duplicate_name…` |
| Bound to well / wellbore / revision | `well_id` NOT NULL (CASCADE); `wellbore_id` must belong to the well (SET NULL on delete); source = working survey stations (optionally one report scope, frozen `source_report_id`) or an immutable survey revision of the same well with VERIFIED integrity | `test_a_saved_view_is_bound…`, `test_a_report_scope…`, `test_a_view_bound_to_a_survey_revision…`, `test_views_leave_only_with_their_well…` |
| Reopen | shows the **stored snapshot** and its settings, never recomputes it. The banner states the drift of the current data: MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE (integrity: SHA-256 of the snapshot) | `test_reopen_reports_different…`, `test_a_tampered_snapshot…`, the viewer journey test |
| Clone | new view (revision 1, action CLONE, `parent_id` = source revision) with the snapshot copied unchanged; refused for a non-VERIFIED snapshot | `test_revise_clone_archive_restore…` |
| Revise | new revision from the current data and settings; **optimistic concurrency** (`expected_revision` re-checked inside the writing transaction, and the unique key `(view_key, revision)` as the last guard) | `test_revise_clone…`, `test_a_revision_saved_concurrently…`, `test_a_stale_panel_cannot_revise…` |
| Compare | pairs stations by MD (1e-6 m); stations present on one side only are listed and **never interpolated**; settings changes listed | `test_compare_pairs_stations_by_md…` |
| Archive / restore | new revision with status ARCHIVED / ACTIVE and a mandatory reason. An archived view is read-only until it is restored | `test_revise_clone_archive_restore…` |
| Immutable | insert-only policy (`TABLE_POLICY`); storage guards `trg_trajectory_view_immutable_v1`, `_noreplace_v1`, `_nodupkey_v1`, `_nodelete_v1` | `test_a_saved_view_revision_is_immutable_for_every_writer`, `test_a_viewer_principal_cannot_save_a_view` |
| Audit | one mandatory audit record per action (`trajectory_view_create/revise/clone/archive/restore`), in the same transaction | `test_a_saved_view_is_bound…`, `test_revise_clone…` |
| Messages | every failure says **NOT SAVED** (or NOT EXPORTED) and creates no row. Success text appears only after the DB returned the revision | viewer journey tests |

## 3. Export (M179)

`core.trajectory_views.export_csv` / `export_json` (`trajectory-view-export-v1`):

* exports only the stored stations of one saved revision (no interpolation, no resampling);
* the unit is the viewer's display unit (m or ft) and appears in every column header (`MD (ft)`, `DLS (deg/100ft)`) and in a `Units` line. Conversion uses the exact foot (0.3048 m) and 100 ft = 30.48 m;
* the header records the view name, revision and status, well, wellbore, source (survey revision id / report id), VS azimuth and its source, method and method version, and the snapshot SHA-256;
* a value the snapshot does not hold is an **empty cell** (CSV) or `null` (JSON), never 0;
* a snapshot that fails its integrity check is not exported.

**Comparison with the legacy output** (`test_export_has_units_and_provenance_and_differs_from_the_legacy_zero_z_output`): the retired CSV branch is reproduced verbatim in the test. For the same stations it writes `Z = 0` on every row and has no unit. The new export carries TVD (e.g. 2580.311344 ft at MD 800 m of the M72 J-profile) and the units. MD 500 m exports as 1640.419948 ft, and 3 deg/30 m as 3.048 deg/100 ft.

## 4. Retirement (M180)

* Removed: `TrajectoryPlotTab`, `TrajectoryCalculationManager`, the "Trajectory Plot" sub-tab and its refresh calls, and the unused imports (`csv`, `json`, `date`, `Dict`, `List`, the pyqtgraph probe) in `tabs/w6_Trajectory_Widget.py`. W6 sub-tabs are now: Well Trajectory Viewer, Trip Sheet, Survey Data.
* Kept: the `trajectory_plots` and `trajectory_calculations` tables and rows, `DatabaseManager.save_trajectory_plot` / `load_trajectory_plots`, `core.trajectory_plot`, `core.survey_records.plot_series`.
* Read-compat adapter: `core.trajectory_views.legacy_plots(db, well_id)` lists the legacy rows of the well's reports, read-only. It shows the title, report and date, the number of plan points, or UNREADABLE for a broken payload, and a label that the row is bound to a report only and that its old CSV wrote Z = 0. The Saved views panel shows this list. Test: `test_legacy_trajectory_plot_rows_stay_and_are_listed_read_only_per_well` checks that the rows are byte-identical after listing.
* Not done (by rule): no migration converts a legacy row into a saved view. A legacy row has no well, wellbore or revision binding and no input stations, so a conversion would have to invent them.

## 5. Limits

* A user with write access to the database file can drop the guard triggers (the same documented limit as M70 / M136). A tampered snapshot is then reported as HASH MISMATCH / UNREADABLE and is never drawn, compared, cloned or exported.
* No survey uncertainty, grid convergence or map projection. The snapshot carries the source's datum and azimuth reference implicitly (working stations) or through the survey revision.
* Interactive Windows acceptance of the new panel: **NOT RUN**.
